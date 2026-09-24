#!/usr/bin/env python3
"""Install completed 4x Topaz drafts without changing artwork review status."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import struct
import tempfile
import time

from PIL import Image
from prepare_topaz import chunks
from quiver_cannon import atomic, locked
from topaz_character_cutouts import digest, load_jobs
from topaz_cannon_removebg import stopped
from topaz_scenes import OUTPUT, ROOT, SOURCE, read


def collect(output):
    plan=read(output/'plan.json'); batch=Path(plan['source_batch'])
    entries={e['source']:e for scene in plan['scenes'] for e in scene['sources']}
    records={}
    bases=[batch.parent/name for name in ('topaz-cannon-objectmatting','topaz-character-objectmatting','topaz-difficulty-knife')]
    bases += [output/scene['id'] for scene in plan['scenes']]
    # Explicit repair attempts supersede older provider outputs, including drafts.
    bases += sorted(p.parent for p in (output/'repairs').glob('*/attempt-*/jobs.json'))
    for base in bases:
        if not (base/'jobs.json').exists():continue
        for source,job in load_jobs(base).items():
            if source not in entries or entries[source]['operation'] in ('preserve','empty'):continue
            if not SOURCE.fullmatch(source):raise ValueError('Unsafe asset path')
            if job.get('state') not in ('validated','accepted','rejected'):continue
            master=base/'4x'/source; check=job.get('validation',{})
            if not master.exists() or not check.get('sha256'):continue
            if digest(master)!=check['sha256']:raise ValueError(f'Output changed: {source}')
            with Image.open(master) as im:
                if im.mode!='RGBA' or list(im.size)!=[v*4 for v in entries[source]['size']]:
                    raise ValueError(f'Invalid runtime canvas: {source}')
            records[source]=dict(master=str(master.resolve()),sha256=check['sha256'],state=job['state'],
                                 validation_passed=check.get('passed',False),derived=False)
    from asset_edits import overrides
    records.update(overrides(output, entries))
    # Preview derivatives may reuse rejected artwork; keep them separate from
    # validated derivatives and never change the main processing/review journals.
    pending=[e for e in entries.values() if e['operation'] in ('alias','derive-layer')]
    while pending:
        advanced=False
        for e in list(pending):
            if e['source'] in records:pending.remove(e);continue
            parent=records.get(e['parent'])
            if not parent:continue
            source=e['source'];master=output/'preview-derived/4x'/source
            master.parent.mkdir(parents=True,exist_ok=True)
            with Image.open(parent['master']) as im:
                if e['operation']=='alias':
                    if list(im.size)!=[v*4 for v in e['size']]:raise ValueError('Alias size mismatch')
                    shutil.copy2(parent['master'],master)
                else:
                    layer=Image.new('RGBA',tuple(v*4 for v in e['size']))
                    layer.paste(im,tuple(v*4 for v in e['offset']));layer.save(master)
            records[source]=dict(master=str(master.resolve()),sha256=digest(master),state='draft-derived',
                                 validation_passed=parent['validation_passed'],derived=True,parent=e['parent'])
            pending.remove(e);advanced=True
        if not advanced:break
    return plan,records


def install(output,local):
    stopped(local)
    with locked(local/'draft-install'):
        plan,records=collect(output)
        batch=Path(plan['source_batch']);mapping_path=local/'hd/object_map.json'
        mapping=read(mapping_path,{})
        object_records=[s for s in records if s.startswith('objects/')]
        ids={}
        if object_records:
            payload=next(p for t,_,p in chunks((local/'game/COMI.LA0').read_bytes()) if t=='DOBJ')
            for number in range(struct.unpack_from('<I',payload)[0]):
                name=payload[4+number*46:44+number*46].split(b'\0')[0].decode()
                if name:ids.setdefault(name,[]).append(number)
        for source in object_records:
            room,name,state=Path(source).stem.split('_',2)
            if len(ids.get(name,[]))!=1:raise ValueError(f'Ambiguous object ID: {source}')
            entry=mapping.setdefault(str(ids[name][0]),dict(name=name,rooms={}))
            item=entry['rooms'].setdefault(str(int(room)),dict(states=[]))
            item['states']=sorted(set(item['states']+[int(state)]))
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup=local/'backups'/f'asset-drafts-{stamp}'
        policy_path=batch/'protected-cutouts.json';policy=read(policy_path,{})
        manifest_records={r['source']:r for r in read(batch/'manifest.json')['records']}
        from topaz_batch import job_key
        changed=set();receipt=[]
        with tempfile.TemporaryDirectory(dir=local) as temporary:
            staged=[]
            for source,record in records.items():
                master=Path(record['master'])
                targets=[batch/'4x'/source]
                targets += ([local/'hd'/pack/source.replace('_frame_','_aframe_') for pack in ('topaz-cannon','topaz-crisp')]
                            if source.startswith('costumes/') else [local/'hd'/source])
                for target in targets:
                    receipt.append(dict(source=source,target=str(target.resolve()),sha256=record['sha256']))
                    if target.exists() and digest(target)==record['sha256']:continue
                    # Backups use labeled paths, without assuming custom output/local roots share a parent.
                    relative=(Path('asset-tool')/target.relative_to(batch)) if target.is_relative_to(batch) else Path('runtime')/target.relative_to(local)
                    previous=backup/relative
                    if target.exists():
                        previous.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,previous)
                    stage=Path(temporary)/str(len(staged));shutil.copy2(master,stage)
                    if digest(stage)!=record['sha256']:raise ValueError('Draft changed while staging')
                    staged.append((stage,target));changed.add(source)
                policy[f'4:{source}']=dict(file=record['master'],sha256=record['sha256'],
                    upscale_job_key=job_key(manifest_records[source],4),provenance=dict(draft=True,validation_passed=record['validation_passed']))
            for label,path in [('protected-cutouts.json',policy_path),('object_map.json',mapping_path)]:
                if path.exists():
                    backup.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup/label)
            stopped(local)
            for stage,target in staged:
                target.parent.mkdir(parents=True,exist_ok=True);stage.replace(target)
        atomic(mapping_path,mapping);atomic(policy_path,policy)
        for item in receipt:
            if digest(Path(item['target']))!=item['sha256']:raise ValueError('Installed draft verification failed')
        result=dict(installed_at=time.time(),scale=4,new_or_changed=len(changed),total=len(records),
                    changed_sources=sorted(changed),assets=records,files=receipt,backup=str(backup.resolve()),
                    reviewed=False,notes='User requested all completed drafts; artwork approvals remain unchanged.')
        atomic(backup/'receipt.json',result);atomic(local/'draft-install/receipt.json',result)
        print(f"Installed {len(changed)} new/changed drafts; {len(records)} total asset hashes verified. Backup: {backup}")
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--local',type=Path,default=ROOT/'.playtest')
    args=p.parse_args();install(args.output,args.local)


if __name__=='__main__':main()
