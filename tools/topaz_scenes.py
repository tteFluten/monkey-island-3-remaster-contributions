#!/usr/bin/env python3
"""Plan and process scene batches with global deduplication and a fixed credit ceiling.

Preparation is local. Processing preserves all provider outputs; publication into
runtime packs remains a separate visual review/install operation.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import time

from PIL import Image
from quiver_cannon import atomic, locked
from topaz_batch import API, SETTINGS, job_key
from topaz_cannon_removebg import SETTINGS as MATTING
from topaz_cannon_removebg import stopped
from prepare_topaz import chunks
from topaz_character_cutouts import digest, load_jobs, run

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'output/topaz-scenes'
BATCH = ROOT/'output/topaz-batch'
EXISTING = ('topaz-cannon-objectmatting', 'topaz-character-objectmatting',
            'topaz-difficulty-knife', 'topaz-ui-objectmatting')
SOURCE = re.compile(r'(costumes|objects|objects_layers)/[A-Za-z0-9_-]+\.png')


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def room_of(source):
    return int(re.search(r'/(?:LFLF_)?(\d+)_', source)[1])


def natural(source):
    return [int(v) if v.isdigit() else v for v in re.split(r'(\d+)', source)]


def existing_owners(batch):
    owners = {}
    for directory in EXISTING:
        base = batch.parent/directory
        for r in read(base/'manifest.json', {}).get('records', []):
            owners[r['source']] = directory
    return owners


def prepare(output=OUTPUT, batch=BATCH):
    manifest = read(batch/'manifest.json')
    records = {r['source']: r for r in manifest['records']}
    if any(not SOURCE.fullmatch(s) for s in records): raise ValueError('Unsafe prepared source')
    owners = existing_owners(batch)
    cannon = set()
    for filename in ('cannon-character-scope.json', 'idle-walk-scope.json'):
        cannon.update(read(batch/filename, {}).get('sources', []))
    cannon.update(s for s in records if room_of(s) == 9)
    groups = {}
    for source in records:
        room = 9 if source in cannon else room_of(source)
        groups.setdefault(room, []).append(source)
    # Resource room numbers are stable, but are not a linear puzzle walkthrough.
    # First finish the selected cannon scene, then the separately requested knife.
    order = [r for r in (9, 87) if r in groups]
    order += sorted(r for r in groups if r >= 10 and r not in order)
    order += sorted(r for r in groups if r not in order)
    names = {int(p.stem.split('_')[0]): p.stem.split('_',1)[1]
             for p in (ROOT/'extracted/backgrounds').glob('*.png')}
    chosen = {}
    # Prefer already-paid/reserved inputs even if their resource lives later.
    for source in owners:
        if source in records: chosen.setdefault(records[source]['cleaned_sha256'], source)
    scenes = []
    for number in order:
        entries = []
        for source in sorted(groups[number], key=natural):
            r = records[source]
            entry = dict(source=source, resource_room=room_of(source), size=r['size'],
                         cleaned_sha256=r['cleaned_sha256'])
            if number == 87 and not re.fullmatch(r'costumes/LFLF_0087_AKOS_0439_frame_[0-3]\.png', source):
                entry.update(operation='preserve', reason='Difficulty screen: knife only; existing artwork stays intact')
            elif 'derived_from' in r:
                if r['derived_from'] not in records: raise ValueError('Missing layer parent')
                entry.update(operation='derive-layer', parent=r['derived_from'], offset=r['offset'])
            else:
                canonical = chosen.setdefault(r['cleaned_sha256'], source)
                if source != canonical:
                    entry.update(operation='alias', parent=canonical)
                elif source in owners:
                    entry.update(operation='existing', owner=owners[source])
                else:
                    with Image.open(batch/'cleaned'/source) as im:
                        extrema = im.convert('RGBA').getchannel('A').getextrema()
                    if extrema[1] == 0: entry.update(operation='empty')
                    elif max(r['size']) < 24:
                        entry.update(operation='review-small', reason='Needs a padded-input pilot before paid processing')
                    else: entry.update(operation='upscale-only' if extrema[0] == 255 else 'upscale-matting')
                    if entry['operation'] in ('upscale-only', 'upscale-matting'):
                        entry['cached_scale'] = next((scale for scale in (4,6)
                            if (batch/'raw'/(job_key(r,scale)+'.png')).exists()), None)
            entries.append(entry)
        counts = Counter(e['operation'] for e in entries)
        # Counts, not a quote: API estimates are checked before every submission.
        minimum = sum((0 if e.get('cached_scale') else 1) + (e['operation']=='upscale-matting')
                      for e in entries if e['operation'] in ('upscale-only','upscale-matting'))
        scenes.append(dict(id=f'room-{number:04}', room=number, name=names.get(number, 'shared-assets'),
                           sources=entries, counts=dict(counts), minimum_new_credits=minimum))
    value = dict(version=1, scale=4, settings=SETTINGS, matting_settings=MATTING,
        source_batch=str(batch.resolve()), source_manifest_sha256=digest(batch/'manifest.json'),
        prepared_at=time.time(), spending='available balance only; never purchase credits',
        order_basis='Cannon first, difficulty knife next, then resource rooms in numeric order; shared resources last',
        original_pixels_restored=False, original_mask_applied=False,
        total_sources=len(records), scenes=scenes,
        previous_crisp_sources=sorted(('costumes/'+p.name for p in (batch/'6x-crisp/costumes').glob('*.png')), key=natural))
    old = read(output/'plan.json')
    if old and read(output/'progress.json',{}).get('state') == 'running':
        raise ValueError('Do not replace a running scene plan')
    atomic(output/'plan.json', value)
    lines = ['# Scene batch plan', '', '4× Wonder 3.5 High → Topaz Object Matting for transparent sprites. '
             'Solid artwork stays solid. No original edge pixels or alpha masks are restored.', '',
             'Cannon first, then the difficulty knife. Remaining rooms use resource-number order, '
             'not an inferred story progression. Shared frames are paid for once. Backgrounds are excluded.', '',
             '| Room | Resource | Files | New inputs | Cached raw | Reused / reserved | Layers | Small pilots | Minimum new credits* |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in scenes:
        c=s['counts']; active=[e for e in s['sources'] if e['operation'] in ('upscale-only','upscale-matting')]
        lines.append(f"| {s['room']} | {s['name']} | {len(s['sources'])} | {len(active)} | {sum(bool(e.get('cached_scale')) for e in active)} | {c.get('existing',0)+c.get('alias',0)} | {c.get('derive-layer',0)} | {c.get('review-small',0)} | {s['minimum_new_credits']} |")
    lines += ['', '*Planning lower bounds only: excludes existing in-flight work and small pilots. '
              'Live API estimates govern spending. Outputs must pass visual review before game installation.', '']
    (output/'plan.md').write_text('\n'.join(lines))
    print(json.dumps(dict(files=len(records), scenes=len(scenes), counts=dict(Counter(e['operation'] for s in scenes for e in s['sources'])),
                          minimum_new_credits=sum(s['minimum_new_credits'] for s in scenes))))
    return value


def prepare_scene(output, scene, batch):
    base=output/scene['id']; path=base/'manifest.json'
    if path.exists(): return base
    originals={r['source']:r for r in read(batch/'manifest.json')['records']}
    records=[]
    for entry in scene['sources']:
        if entry['operation'] not in ('upscale-only','upscale-matting'): continue
        source=entry['source']; r=originals[source]; clean=batch/'cleaned'/source
        if digest(clean)!=entry['cleaned_sha256']: raise ValueError('Prepared source changed')
        raw=base/'raw'/source; cached=None
        for scale in (4,6):
            candidate=batch/'raw'/(job_key(r,scale)+'.png')
            if not candidate.exists(): continue
            raw.parent.mkdir(parents=True,exist_ok=True)
            with Image.open(candidate) as im:
                if list(im.size)!=[v*scale for v in r['size']]: raise ValueError('Invalid cached dimensions')
                im.convert('RGB').resize(tuple(v*4 for v in r['size']),Image.Resampling.LANCZOS).save(raw)
            cached=dict(path=str(candidate.resolve()),scale=scale,sha256=digest(candidate));break
        records.append(dict(source=source,original_size=r['size'],size=[v*4 for v in r['size']],
            raw=str(raw.resolve()),raw_sha256=digest(raw) if raw.exists() else None,
            cleaned_sha256=r['cleaned_sha256'],cached=cached,operation=entry['operation']))
    atomic(path,dict(kind='scene',room=scene['room'],scale=4,source_batch=str(batch.resolve()),
                    settings=MATTING,upscale_settings=SETTINGS,records=records))
    return base


def journal_cost(base):
    return sum(h['estimate']['credits'] for j in read(base/'jobs.json',{}).values() for h in j.get('history',[]))


def materialize(output, plan):
    """Reuse completed pixels for duplicates and positioned layers; no API calls."""
    batch=Path(plan['source_batch']); found={}; base=output/'derived'
    journal=read(base/'jobs.json',{})
    for directory in [batch.parent/d for d in EXISTING]+[output/s['id'] for s in plan['scenes']]:
        if not (directory/'jobs.json').exists():continue
        for source,job in load_jobs(directory).items():
            if job.get('state') in ('accepted','validated') and job.get('validation',{}).get('passed'):
                found[source]=(directory/'4x'/source,job['validation']['sha256'])
    pending=[e for s in plan['scenes'] for e in s['sources'] if e['operation'] in ('alias','derive-layer','empty')]
    while pending:
        advanced=False
        for e in list(pending):
            parent=found.get(e.get('parent'))
            if e['operation']!='empty' and not parent:continue
            target=base/'4x'/e['source']; previous=journal.get(e['source'],{})
            parent_sha=parent[1] if parent else None
            if previous.get('parent_sha256')==parent_sha and target.exists() and digest(target)==previous.get('validation',{}).get('sha256'):
                found[e['source']]=(target,previous['validation']['sha256']);pending.remove(e);advanced=True;continue
            target.parent.mkdir(parents=True,exist_ok=True)
            if parent and digest(parent[0])!=parent_sha:raise ValueError('Completed parent changed')
            if e['operation']=='alias':shutil.copy2(parent[0],target)
            else:
                image=Image.new('RGBA',tuple(v*4 for v in e['size']))
                if parent:
                    with Image.open(parent[0]) as obj:image.paste(obj,tuple(v*4 for v in e['offset']))
                image.save(target)
            sha=digest(target)
            journal[e['source']]=dict(state='validated',parent_sha256=parent_sha,
                validation=dict(passed=True,sha256=sha,size=[v*4 for v in e['size']],
                                cleanup=dict(type=e['operation'],original_pixels_restored=False)))
            found[e['source']]=(target,sha);pending.remove(e);advanced=True
        if not advanced:break
    for e in pending:
        if e['source'] in journal:
            journal[e['source']].update(state='blocked_parent')
    atomic(base/'jobs.json',journal)


def completed(output, plan):
    batch=Path(plan['source_batch']); result={}
    for base in [batch.parent/d for d in EXISTING]+[output/s['id'] for s in plan['scenes']]+[output/'derived']:
        if not (base/'jobs.json').exists():continue
        for source,job in load_jobs(base).items():
            if not SOURCE.fullmatch(source):raise ValueError('Unsafe completed source')
            if job.get('state') not in ('accepted','validated') or not job.get('validation',{}).get('passed'):continue
            master=base/'4x'/source;sha=job['validation']['sha256']
            review=read(base/'reviews'/(source+'.json'),{})
            result[source]=dict(master=master,sha256=sha,
                parent_sha256=job.get('parent_sha256'),
                reviewed=job['state']=='accepted' or review.get('sha256')==sha)
    return result


def review_scene(output, sources):
    plan=read(output/'plan.json'); files=completed(output,plan)
    if not sources:raise ValueError('Select the frames actually viewed')
    allowed={e['source'] for s in plan['scenes'] for e in s['sources'] if e['operation']!='preserve'}
    for source in sources:
        if source not in allowed or source not in files:raise ValueError('Not a validated planned output')
        f=files[source]
        if digest(f['master'])!=f['sha256']:raise ValueError('Output changed after validation')
        atomic(output/'reviews'/(source+'.json'),dict(sha256=f['sha256'],reviewed_at=time.time()))


def install_scene(output, room, local, completed_only=False):
    """Publish reviewed room-9/knife art; other renderer rooms need in-game validation."""
    stopped(local)
    if room not in (9,87):raise ValueError('Enable and verify this room in the native renderer before installation')
    plan=read(output/'plan.json');batch=Path(plan['source_batch'])
    scene=next(s for s in plan['scenes'] if s['room']==room); files=completed(output,plan)
    entries={e['source']:e for s in plan['scenes'] for e in s['sources']}
    def approved(source,trail=()):
        if source in trail:raise ValueError('Cyclic approval dependency')
        if source not in files:return False
        f=files[source];record=read(output/'reviews'/(source+'.json'),{})
        if f['reviewed'] or record.get('sha256')==f['sha256']:return True
        e=entries[source]
        return (e['operation'] in ('alias','derive-layer') and e['parent'] in files
                and f['parent_sha256']==files[e['parent']]['sha256'] and approved(e['parent'],trail+(source,)))
    selected=[]
    for e in scene['sources']:
        if e['operation'] in ('preserve','empty'):continue
        source=e['source']
        if not approved(source):
            if completed_only:continue
            raise ValueError(f'Review this output before completing the scene: {source}')
        f=files[source]
        if digest(f['master'])!=f['sha256']:raise ValueError('Reviewed output changed')
        with Image.open(f['master']) as im:
            if im.mode!='RGBA' or list(im.size)!=[v*4 for v in e['size']]:raise ValueError('Wrong runtime dimensions')
        selected.append(e)
    if not selected:raise ValueError('No reviewed scene outputs')
    mapping_path=local/'hd/object_map.json';mapping=read(mapping_path,{})
    ids={}
    if any(e['source'].startswith('objects/') for e in selected):
        index=next(p for t,_,p in chunks((local/'game/COMI.LA0').read_bytes()) if t=='DOBJ')
        for number in range(struct.unpack_from('<I',index)[0]):
            name=index[4+number*46:44+number*46].split(b'\0')[0].decode()
            if name:ids.setdefault(name,[]).append(number)
    originals={r['source']:r for r in read(batch/'manifest.json')['records']}
    policy=read(batch/'protected-cutouts.json',{});receipt=[];pending=[]
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        for e in selected:
            source=e['source'];f=files[source]
            targets=[('asset-tool',batch/'4x'/source)]
            if source.startswith('costumes/'):
                targets += [(pack,local/'hd'/pack/source.replace('_frame_','_aframe_')) for pack in ('topaz-cannon','topaz-crisp')]
            else:targets.append(('runtime',local/'hd'/source))
            if source.startswith('objects/'):
                room_text,name,state=Path(source).stem.split('_',2)
                if len(ids.get(name,[]))!=1:raise ValueError(f'Ambiguous object ID: {name}')
                entry=mapping.setdefault(str(ids[name][0]),dict(name=name,rooms={}))
                states=entry['rooms'].setdefault(str(int(room_text)),dict(states=[]))['states']
                entry['rooms'][str(int(room_text))]['states']=sorted(set(states+[int(state)]))
            for label,target in targets:
                backup=output/'previous'/label/source
                if target.exists() and not backup.exists():
                    backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
                staged=Path(temporary)/str(len(pending));shutil.copy2(f['master'],staged);pending.append((staged,target))
                receipt.append(dict(source=source,target=str(target.resolve()),sha256=f['sha256']))
            policy[f'4:{source}']=dict(file=str(f['master'].resolve()),sha256=f['sha256'],
                upscale_job_key=job_key(originals[source],4),provenance=dict(scene=scene['id']))
        for staged,target in pending:
            target.parent.mkdir(parents=True,exist_ok=True);staged.replace(target)
    atomic(mapping_path,mapping);atomic(batch/'protected-cutouts.json',policy)
    atomic(output/scene['id']/'installation.json',dict(installed_at=time.time(),scale=4,files=receipt))
    print(f'Installed {len(selected)} reviewed scene assets; backgrounds preserved.')


def active_character():
    progress=read(BATCH.parent/'topaz-character-objectmatting/progress.json',{})
    if progress.get('state')!='running': return False
    try: os.kill(progress['pid'],0); return True
    except ProcessLookupError:return False


def status(output, plan):
    batch=Path(plan['source_batch']); lookup={}
    bases=[batch.parent/d for d in EXISTING]+[output/s['id'] for s in plan['scenes']]+[output/'derived']
    for base in bases:
        if not (base/'jobs.json').exists():continue
        for source,job in load_jobs(base).items():
            if job.get('state') in ('accepted','validated') and job.get('validation',{}).get('passed'):
                lookup[source]=dict(base=base,job=job)
    reports=[]
    all_entries={e['source']:e for s in plan['scenes'] for e in s['sources']}
    def resolved(source,trail=()):
        if source in trail:raise ValueError('Cyclic source dependency')
        if source in lookup:return True
        e=all_entries[source]
        if e['operation'] in ('empty','preserve'):return True
        if e['operation'] in ('alias','derive-layer'):return False
        return False
    for scene in plan['scenes']:
        counts=Counter(e['operation'] for e in scene['sources'])
        jobs=read(output/scene['id']/'jobs.json',{})
        reports.append(dict(id=scene['id'],room=scene['room'],name=scene['name'],total=len(scene['sources']),
            ready=sum(resolved(e['source']) for e in scene['sources']),
            needs_pilot=counts.get('review-small',0),preserved=counts.get('preserve',0),
            rejected=sum(j.get('state') in ('rejected','failed','unknown','submitting') for j in jobs.values()),
            minimum_new_credits=scene['minimum_new_credits']))
    atomic(output/'status.json',dict(updated_at=time.time(),total=plan['total_sources'],scenes=reports))
    return reports


def process(output, api, max_credits):
    plan=read(output/'plan.json');batch=Path(plan['source_batch'])
    if digest(batch/'manifest.json')!=plan['source_manifest_sha256']:raise ValueError('Rebuild scene plan after input changes')
    ceiling=min(max_credits,api.balance());spent=0
    def progress(state,current=None):
        atomic(output/'progress.json',dict(state=state,pid=os.getpid(),updated_at=time.time(),
            current_scene=current,submitted_credits=spent,credit_cap=ceiling))
        status(output,plan)
    progress('waiting_for_characters')
    while active_character():
        if (output/'stop-after-current').exists():progress('stopped');return
        time.sleep(20);progress('waiting_for_characters')
    # Finish the already approved character scope before new scene work. Their
    # saved IDs resume and are never purchased again. The fixed ceiling includes
    # these additional submissions, but not the prior worker's recorded spend.
    tasks=[('characters',batch.parent/'topaz-character-objectmatting',())]
    priority=set(plan.get('previous_crisp_sources',[]))
    # Complete the first scene and knife, then convert every previously generated
    # crisp asset before spending on unrelated new frames in later scenes.
    for scene in plan['scenes']:
        if scene['room'] in (9,87):
            if scene['room']==87:tasks.append(('difficulty-knife',batch.parent/'topaz-difficulty-knife',()))
            tasks.append((scene['id'],prepare_scene(output,scene,batch),()))
    for scene in plan['scenes']:
        if scene['room'] in (9,87):continue
        selected=[e['source'] for e in scene['sources'] if e['source'] in priority and e['operation'] in ('upscale-only','upscale-matting')]
        if selected:tasks.append((scene['id'],prepare_scene(output,scene,batch),selected))
    for scene in plan['scenes']:
        if scene['room'] not in (9,87):tasks.append((scene['id'],prepare_scene(output,scene,batch),()))
    try:
        for name,base,sources in tasks:
            if (output/'stop-after-current').exists():progress('stopped',name);return
            manifest=read(base/'manifest.json',{})
            if not manifest.get('records'):continue
            before=journal_cost(base);progress('running',name)
            with locked(base):
                run(base,api,max(0,ceiling-spent),sources=sources,concurrency=4,require_pilots=False,
                    stop_files=(output/'stop-after-current',))
            spent+=journal_cost(base)-before
            before=journal_cost(base)
            materialize(output,plan)
            jobs=read(base/'jobs.json',{})
            if any(j.get('state') in ('unknown','submitting') for j in jobs.values()):
                progress('needs_submission_review',name);return
            current=read(base/'progress.json',{})
            if current.get('state')=='credit_cap':progress('credit_cap',name);return
            if current.get('state')=='stopped':progress('stopped',name);return
            progress('running',name)
        unresolved=any(j.get('state')=='submitted' for _,base,_ in tasks for j in read(base/'jobs.json',{}).values())
        progress('awaiting_provider' if unresolved else 'awaiting_review')
    except Exception:
        if 'base' in locals():spent+=max(0,journal_cost(base)-before)
        progress('interrupted',locals().get('name'));raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('prepare','run','status','review','install'))
    p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--batch',type=Path,default=BATCH)
    p.add_argument('--max-credits',type=int,default=0)
    p.add_argument('--room',type=int,default=9)
    p.add_argument('--source',action='append',default=[])
    p.add_argument('--local',type=Path,default=ROOT/'.playtest')
    p.add_argument('--completed-only',action='store_true')
    args=p.parse_args()
    if args.command=='run':
        p.error('Automatic scene advancement is disabled. Use tools/asset_batches.py run --batch-id ID --max-credits N')
    if args.command=='status':print(json.dumps(status(args.output,read(args.output/'plan.json')),indent=2));return
    if args.command=='review':return review_scene(args.output,args.source)
    if args.command=='install':return install_scene(args.output,args.room,args.local,args.completed_only)
    with locked(args.output):
        if args.command=='prepare':prepare(args.output,args.batch)
        else:
            if args.max_credits<0:p.error('Credits must be nonnegative')
            process(args.output,API(ROOT/'.context/secrets/topaz-api-key',4),args.max_credits)


if __name__=='__main__':main()
