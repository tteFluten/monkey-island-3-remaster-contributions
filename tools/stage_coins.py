#!/usr/bin/env python3
"""Replace only the five verb-coin states, adapting 6x RGBA masters to 4x."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image
from stage_pointer_coin import ROOT, digest


def stage(source, local):
    process = local / 'process.json'
    if process.exists():
        try:
            os.kill(json.loads(process.read_text())['pid'], 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Stop the game before replacing its coin textures')
    report = dict(source=str(source.resolve()), source_scale=6, scale=4,
                  resampling='premultiplied-alpha Lanczos', files=[])
    backup = local / 'backups' / ('coins-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    with tempfile.TemporaryDirectory(dir=local, prefix='stage-coins-') as temporary:
        temporary = Path(temporary)
        # Finish validation and conversion before changing any installed image.
        for frame in range(63, 68):
            name = f'LFLF_0001_AKOS_0001_aframe_{frame}.png'
            original, output = source / name, temporary / name
            with Image.open(original) as image:
                if image.mode != 'RGBA' or image.size != (696, 708):
                    raise ValueError(f'Expected 696x708 RGBA coin: {original}')
                if image.getchannel('A').getextrema() != (0, 255):
                    raise ValueError(f'Expected transparent canvas and opaque coin: {original}')
                image.convert('RGBa').resize((464, 472), Image.Resampling.LANCZOS).convert('RGBA').save(output)
            report['files'].append(dict(source=str(original), target=f'costumes/{name}', size=[464, 472],
                                       source_sha256=digest(original), destination_sha256=digest(output)))
        backup.mkdir(parents=True)
        destination = local / 'hd/costumes'
        destination.mkdir(parents=True, exist_ok=True)
        for record in report['files']:
            name = Path(record['target']).name
            if (destination / name).exists():
                shutil.copy2(destination / name, backup / name)
        previous_report = local / 'coin-staging.json'
        if previous_report.exists():
            shutil.copy2(previous_report, backup / previous_report.name)
        for record in report['files']:
            name = Path(record['target']).name
            (temporary / name).replace(destination / name)
        report['backup'] = str(backup)
        (temporary / 'coin-staging.json').write_text(json.dumps(report, indent=2) + '\n')
        (temporary / 'coin-staging.json').replace(previous_report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--local', type=Path, default=ROOT / '.playtest')
    args = parser.parse_args()
    stage(args.source, args.local)
    print('Installed all five coin states at 4x; originals and previous artwork preserved. Restart the game.')
