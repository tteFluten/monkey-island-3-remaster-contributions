#!/usr/bin/env python3
"""Inventory Guybrush's full resource sets and prioritize their existing Topaz jobs."""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import os
from pathlib import Path
import re
import time

from quiver_cannon import atomic, locked
from topaz_batch import API
from topaz_character_cutouts import digest, load_jobs, run
from topaz_parallel_scenes import cost, TERMINAL
from topaz_scenes import OUTPUT, ROOT, read, natural, prepare_scene, materialize

# Resource sets identified from local contact sheets, including combined actor
# animations, detached limbs, disguises, child poses and distant representations.
# Membership is deliberately whole-resource, not a guessed interval of cels.
COSTUMES = (
    2,3,4,5,6,14,15,17,24,29,30,31,33,61,64,65,76,79,81,82,86,88,90,94,
    96,99,100,113,121,122,123,125,132,134,135,137,138,139,142,145,150,151,
    152,153,155,157,158,161,165,172,179,180,183,184,192,193,194,195,204,
    209,210,213,254,268,274,280,281,282,283,285,287,297,300,303,304,307,
    312,313,314,315,316,317,320,324,326,327,329,331,332,335,336,342,346,
    353,354,355,357,361,362,366,372,373,378,379,384,388,389,394,399,401,
    404,407,408,409,410,411,412,413,417,422,427,430,431,433,435,
)
# Palette-dependent dissolves / native shadow are not ordinary painted sprites.
EFFECTS = {65, 192, 366}


def costume(source):
    match = re.search(r'_AKOS_(\d+)_', source)
    return int(match[1]) if match else None


def selection(plan):
    entries = {e['source']: dict(e, scene=s['id']) for s in plan['scenes'] for e in s['sources']}
    selected = [s for s in entries if costume(s) in COSTUMES]
    owners = {}
    def owner(source, trail=()):
        if source in trail:
            raise ValueError('Cyclic asset dependency')
        e = entries[source]
        if e['operation'] == 'alias':
            return owner(e['parent'], trail + (source,))
        if e['operation'] == 'existing':
            return '../' + e['owner']
        if e['operation'] in ('upscale-only', 'upscale-matting'):
            return e['scene']
        return None
    for source in sorted(selected, key=lambda s: (costume(s) != 2, natural(s))):
        if costume(source) in EFFECTS:
            continue
        base = owner(source)
        if base:
            while entries[source]['operation'] == 'alias':
                source = entries[source]['parent']
            owners[source] = base
    return entries, selected, owners


def prepare(output=OUTPUT):
    plan = read(output/'plan.json')
    entries, sources, owners = selection(plan)
    folder = output/'batches/guybrush-all'
    membership = dict(scene_plan_sha256=digest(output/'plan.json'), costumes=list(COSTUMES),
                      sources=sources, owners=owners, native_effect_costumes=sorted(EFFECTS))
    previous = read(folder/'plan.json')
    if previous and previous != membership:
        raise ValueError('Frozen Guybrush membership changed')
    atomic(folder/'plan.json', membership)
    # Check the actual game resource headers so omissions cannot look complete.
    from quiver_extract import resources
    import struct
    actual = []
    for cid, room, raw, fields, _ in resources(ROOT/'.playtest/game', COSTUMES):
        count = struct.unpack('<6H', fields['AKHD'][:12])[3]
        missing = [f'costumes/LFLF_{room:04}_AKOS_{cid:04}_frame_{n}.png'
                   for n in range(count) if f'costumes/LFLF_{room:04}_AKOS_{cid:04}_frame_{n}.png' not in entries]
        actual.append(dict(costume=cid, room=room, native_cels=count, missing_sources=missing))
    atomic(folder/'native-coverage.json', dict(resources=actual, total_native_cels=sum(r['native_cels'] for r in actual)))
    return membership


def status(output=OUTPUT, local=ROOT/'.playtest'):
    plan=read(output/'plan.json'); entries, sources, owners=selection(plan)
    jobs={}; masters={}
    for base in set(owners.values()):
        path=output/base
        for source,job in (load_jobs(path) if (path/'jobs.json').exists() else {}).items():
            jobs[source]=job;masters[source]=path/'4x'/source
    rows=[]
    for source in sources:
        root=source;seen=set()
        while entries[root]['operation']=='alias':
            if root in seen:raise ValueError('Cyclic alias')
            seen.add(root);root=entries[root]['parent']
        e=entries[source];job=jobs.get(root,{})
        state='native_effect_review' if costume(source) in EFFECTS else job.get('state',e['operation'])
        sha=job.get('validation',{}).get('sha256')
        installed=bool(sha) and all(p.exists() and digest(p)==sha for p in
            (local/'hd'/pack/source.replace('_frame_','_aframe_') for pack in ('topaz-cannon','topaz-crisp')))
        rows.append(dict(source=source,owner=owners.get(root),state=state,installed_matching_output=installed))
    value=dict(updated_at=time.time(),total_sources=len(rows),states=dict(Counter(r['state'] for r in rows)),
               installed_matching_outputs=sum(r['installed_matching_output'] for r in rows),assets=rows,
               note='Automated validation is not visual/animation approval. Manual replacements may supersede these hashes.')
    atomic(output/'batches/guybrush-all/status.json',value)
    return value


def remaining(budget, current_cost):
    return max(0, budget['ceiling'] - (current_cost - budget['initial_cost']))


def execute(max_credits, output=OUTPUT, local=ROOT/'.playtest'):
    if max_credits < 0:
        raise ValueError('Negative credit ceiling')
    folder=output/'batches/guybrush-all';marker=output/'stop-after-current'
    with ExitStack() as locks:
        for path in (output,output/'batches',folder):locks.enter_context(locked(path))
        membership=prepare(output);plan=read(output/'plan.json')
        grouped=defaultdict(list)
        for source,base in membership['owners'].items():grouped[base].append(source)
        for base in grouped:
            locks.enter_context(locked(output/base))
            scene=next((s for s in plan['scenes'] if s['id']==base),None)
            if scene:prepare_scene(output,scene,Path(plan['source_batch']))
        total_cost=lambda:sum(cost(output/b,ss) for b,ss in grouped.items())
        api=API(ROOT/'.context/secrets/topaz-api-key',4)
        budget=read(folder/'budget.json')
        if not budget:
            budget=dict(ceiling=min(max_credits,api.balance()),initial_cost=total_cost(),
                        membership_sha256=digest(folder/'plan.json'))
            atomic(folder/'budget.json',budget)
        if budget['membership_sha256']!=digest(folder/'plan.json'):
            raise ValueError('Budget membership changed')
        def progress(state,**details):
            atomic(folder/'progress.json',dict(state=state,pid=os.getpid(),updated_at=time.time(),
                ceiling=budget['ceiling'],credits=total_cost()-budget['initial_cost'],**details))
        # Main costume first even when its already-paid owner is elsewhere.
        ordered=sorted(grouped,key=lambda b:(not any(costume(s)==2 for s in grouped[b]),b))
        try:
            for base in ordered:
                sources=grouped[base]
                for offset in range(0,len(sources),100):
                    if marker.exists() or (folder/'stop-after-current').exists():progress('stopped');return
                    jobs=read(output/base/'jobs.json',{})
                    pending=[s for s in sources[offset:offset+100] if jobs.get(s,{}).get('state') not in TERMINAL]
                    if not pending:continue
                    left=remaining(budget,total_cost())
                    if left<1 and not any(jobs.get(s,{}).get('state')=='submitted' for s in pending):
                        progress('credit_cap');status(output,local);return
                    progress('running',owner=base,batch=offset//100+1)
                    run(output/base,api,left,sources=pending,concurrency=16,require_pilots=False,
                        stop_files=(marker,folder/'stop-after-current'),poll_timeout=300)
                    materialize(output,plan)
                    report=status(output,local)
                    print('GUYBRUSH CHECKPOINT',base,offset//100+1,report['states'],flush=True)
                    state=read(output/base/'progress.json')['state']
                    if state in ('credit_cap','stopped','interrupted','awaiting_provider'):
                        progress(state,owner=base);return
            progress('production_checkpoint');status(output,local)
        except Exception as error:
            progress('interrupted',error=str(error));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','status','run'))
    parser.add_argument('--max-credits',type=int,default=0)
    args=parser.parse_args()
    if args.command=='prepare':prepare();print(status()['states'])
    elif args.command=='status':print(status()['states'])
    else:execute(args.max_credits)
