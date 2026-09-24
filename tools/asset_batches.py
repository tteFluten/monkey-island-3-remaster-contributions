#!/usr/bin/env python3
"""Scene/costume checkpoints. Each run processes exactly one selected batch."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
import time

from quiver_cannon import atomic, locked
from topaz_character_cutouts import digest, load_jobs, run
from topaz_scenes import (API, EXISTING, OUTPUT, ROOT, completed,
                          materialize, natural, prepare_scene, read)


def build_plan(plan, size=32):
    if size < 1:
        raise ValueError('Batch size must be positive')
    batches = []
    priority = set(plan.get('previous_crisp_sources', []))
    for scene in plan['scenes']:
        groups = defaultdict(list)
        for entry in scene['sources']:
            source = entry['source']
            group = re.sub(r'_frame_\d+\.png$', '', Path(source).name) if source.startswith('costumes/') else source.split('/')[0]
            op = entry['operation']
            phase = ('preserve' if op == 'preserve' else 'pilot' if op == 'review-small'
                     else 'reuse' if op in ('alias', 'derive-layer', 'empty') else 'process')
            groups[(group, phase, source in priority)].append(entry)
        number = 0
        for (group, phase, crisp), entries in sorted(groups.items(), key=lambda item: (not item[0][2], natural(item[0][0]), item[0][1])):
            for start in range(0, len(entries), size):
                number += 1
                selected = sorted(entries, key=lambda e: natural(e['source']))[start:start+size]
                batches.append(dict(id=f"{scene['id']}-b{number:03}", scene=scene['id'], room=scene['room'],
                    name=scene['name'], group=group, phase=phase, previous_crisp=crisp,
                    sources=[e['source'] for e in selected],
                    planning_minimum_credits=sum((not e.get('cached_scale')) + (e['operation']=='upscale-matting')
                        for e in selected if e['operation'] in ('upscale-only', 'upscale-matting'))))
    owner = {source: b['id'] for b in batches for source in b['sources']}
    entries = {e['source']: e for s in plan['scenes'] for e in s['sources']}
    for b in batches:
        b['dependencies'] = sorted({owner[entries[s]['parent']] for s in b['sources']
                                    if entries[s].get('parent') and owner[entries[s]['parent']] != b['id']})
    assert len(owner) == sum(len(b['sources']) for b in batches) == plan['total_sources']
    return dict(version=1, batch_size=size, total_sources=len(owner), scene_count=len(plan['scenes']),
                policy='One explicit batch per run; review and install separately; wait for user before next batch.', batches=batches)


def prepare(output, size=32):
    path = output/'batches/plan.json'
    fingerprint = digest(output/'plan.json')
    old = read(path)
    if old:
        if old['scene_plan_sha256'] != fingerprint or old['batch_size'] != size:
            raise ValueError('Existing batch IDs are frozen; reconcile the changed plan before replacing them')
        return old
    value = build_plan(read(output/'plan.json'), size)
    value.update(scene_plan_sha256=fingerprint, prepared_at=time.time())
    atomic(path, value)
    return value


def report(output, local):
    plan = read(output/'plan.json'); batches = read(output/'batches/plan.json')
    if batches['scene_plan_sha256'] != digest(output/'plan.json'):
        raise ValueError('Scene plan changed; reconcile the batch plan')
    entries = {e['source']: e for scene in plan['scenes'] for e in scene['sources']}
    files = completed(output, plan); jobs = {}
    bases = [Path(plan['source_batch']).parent/d for d in EXISTING] + [output/s['id'] for s in plan['scenes']] + [output/'derived']
    for base in bases:
        jobs.update(load_jobs(base) if (base/'jobs.json').exists() else {})
    reviewed = {}
    def approved(source, trail=()):
        if source in reviewed: return reviewed[source]
        if source in trail: raise ValueError('Cyclic review dependency')
        if source not in files: return False
        f = files[source]; e = entries[source]
        result = f['reviewed'] or read(output/'reviews'/(source+'.json'), {}).get('sha256') == f['sha256']
        if not result and e.get('parent') in files:
            result = f.get('parent_sha256') == files[e['parent']]['sha256'] and approved(e['parent'], trail+(source,))
        reviewed[source] = result
        return result
    drafts = read(local/'draft-install/receipt.json', {}).get('assets', {})
    def draft_installed(source):
        draft = drafts.get(source)
        if not draft: return False
        targets = ([local/'hd'/pack/source.replace('_frame_', '_aframe_') for pack in ('topaz-cannon','topaz-crisp')]
                   if source.startswith('costumes/') else [local/'hd'/source])
        return all(p.exists() and digest(p)==draft['sha256'] for p in targets)
    states = {}
    for source, e in entries.items():
        op = e['operation']; job = jobs.get(source, {})
        if op in ('preserve', 'empty'):
            state = op
        elif source in files:
            f = files[source]
            targets = ([local/'hd'/pack/source.replace('_frame_', '_aframe_') for pack in ('topaz-cannon','topaz-crisp')]
                       if source.startswith('costumes/') else [local/'hd'/source])
            if not f['master'].exists() or digest(f['master']) != f['sha256']:
                state = 'changed_output'
            elif not approved(source): state = 'needs_review'
            elif all(p.exists() and digest(p) == f['sha256'] for p in targets): state = 'installed'
            else: state = 'ready_to_install'
        elif job.get('state') in ('rejected','failed','unknown','submitting'):
            state = 'needs_repair' if job['state'] == 'rejected' else 'needs_provider_review'
        elif job.get('state') == 'submitted': state = 'in_flight'
        elif op == 'review-small': state = 'needs_pilot'
        elif op in ('alias','derive-layer'): state = 'waiting_for_parent'
        else: state = 'pending'
        if state not in ('installed','preserve','empty') and draft_installed(source):
            state = 'installed_draft'
        states[source] = state
    results = []
    for batch in batches['batches']:
        counts = Counter(states[s] for s in batch['sources'])
        done = all(s in ('installed','preserve','empty') for s in counts)
        results.append({**batch, 'counts': dict(counts), 'complete': done})
    result = dict(updated_at=time.time(), total_sources=len(states), counts=dict(Counter(states.values())), batches=results)
    atomic(output/'batches/status.json', result)
    lines = ['# Asset batch checkpoints', '',
        '32 files maximum per batch, grouped by scene and costume/object type. IDs and membership are frozen.',
        'One explicit batch per run. Stop for review, installation and user handoff before another batch.',
        'Resource numbers are organizational groups, not verified story order. Backgrounds are excluded.', '',
        'Counts distinguish provider processing, visual review and actual installed file hashes. Complete does not mean animation-tested.', '',
        '| Scene | Name | Files | Batches | Approved installed | Draft installed | Needs review | Repair/provider review |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for scene in plan['scenes']:
        selected = [b for b in results if b['scene']==scene['id']]
        c = Counter(states[e['source']] for e in scene['sources'])
        lines.append(f"| {scene['room']} | {scene['name']} | {len(scene['sources'])} | {len(selected)} | {c['installed']} | {c['installed_draft']} | {c['needs_review']} | {c['needs_repair']+c['needs_provider_review']} |")
        detail = [f"# Scene {scene['room']}: {scene['name']}", '',
                  '| Batch | Group | Kind | Files | Dependency batches | Status |', '| --- | --- | --- | ---: | --- | --- |']
        for b in selected:
            counts = ', '.join(f'{n} {state}' for state,n in sorted(b['counts'].items()))
            detail.append(f"| {b['id']} | {b['group']} | {b['phase']} | {len(b['sources'])} | {', '.join(b['dependencies']) or '—'} | {counts} |")
        detail += ['', '## Exact source lists', '']
        for b in selected:
            detail += [f"### {b['id']}", '', *[f'- `{s}`' for s in b['sources']], '']
        (output/'batches'/f"{scene['id']}.md").write_text('\n'.join(detail))
    (output/'batches/README.md').write_text('\n'.join(lines)+'\n')
    return result


def execute(output, batch_id, api, max_credits, local):
    if max_credits < 0: raise ValueError('Credits must be nonnegative')
    plan = read(output/'plan.json'); batch_plan = read(output/'batches/plan.json')
    if batch_plan['scene_plan_sha256'] != digest(output/'plan.json'):
        raise ValueError('Scene plan changed')
    batch = next((b for b in batch_plan['batches'] if b['id']==batch_id), None)
    if batch is None: raise ValueError('Unknown batch ID')
    if batch['phase'] == 'pilot': raise ValueError('Review a padded-input pilot before processing this batch')
    source_batch = Path(plan['source_batch'])
    if digest(source_batch/'manifest.json') != plan['source_manifest_sha256']:
        raise ValueError('Source manifest changed')
    scene = next(s for s in plan['scenes'] if s['id']==batch['scene'])
    selected = [e for e in scene['sources'] if e['source'] in batch['sources']]
    tasks = defaultdict(list)
    for entry in selected:
        if entry['operation'] == 'existing':
            tasks[source_batch.parent/entry['owner']].append(entry['source'])
        elif entry['operation'] in ('upscale-only','upscale-matting'):
            tasks[prepare_scene(output, scene, source_batch)].append(entry['source'])
    def selected_cost(base):
        jobs = read(base/'jobs.json', {})
        return sum(h['estimate']['credits'] for source in tasks[base]
                   for h in jobs.get(source, {}).get('history', []))
    budget_path = output/'batches'/batch_id/'budget.json'
    budget = read(budget_path)
    if not budget:
        budget = dict(ceiling=min(max_credits, api.balance()) if tasks else 0,
                      baselines={str(base): selected_cost(base) for base in tasks})
        atomic(budget_path, budget)
    elif max_credits != budget['ceiling']:
        raise ValueError(f"Resume this batch with its frozen ceiling: {budget['ceiling']}")
    def spent(): return sum(selected_cost(Path(base))-initial for base,initial in budget['baselines'].items())
    def progress(state):
        atomic(output/'batches'/batch_id/'progress.json', dict(state=state, batch=batch_id,
            credits=spent(), ceiling=budget['ceiling'], updated_at=time.time()))
    progress('running')
    try:
        for base, sources in tasks.items():
            if (output/'stop-after-current').exists(): break
            # Never pass an empty selection: the underlying runner interprets it as all records.
            assert sources and set(sources) <= set(batch['sources'])
            with locked(base):
                run(base, api, max(0,budget['ceiling']-spent()), sources=sources,
                    concurrency=4, require_pilots=False, stop_files=(output/'stop-after-current',))
        # Resolve free parent dependencies, without starting any other paid batch.
        entries = {e['source']: e for s in plan['scenes'] for e in s['sources']}
        needed = set(batch['sources'])
        todo = list(needed)
        while todo:
            parent = entries[todo.pop()].get('parent')
            if parent and parent not in needed:
                needed.add(parent); todo.append(parent)
        scoped = {**plan, 'scenes': [{**s, 'sources': [e for e in s['sources'] if e['source'] in needed]} for s in plan['scenes']]}
        materialize(output, scoped)
        result = next(b for b in report(output, local)['batches'] if b['id']==batch_id)
        result.update(credits=spent(), ceiling=budget['ceiling'], stopped_at_checkpoint=True)
        atomic(output/'batches'/batch_id/'handoff.json', result)
        progress('checkpoint')
        print(f"{batch_id}: {result['counts']}; {spent()} credits. Stopped at checkpoint; no next batch started.")
        return result
    except Exception:
        progress('interrupted')
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('prepare','status','run'))
    p.add_argument('--output', type=Path, default=OUTPUT)
    p.add_argument('--local', type=Path, default=ROOT/'.playtest')
    p.add_argument('--batch-id')
    p.add_argument('--max-credits', type=int, default=0)
    args = p.parse_args()
    with locked(args.output/'batches'):
        if args.command == 'prepare': prepare(args.output)
        elif args.command == 'run':
            if not args.batch_id: p.error('run requires --batch-id; automatic advancement is disabled')
            with locked(args.output):
                execute(args.output, args.batch_id, API(ROOT/'.context/secrets/topaz-api-key',4), args.max_credits, args.local)
            return
        result = report(args.output, args.local)
        print(f"{len(result['batches'])} batches, {result['total_sources']} files: {result['counts']}")
        print(args.output/'batches/README.md')


if __name__ == '__main__':
    main()
