#!/usr/bin/env python3
"""Stage the supplied efmi/sharp 6x font sheets for the 4x COMI-HD engine."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VARIANT = 'efmi/sharp'
NAMES = [f'FONT{i}.NUT_chars.png' for i in range(5)]
SHADOW_SLOTS = (0, 1, 2, 3)  # FONT4 already contains the original drop shadow.
SHADOW_OFFSET = 4  # One original game pixel at the runtime scale.


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hard_shadow(sheet):
    """Put solid black behind each glyph, without moving its fill or baseline."""
    result = Image.new('RGBA', sheet.size)
    for y in range(0, sheet.height, 224):
        for x in range(0, sheet.width, 224):
            cell = sheet.crop((x, y, x + 224, y + 224))
            alpha = cell.getchannel('A')
            bounds = alpha.getbbox()
            if bounds and (bounds[2] + SHADOW_OFFSET > 224 or bounds[3] + SHADOW_OFFSET > 224):
                raise ValueError('Glyph shadow would cross its font cell boundary')
            shadow = Image.new('RGBA', cell.size)
            shadow.paste((0, 0, 0, 255), (SHADOW_OFFSET, SHADOW_OFFSET, 224, 224),
                         alpha.crop((0, 0, 224 - SHADOW_OFFSET, 224 - SHADOW_OFFSET)))
            result.paste(Image.alpha_composite(shadow, cell), (x, y))
    return result


def stage(package, local):
    package, local = Path(package).resolve(), Path(local).resolve()
    process = local / 'process.json'
    if process.exists():
        pid = json.loads(process.read_text())['pid']
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Stop the game before staging its fonts')
    if any((local / 'hd/dialogue-font').glob('*x/FONT*.dat')):
        raise ValueError('Disable hd/dialogue-font before installing these sheets')

    report = {'package': str(package), 'variant': VARIANT,
              'source_scale': 6, 'scale': 4, 'resampling': 'nearest',
              'grid': [16, 16], 'cell_size': [224, 224],
              'added_shadow': {'slots': list(SHADOW_SLOTS),
                               'offset': [SHADOW_OFFSET, SHADOW_OFFSET],
                               'color': [0, 0, 0, 255]},
              'preserved_shadow_slots': [4], 'files': []}
    local.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=local, prefix='stage-fonts-') as temp:
        temporary = Path(temp)
        # Validate and convert the complete set before replacing any active font.
        for slot, name in enumerate(NAMES):
            source = package / VARIANT / name
            with Image.open(source) as image:
                if image.format != 'PNG' or image.mode != 'RGBA' or image.size != (5376, 5376):
                    raise ValueError(f'Expected a 5376x5376 RGBA PNG: {source}')
                if any(image.getchannel('A').histogram()[1:255]):
                    raise ValueError(f'Expected binary alpha (0 or 255): {source}')
                resized = image.resize((3584, 3584), Image.Resampling.NEAREST)
                if slot in SHADOW_SLOTS:
                    resized = hard_shadow(resized)
                resized.save(temporary / name)
            report['files'].append({
                'source': str(source), 'target': f'hd/fonts/{name}',
                'size': [3584, 3584], 'source_sha256': sha256(source),
                'destination_sha256': sha256(temporary / name),
            })
        destination = local / 'hd/fonts'
        destination.mkdir(parents=True, exist_ok=True)
        for name in NAMES:
            (temporary / name).replace(destination / name)
        report_path = temporary / 'font-staging.json'
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        report_path.replace(local / 'font-staging.json')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path, help='Path to the supplied fonts-6x package')
    parser.add_argument('--local', type=Path, default=ROOT / '.playtest')
    args = parser.parse_args()
    stage(args.package, args.local)
    print('Staged all five efmi/sharp fonts at 4x; originals preserved. Restart the game to load them.')
