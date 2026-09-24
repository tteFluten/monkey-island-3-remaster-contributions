#!/usr/bin/env python3
"""Prepare cannon-room standing/walking cels for Topaz; no paid requests."""
import hashlib
import json
import shutil
from pathlib import Path

from costume_sequences import cels
from quiver_extract import extract, resources


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root=Path('output/topaz-batch'), game=Path('.playtest/game')):
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    records = {r['source']: r for r in manifest['records']}
    selected = []
    sequences = {}
    # Chores from live actor diagnostics: Guybrush walk=2, stand=3.
    # Wally stays in place; these body/head poses are used by his idle scripts.
    # Talk-stop sets the head separately from the standing body. Wally's normal
    # post-intro standing chore is 6; its head can retain chore 9 or 10.
    chores = {2: [2, 3, 5], 25: [6, 9, 10, 15, 19, 22, 31, 32]}
    extraction = root / 'extracted-idle'
    extract(game, extraction, [25])
    unique = {r['cleaned_sha256']: r['canonical'] for r in records.values() if 'canonical' in r}
    for cid, room, raw, fields, _ in resources(game, chores):
        for chore in chores[cid]:
            frames, _ = cels(fields, chore)
            sequences[f'{cid}:{chore}'] = frames
            for cel in frames:
                name = f'LFLF_{room:04d}_AKOS_{cid:04d}_frame_{cel}.png'
                source = 'costumes/' + name
                selected.append(source)
                if source in records:
                    continue
                indexed = extraction / 'indexed' / name
                clean = extraction / 'cleaned' / name
                target = root / 'cleaned' / source
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(clean, target)
                from PIL import Image
                with Image.open(clean) as image:
                    size = list(image.size)
                record = {'source': source, 'source_file': str(indexed.resolve()),
                          'source_sha256': digest(indexed), 'size': size,
                          'cleaned_sha256': digest(target), 'origin': 'local-game-extraction',
                          'game_resource_sha256': hashlib.sha256(raw).hexdigest()}
                record['canonical'] = unique.setdefault(record['cleaned_sha256'], source)
                records[source] = record
                manifest['records'].append(record)
    selected = sorted(set(selected))
    canonical = sorted({records[s]['canonical'] for s in selected}, key=lambda s: (int(s.split('_AKOS_')[1].split('_')[0]), int(s.rsplit('_', 1)[1][:-4])))
    temporary = manifest_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(manifest, indent=2))
    temporary.replace(manifest_path)
    (root / 'idle-walk-selection.json').write_text(json.dumps(canonical, indent=2))
    (root / 'idle-walk-scope.json').write_text(json.dumps({'room': 9, 'sources': selected,
        'sequences': sequences, 'note': 'Guybrush eight-direction standing/walking; Wally standing body/head poses. Not the complete dialogue/action library.'}, indent=2))
    print(f'Prepared {len(selected)} cels, {len(canonical)} canonical inputs; existing results will be reused.')


if __name__ == '__main__':
    prepare()
