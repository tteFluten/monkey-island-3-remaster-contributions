#!/usr/bin/env python3
"""Stage the supplied 6x pointer/verb-coin package for the 4x game."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile

from PIL import Image
from hashlib import sha256

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def chunks(data):
    offset = 0
    while offset + 8 <= len(data):
        size = struct.unpack_from('>I', data, offset + 4)[0]
        if size < 8 or offset + size > len(data):
            raise ValueError('Invalid game index chunk')
        yield data[offset:offset + 4].decode(), offset, data[offset + 8:offset + size]
        offset += size

ROOT = Path(__file__).resolve().parents[1]


def stage(package, local, originals=ROOT / 'extracted/objects'):
    process = local / 'process.json'
    if process.exists():
        try:
            os.kill(json.loads(process.read_text())['pid'], 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Stop the game before staging its UI')
    manifest = json.loads((package / 'cursors-6x/manifest.json').read_text())
    names = sorted(manifest)
    if len(names) != 30 or any(Path(n).name != n or not n.startswith('0003_') or not n.endswith('.png') for n in names):
        raise ValueError('Expected 30 room-3 cursor images')
    index = next(data for tag, _, data in chunks((local / 'game/COMI.LA0').read_bytes()) if tag == 'DOBJ')
    ids = {}
    for number in range(struct.unpack_from('<I', index)[0]):
        name = index[4 + number * 46:44 + number * 46].split(b'\0')[0].decode()
        if name:
            ids.setdefault(name, []).append(number)
    mapping_path = local / 'hd/object_map.json'
    mapping = json.loads(mapping_path.read_text())
    report = dict(source=str(package.resolve()), source_scale=6, scale=4,
                  variant='antialiased', default_pointer='red', resampling='premultiplied-alpha Lanczos', files=[])
    sources = []
    for name in names:
        _, object_name, state = Path(name).stem.split('_')
        if len(ids.get(object_name, [])) != 1:
            raise ValueError(f'Ambiguous object: {object_name}')
        native_path = originals / name
        if not native_path.exists():
            native_path = originals / (name.rsplit('_', 1)[0] + '_0000.png')
        with Image.open(native_path) as native:
            size = native.size
        # Keep the user's red default; the supplied white state remains intact.
        source_name = name.replace('_0000.png', '_0001.png') if object_name == 'system-cursor-icon' else name
        sources.append((package / 'cursors-6x/antialiased' / source_name, Path('objects') / name, size))
        entry = mapping.setdefault(str(ids[object_name][0]), {'name': object_name, 'rooms': {}})
        if entry['name'] != object_name:
            raise ValueError(f'Conflicting mapping: {object_name}')
        states = entry['rooms'].setdefault('3', {'states': []})['states']
        entry['rooms']['3']['states'] = sorted(set(states + [int(state)]))
    for frame in range(63, 68):
        name = f'LFLF_0001_AKOS_0001_aframe_{frame}.png'
        sources.append((package / 'coin-6x/costumes' / name, Path('costumes') / name, (116, 118)))
    backup = local / 'backups' / ('pointer-coin-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    with tempfile.TemporaryDirectory(dir=local, prefix='pointer-coin-') as temp:
        temp = Path(temp)
        # Validate and convert everything before modifying the installed pack.
        for source, target, size in sources:
            with Image.open(source) as image:
                if image.mode != 'RGBA' or image.size != tuple(v * 6 for v in size):
                    raise ValueError(f'Expected RGBA at 6x original dimensions: {source}')
                if image.getchannel('A').getextrema()[0] != 0:
                    raise ValueError(f'Missing transparent canvas: {source}')
                output = temp / target
                output.parent.mkdir(parents=True, exist_ok=True)
                image.convert('RGBa').resize(tuple(v * 4 for v in size), Image.Resampling.LANCZOS).convert('RGBA').save(output)
            report['files'].append(dict(source=str(source), target=str(target), size=[v * 4 for v in size],
                                        source_sha256=digest(source), destination_sha256=digest(output)))
        backup.mkdir(parents=True)
        shutil.copy2(mapping_path, backup / 'object_map.json')
        for record in report['files']:
            target = Path(record['target'])
            dest = local / 'hd' / target
            if dest.exists():
                (backup / target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup / target)
            dest.parent.mkdir(parents=True, exist_ok=True)
            (temp / target).replace(dest)
        (temp / 'object_map.json').write_text(json.dumps(mapping, indent=2) + '\n')
        (temp / 'object_map.json').replace(mapping_path)
    report['backup'] = str(backup)
    (local / 'pointer-coin-staging.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--local', type=Path, default=ROOT / '.playtest')
    args = parser.parse_args()
    result = stage(args.package, args.local)
    print(f'Staged {len(result["files"])} images at 4x; originals preserved. Restart the game.')
