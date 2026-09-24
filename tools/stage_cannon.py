#!/usr/bin/env python3
"""Install the direct 4x cannon batch in both existing Topaz comparison packs."""
import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image
from prepare_topaz import digest


def stage(batch, local):
    process = local / 'process.json'
    if process.exists():
        pid = json.loads(process.read_text())['pid']
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Stop the game before installing cannon textures')
    sources = json.loads((batch / 'cannon-sprites-scope.json').read_text())['sources']
    records = {r['source']: r for r in json.loads((batch / 'manifest.json').read_text())['records']}
    if not sources or any(not re.fullmatch(r'costumes/LFLF_0009_AKOS_0026_frame_\d+\.png', s) for s in sources):
        raise ValueError('Cannon scope must contain only room-9 costume-26 frames')
    local.mkdir(parents=True, exist_ok=True)
    report = dict(scale=4, model='Wonder 3.5', enhancement='high', files=[])
    with tempfile.TemporaryDirectory(dir=local, prefix='stage-cannon-') as temporary:
        temporary = Path(temporary)
        for source in sources:
            master = batch / '4x' / source
            expected = tuple(v * 4 for v in records[source]['size'])
            with Image.open(master) as image:
                if image.mode != 'RGBA' or image.size != expected:
                    raise ValueError(f'Invalid 4x cannon result: {source}')
                image.load()
            for pack in ('topaz-cannon', 'topaz-crisp'):
                target = Path(pack) / source.replace('_frame_', '_aframe_')
                staging = temporary / target
                staging.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(master, staging)
                report['files'].append(dict(source=source, target=str(target),
                                            size=expected, master_sha256=digest(master)))
        for entry in report['files']:
            destination = local / 'hd' / entry['target']
            destination.parent.mkdir(parents=True, exist_ok=True)
            (temporary / entry['target']).replace(destination)
        receipt = temporary / 'cannon-sprites-staging.json'
        receipt.write_text(json.dumps(report, indent=2) + '\n')
        receipt.replace(local / receipt.name)
    print(f'Installed {len(sources)} direct-4x cannon frames in both Topaz packs; masters preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--local', type=Path, default=Path('.playtest'))
    args = parser.parse_args()
    stage(args.batch, args.local)
