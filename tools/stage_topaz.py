#!/usr/bin/env python3
"""Stage a completed Topaz scene for the 4x COMI-HD engine, preserving masters."""
import argparse
import hashlib
import json
import os
import re
import struct
import tempfile
from pathlib import Path

from PIL import Image
from prepare_topaz import chunks


def stage(batch, local, scope_file, crisp=False, report_name=None):
    report_name = report_name or ('topaz-crisp-staging.json' if crisp else 'topaz-staging.json')
    if report_name not in ('topaz-crisp-staging.json', 'topaz-staging.json', 'ui-staging.json'):
        raise ValueError('Invalid staging report name')
    process = local / 'process.json'
    if process.exists():
        pid = json.loads(process.read_text())['pid']
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Stop the game before staging its textures')
    scope = json.loads(scope_file.read_text())['sources']
    records = {r['source']: r for r in json.loads((batch / 'manifest.json').read_text())['records']}
    if not scope or any(s not in records for s in scope):
        raise ValueError('Scene scope must contain prepared source names')
    for source in scope:
        if not re.fullmatch(r'(costumes|objects|objects_layers)/[A-Za-z0-9_-]+\.png', source):
            raise ValueError('Invalid source name')
        if not (batch / '6x' / source).is_file():
            raise ValueError(f'Complete the batch first: {source}')
    # The scene pack uses exact cel matching: missing poses fall back to native.
    sources = set(scope)
    hd = local / 'hd'
    hd.mkdir(parents=True, exist_ok=True)
    map_path = hd / 'object_map.json'
    mapping = json.loads(map_path.read_text()) if map_path.exists() else {}
    index = next(payload for tag, _, payload in chunks((local / 'game/COMI.LA0').read_bytes()) if tag == 'DOBJ')
    count = struct.unpack_from('<I', index)[0]
    ids = {}
    for number in range(count):
        name = index[4 + number * 46:44 + number * 46].split(b'\0')[0].decode()
        if name:
            ids.setdefault(name, []).append(number)
    report = {'scale': 4, 'scope': str(scope_file), 'files': []}
    with tempfile.TemporaryDirectory(dir=local, prefix='stage-topaz-') as temporary:
        temporary = Path(temporary)
        for source in sorted(sources):
            record = records[source]
            enhanced = batch / ('6x-crisp' if crisp and source.startswith('costumes/') else '6x') / source
            if crisp and source.startswith('costumes/') and not enhanced.exists():
                raise ValueError(f'Generate the crisp-border variant first: {source}')
            master = enhanced if enhanced.exists() else batch / 'cleaned' / source
            target = ('topaz-crisp/' if crisp else 'topaz-cannon/') + source.replace('_frame_', '_aframe_') if source.startswith('costumes/') else source
            size = tuple(v * 4 for v in record['size'])
            with Image.open(master) as image:
                expected = tuple(v * (6 if enhanced.exists() else 1) for v in record['size'])
                if image.mode != 'RGBA' or image.size != expected:
                    raise ValueError(f'Invalid master dimensions or transparency: {source}')
                output = temporary / target
                output.parent.mkdir(parents=True, exist_ok=True)
                image.resize(size, Image.Resampling.LANCZOS if enhanced.exists() else Image.Resampling.NEAREST).save(output)
            if source.startswith('objects/'):
                room, name, state = Path(source).stem.split('_', 2)
                if len(ids.get(name, [])) != 1:
                    raise ValueError(f'Ambiguous game object ID: {name}')
                entry = mapping.setdefault(str(ids[name][0]), {'name': name, 'rooms': {}})
                states = entry['rooms'].setdefault(str(int(room)), {'states': []})['states']
                entry['rooms'][str(int(room))]['states'] = sorted(set(states + [int(state)]))
            report['files'].append({'source': source, 'target': target, 'size': size,
                                    'enhanced': enhanced.exists(),
                                    'master_sha256': hashlib.sha256(master.read_bytes()).hexdigest()})
        (temporary / 'object_map.json').write_text(json.dumps(mapping, indent=2))
        # All inputs are validated and converted before publishing any files.
        for entry in report['files']:
            target = hd / entry['target']
            target.parent.mkdir(parents=True, exist_ok=True)
            (temporary / entry['target']).replace(target)
        (temporary / 'object_map.json').replace(map_path)
        (temporary / 'topaz-staging.json').write_text(json.dumps(report, indent=2))
        (temporary / 'topaz-staging.json').replace(local / report_name)
    print(f'Staged {len(report["files"])} transparent PNGs at 4x; 6x masters preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--local', type=Path, default=Path('.playtest'))
    parser.add_argument('--scope', type=Path, default=Path('output/topaz-batch/cannon-scope.json'))
    parser.add_argument('--crisp', action='store_true', help='Stage the separate refined-border variant')
    args = parser.parse_args()
    stage(args.batch, args.local, args.scope, args.crisp)
