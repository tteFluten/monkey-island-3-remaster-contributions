#!/usr/bin/env python3
"""Package installed Topaz drafts and their references without changing reviews."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import shutil

from PIL import Image
from quiver_cannon import atomic, locked
from topaz_character_cutouts import digest
from topaz_scenes import ROOT, read


def package(root=ROOT):
    with locked(root/'.context/topaz-packaging'), locked(root/'.playtest/draft-install'):
        manifest = read(root/'assets/manifest.json')
        index = {r['path']: r for r in manifest['files']}
        assets = read(root/'.playtest/draft-install/receipt.json')['assets']
        reviews = read(root/'assets/metadata/artwork-review.json')
        library = read(root/'assets/metadata/topaz-library.json')
        known = {r['source'] for r in library['records']}
        records = {r['source']: r for r in read(root/'output/topaz-batch/manifest.json')['records']}
        scene_plan = read(root/'assets/metadata/topaz-scene-plan.json')
        full_plan = read(root/'output/topaz-scenes/plan.json')
        changed = []

        def register(name, origin, category, source, state, destination, **extra):
            target = root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            checksum = digest(origin)
            if not target.exists() or digest(target) != checksum:
                shutil.copy2(origin, target)
            with Image.open(target) as image:
                image.load()
                dimensions = dict(width=image.width, height=image.height, mode=image.mode)
            row = dict(path=name, sha256=checksum, bytes=target.stat().st_size,
                       category=category, source_id=source, review_status=state,
                       destination=destination, image=dimensions, **extra)
            if name in index:index[name].update(row)
            else:manifest['files'].append(row);index[name]=row

        # Validate inputs and installed copies before changing any packaged file.
        candidates = []
        for source, asset in sorted(assets.items()):
            name = 'assets/masters/topaz-4x/' + source
            existing = index.get(name)
            # Manual UI masters are already canonical under another category.
            if not existing:
                existing = next((r for r in manifest['files'] if r.get('canonical') and
                    r.get('destination') == 'output/topaz-batch/4x/'+source), None)
            if existing and existing['sha256'] == asset['sha256']:
                continue
            if existing:name=existing['path']
            original = Path(asset['master'])
            if digest(original) != asset['sha256']:
                raise ValueError('Draft master changed: '+source)
            runtime = ([f'{pack}/{source.replace("_frame_", "_aframe_")}'
                        for pack in ('topaz-cannon','topaz-crisp')]
                       if source.startswith('costumes/') else [source])
            for path in runtime:
                if digest(root/'.playtest/hd'/path) != asset['sha256']:
                    raise ValueError('Install draft before packaging: '+source)
            clean = root/'output/topaz-batch/cleaned'/source
            if digest(clean) != records[source]['cleaned_sha256']:
                raise ValueError('Cleaned reference changed: '+source)
            candidates.append((source,asset,name,original,runtime,clean,existing))

        for source,asset,name,original,runtime,clean,existing in candidates:
            changed.append(source)
            category = existing['category'] if existing else 'masters/topaz-4x'
            register(name,original,category,source,asset['state'],
                     'output/topaz-batch/4x/'+source,canonical=True)
            for path in runtime:
                register('assets/runtime/'+path,root/'.playtest/hd'/path,
                         'runtime/'+path.split('/')[0],source,asset['state'],'.playtest/hd/'+path,
                         derived_from=name,transform=dict(kind='copy',source_sha256=asset['sha256']))
            register('assets/references/topaz-cleaned/'+source,clean,
                     'references/topaz-cleaned',source,'original-reference',
                     'output/topaz-batch/cleaned/'+source)
            reviews[source] = dict(asset,master='source:albuquerque/'+original.relative_to(root).as_posix())
            if source not in known:
                library['records'].append(records[source]);known.add(source)

        library['records'].sort(key=lambda r:r['source'])
        selected = {e['source'] for s in scene_plan['scenes'] for e in s['sources']} | set(assets)
        for scene in scene_plan['scenes']:
            full = next(s for s in full_plan['scenes'] if s['id']==scene['id'])
            scene['sources'] = [e for e in full['sources'] if e['source'] in selected]
        scene_plan['total_sources'] = sum(len(s['sources']) for s in scene_plan['scenes'])
        for name,value in [('artwork-review.json',reviews),('topaz-library.json',library),
                           ('topaz-scene-plan.json',scene_plan)]:
            path = 'assets/metadata/'+name
            atomic(root/path,value)
            index[path].update(sha256=digest(root/path),bytes=(root/path).stat().st_size)
        mapping = 'assets/runtime/object_map.json'
        shutil.copy2(root/'.playtest/hd/object_map.json',root/mapping)
        index[mapping].update(sha256=digest(root/mapping),bytes=(root/mapping).stat().st_size)
        categories=defaultdict(lambda:dict(files=0,bytes=0));unique={}
        for row in manifest['files']:
            categories[row['category']]['files']+=1
            categories[row['category']]['bytes']+=row['bytes']
            unique[row['sha256']]=row['bytes']
        manifest.update(categories=dict(categories),logical_bytes=sum(r['bytes'] for r in manifest['files']),
                        unique_bytes=sum(unique.values()),updated_at=datetime.now(timezone.utc).isoformat())
        atomic(root/'assets/manifest.json',manifest)
        summary=dict(new_assets=len(changed),total_selected_sources=len(selected),
                     manifest_entries=len(manifest['files']),
                     new_states=dict(Counter(assets[s]['state'] for s in changed)))
        atomic(root/'.context/topaz-package-summary.json',summary)
        return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    print(package(parser.parse_args().root))
