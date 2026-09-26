#!/usr/bin/env python3
"""Native final-film checks, with isolated saves/config and same-frame GPU captures."""
import argparse
import configparser
import json
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageChops, ImageStat
from check_aspect import Check, ROOT


def capture(check, name, enabled=True, retain=True):
    for stage in ('before', 'after'):
        (check.output / f'film-{stage}.png').unlink(missing_ok=True)
    check.send('film-capture')
    check.wait(lambda: (check.output / 'film-after.png').exists(), 'film capture')
    # The engine closes both PNGs before consuming another input command.
    check.send('window')
    before = Image.open(check.output / 'film-before.png').convert('RGB')
    after = Image.open(check.output / 'film-after.png').convert('RGB')
    diff = ImageChops.difference(before, after)
    if enabled:
        assert diff.getbbox(), f'{name}: film did not affect the final frame'
        mean = sum(ImageStat.Stat(diff).mean) / 3
        assert mean < 3.0, (name, 'unexpectedly strong or misaligned film', mean)
        # Encoded black and presentation bars must remain exactly black.
        black = before.point(lambda x: 255 if x == 0 else 0)
        r, g, b = black.split()
        black = ImageChops.multiply(ImageChops.multiply(r, g), b)
        for channel in after.split():
            assert not ImageChops.multiply(channel, black).getbbox(), (name, 'black bars changed')
    else:
        assert not diff.getbbox(), f'{name}: bypass altered pixels'
        mean = 0
    if retain:
        for stage in ('before', 'after'):
            shutil.copyfile(check.output / f'film-{stage}.png', check.output / f'{name}-{stage}.png')
    print(f'PASS {name}: {before.size}, mean RGB difference {mean:.4f}', flush=True)
    return mean


def toggle(check, expected):
    check.send('key 102')  # Plain F; no modifiers.
    config = configparser.ConfigParser(interpolation=None)
    config.read(check.output / 'scummvm.ini')
    assert config.getboolean('scummvm', 'hd_film_enabled') == expected
    assert config.getint('scummvm', 'hd_film_strength', fallback=20) == 20


def record_motion(check, output):
    frames = check.output / 'motion'
    frames.mkdir(exist_ok=True)
    # Sample 72 consecutive shader ticks on the static options page. This is
    # a controlled film-motion preview, not a real-time gameplay recording.
    for tick in range(72):
        check.send(f'film-time {tick}')
        capture(check, f'motion-{tick:03}', retain=False)
        shutil.copyfile(check.output / 'film-after.png', frames / f'{tick:03}.png')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '24', '-i',
                    str(frames / '%03d.png'), '-c:v', 'libx264', '-crf', '12',
                    '-pix_fmt', 'yuv420p', str(output / 'film-motion.mp4')], check=True)
    check.send('film-time -1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/film-check')
    parser.add_argument('--motion', action='store_true', help='Save a 3-second sampled film-motion preview')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    grades = out / 'grades.json'
    shutil.copyfile(ROOT / 'data/color-grades.json', grades)
    results = {}
    for aspect in (169, 43):
        check = Check(out / str(aspect), aspect, color_grades_path=grades,
                      config_overrides={'scummvm': {'hd_film_enabled': 'false', 'hd_film_strength': '20'},
                                        'comi': {'hd_gpu_effects': 'true'}})
        try:
            check.jump(9)
            capture(check, 'disabled', False)
            toggle(check, True)
            check.send('film-time 24')
            results[f'gameplay-{aspect}'] = capture(check, 'gameplay')
            check.send('move 180 180')
            capture(check, 'cursor-moved')
            check.send('key 105')
            check.wait(lambda: check.state().get('inventoryOpen'), 'inventory')
            capture(check, 'inventory')
            check.send('key 105')
            check.wait(lambda: not check.state().get('inventoryOpen'), 'inventory closed')
            check.send('key 111')
            check.room(92)
            capture(check, 'menu')
            toggle(check, False)
            capture(check, 'menu-bypass', False)
            toggle(check, True)
            if args.motion and aspect == 169:
                record_motion(check, out)
            check.send('key 27')
            check.room(9)
            check.send('film-time -1')
            check.send('resize 960 800')
            capture(check, 'resized')
            check.send('fullscreen 1')
            capture(check, 'fullscreen')
            check.send('fullscreen 0')
            check.send('resize 1280 720' if aspect == 169 else 'resize 1280 960')
            movie = check.output / 'movie.txt'
            movie.write_text('SB020.SAN\n')
            check.wait(lambda: not movie.exists(), 'movie started')
            capture(check, 'movie')
            toggle(check, False)
            capture(check, 'movie-bypass', False)
            toggle(check, True)
            assert 'HD video: playing' in (check.output / 'engine.log').read_text()
            check.send('key 27')
            time.sleep(1)
            capture(check, 'movie-return')
        finally:
            check.close()
    # Strength zero is an exact bypass even with the switch enabled.
    check = Check(out / 'zero', 169, color_grades_path=grades,
                  config_overrides={'scummvm': {'hd_film_enabled': 'true', 'hd_film_strength': '0'}})
    try:
        capture(check, 'zero-strength', False)
    finally:
        check.close()
    check = Check(out / 'cpu-scene', 169, color_grades_path=grades,
                  config_overrides={'scummvm': {'hd_film_enabled': 'true', 'hd_film_strength': '20'},
                                    'comi': {'hd_gpu_effects': 'false'}})
    try:
        check.jump(9)
        capture(check, 'cpu-scene-film')
        # The authored wide margins must receive film even without GPU scene effects.
        before = Image.open(check.output / 'film-before.png').convert('RGB')
        after = Image.open(check.output / 'film-after.png').convert('RGB')
        assert ImageChops.difference(before, after).crop((0, 0, before.width // 10, before.height)).getbbox()
    finally:
        check.close()
    (out / 'result.json').write_text(json.dumps({'passed': True, 'differences': results}, indent=2))


if __name__ == '__main__':
    main()
