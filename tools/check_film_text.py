#!/usr/bin/env python3
"""Check chromatic text protection in real 16:9 frames with isolated settings/saves."""
import argparse
import json
from pathlib import Path
import shutil
import time

import numpy as np
from PIL import Image, ImageFilter

from check_aspect import Check, ROOT


def menu_ink(before, rect):
    """Find lettering independently of the engine mask, including its edge pixels."""
    x, y, w, h = rect
    # Effects Volume: original game coordinates, clear of the slider/artwork.
    bounds = (round(x + 46 * w / 640), round(y + 83 * h / 480),
              round(x + 119 * w / 640), round(y + 100 * h / 480))
    crop = np.asarray(before.crop(bounds))
    ink = Image.fromarray(np.uint8(crop.max(axis=2) < 100) * 255)
    # Include the antialiased boundary and neighboring pixels where shifted
    # red/blue copies escaped the old point-sampled coverage test.
    ink = ink.filter(ImageFilter.MaxFilter(3))
    mask = Image.new('L', before.size)
    mask.paste(ink, bounds[:2])
    return np.asarray(mask) > 0


def inspect(check, name, menu=False):
    for filename in ('film-before.png', 'film-after.png', 'film-text.pgm', 'film-text.json'):
        (check.output / filename).unlink(missing_ok=True)
    check.send('film-capture')
    check.wait(lambda: (check.output / 'film-after.png').exists(), 'film capture')
    check.send('window')  # Synchronize after the PNG writers close.
    before = Image.open(check.output / 'film-before.png').convert('RGB')
    after = Image.open(check.output / 'film-after.png').convert('RGB')
    coverage = Image.open(check.output / 'film-text.pgm')
    # Use the captured presentation rectangle, including fullscreen safe-area
    # insets and panorama overscan, rather than assuming a centered viewport.
    geometry = json.loads((check.output / 'film-text.json').read_text())
    rect = geometry['screenRect']
    source_x, source_y, source_w, source_h = geometry['sourceRect']
    coverage = coverage.crop((round(source_x * coverage.width), round(source_y * coverage.height),
                              round((source_x + source_w) * coverage.width),
                              round((source_y + source_h) * coverage.height)))
    projected = Image.new('L', before.size)
    projected.paste(coverage.resize((round(rect[2]), round(rect[3])), Image.Resampling.BILINEAR),
                    (round(rect[0]), round(rect[1])))
    protected = np.asarray(projected) > 64
    assert protected.sum() > 100, (name, 'no rendered text in capture')
    difference = np.abs(np.asarray(before).astype(int) - np.asarray(after).astype(int)).max(axis=2)
    # One level allows GPU interpolation rounding at nonintegral window scales.
    assert difference[protected].max() <= 1, (name, 'text changed', int(difference[protected].max()))
    if menu:
        ink = menu_ink(before, rect)
        assert ink.sum() > 100, (name, 'menu lettering missing')
        # The outer ring can include plain parchment; allow its tiny texture
        # changes while rejecting the old, much stronger shifted glyph copies.
        assert difference[ink].max() <= 2, (name, 'colored glyph fringe', int(difference[ink].max()))
    assert (difference[~protected] > 1).sum() > 100, (name, 'scene aberration was disabled')
    for filename in ('film-before.png', 'film-after.png', 'film-text.pgm', 'film-text.json'):
        shutil.copyfile(check.output / filename, check.output / f'{name}-{filename}')
    result = {'textPixels': int(protected.sum()), 'maximumTextDifference': int(difference[protected].max()),
              'changedScenePixels': int((difference[~protected] > 1).sum())}
    print(f'PASS {name}: {result}', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/film-text-check')
    parser.add_argument('--dialogue', action='store_true', help='Also talk to Wally; requires an early-game slot-0 save')
    args = parser.parse_args()
    check = Check(args.output, config_overrides={
        'comi': {'hd_gpu_effects': 'true', 'subtitles': 'true'},
        'scummvm': {'hd_film_enabled': 'true', 'hd_film_strength': '100', 'hd_film_chromatic': '200',
                    'hd_film_grain': '0', 'hd_film_dust': '0', 'hd_film_scratches': '0',
                    'hd_film_flicker': '0', 'hd_film_wobble': '0'}})
    results = {}
    home = check.state()['room']
    try:
        check.jump(9)
        check.send('key 111')
        check.room(92)
        results['menu'] = inspect(check, 'menu', menu=True)
        check.send('resize 960 800')
        results['menu-resized'] = inspect(check, 'menu-resized', menu=True)
        check.send('fullscreen 1')
        results['menu-fullscreen'] = inspect(check, 'menu-fullscreen', menu=True)
        check.send('fullscreen 0')
        check.send('resize 1280 720')
        check.send('key 27')
        check.room(9)
        check.send('key 117')
        results['look'] = inspect(check, 'look')
        check.send('key 9')
        results['film-settings'] = inspect(check, 'film-settings')
        check.send('key 117')
        check.jump(15)
        check.send('key 117')
        results['panorama-look'] = inspect(check, 'panorama-look')
        check.send('resize 960 800')
        results['panorama-resized'] = inspect(check, 'panorama-resized')
        check.send('key 117')
        check.send('key 106')
        results['scene-picker'] = inspect(check, 'scene-picker')
        check.send('key 106')
        check.save_load(2, 0, home)
        for movie, presentation in (('SINKSHP', 'windowed'), ('NEWBOOTS', 'fullscreen'), ('BBSAN', 'resized')):
            check.send('fullscreen ' + ('1' if presentation == 'fullscreen' else '0'))
            if presentation != 'fullscreen':
                check.send('resize ' + ('960 800' if presentation == 'resized' else '1280 720'))
            command = check.output / 'movie.txt'
            command.write_text(movie + '.SAN\n')
            check.wait(lambda: not command.exists(), 'movie command consumed')
            check.wait(lambda: check.window()['movieActive'], 'movie active')
            time.sleep(1)  # These clips have dialogue within their first second.
            name = f'subtitles-{movie}-{presentation}'
            results[name] = inspect(check, name)
            check.send('key 27')
            check.wait(lambda: not check.window()['movieActive'], 'movie ended')
        if args.dialogue:
            check.send('resize 1280 720')
            check.save_load(2, 0, home)
            check.jump(9)
            check.click_game(270, 320)
            check.send('down 565 480')
            time.sleep(1)
            check.send('move 620 430')  # Mouth on the native verb coin.
            check.send('up 620 430')
            time.sleep(2)
            results['speech'] = inspect(check, 'speech')
            time.sleep(4)
            results['dialogue-choices'] = inspect(check, 'dialogue-choices')
    finally:
        check.close()
    (check.output / 'result.json').write_text(json.dumps({'passed': True, 'cases': results}, indent=2))


if __name__ == '__main__':
    main()
