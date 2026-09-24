#!/usr/bin/env python3
"""Restore original COMI pointer artwork at 4x without changing its hotspots."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image
from prepare_topaz import digest, object_rgba

ROOT = Path(__file__).resolve().parents[1]
POINTERS = {105: 'system-cursor-icon', 108: 'north-arrow-icon'}


def stage(source, local, pointer_only=False):
    process = local / 'process.json'
    if process.exists():
        try:
            os.kill(json.loads(process.read_text())['pid'], 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Stop the game before restoring its pointers')
    mapping_path = local / 'hd/object_map.json'
    mapping = json.loads(mapping_path.read_text())
    backup = local / 'backups' / ('original-pointers-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    report = {'scale': 4, 'variant': 'original-red', 'pointer_only': pointer_only, 'resampling': 'nearest', 'files': []}
    with tempfile.TemporaryDirectory(dir=local, prefix='original-pointers-') as temp:
        for object_id, name in ({105: POINTERS[105]} if pointer_only else POINTERS).items():
            for state in (0, 1):
                filename = f'0003_{name}_{state:04d}.png'
                original = source / (f'0003_{name}_0001.png' if object_id == 105 else filename)
                with Image.open(original) as image:
                    if image.mode != 'P' or image.size != (80, 56):
                        raise ValueError(f'Expected original 80x56 indexed pointer: {original}')
                    # These BOMP objects use index 255, not a color-key guess.
                    rgba = object_rgba(image, 255)
                    if object_id == 105:
                        # The extracted preview palette marks original black
                        # outline index 39 as white. Preserve the native pixel
                        # geometry, red fill (index 9), and transparent canvas.
                        pixels = list(rgba.getdata())
                        for i, index in enumerate(image.getdata()):
                            if index == 39:
                                pixels[i] = (0, 0, 0, 255)
                        rgba.putdata(pixels)
                    rgba.resize((320, 224), Image.Resampling.NEAREST).save(Path(temp) / filename)
                report['files'].append({'name': filename, 'source_sha256': digest(original),
                                        'destination_sha256': digest(Path(temp) / filename)})
            mapping[str(object_id)] = {'name': name, 'rooms': {'3': {'states': [0, 1]}}}
        backup.mkdir(parents=True)
        shutil.copy2(mapping_path, backup / 'object_map.json')
        for file in report['files']:
            destination = local / 'hd/objects' / file['name']
            if destination.exists():
                shutil.copy2(destination, backup / file['name'])
            (Path(temp) / file['name']).replace(destination)
        mapping_path.write_text(json.dumps(mapping, indent=2) + '\n')
    report['backup'] = str(backup)
    (local / 'original-pointers.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pointer-only', action='store_true', help='Restore the mouse pointer without changing navigation arrows')
    parser.add_argument('--source', type=Path, default=ROOT / 'extracted/objects')
    parser.add_argument('--local', type=Path, default=ROOT / '.playtest')
    args = parser.parse_args()
    stage(args.source, args.local, args.pointer_only)
    print('Restored original red mouse pointer' + ('' if args.pointer_only else ' and north arrow') + '. Restart the game.')
