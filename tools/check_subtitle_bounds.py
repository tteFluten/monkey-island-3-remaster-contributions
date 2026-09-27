#!/usr/bin/env python3
"""Check actual subtitle ink against the visible frame using isolated saves.

Set MI3_ASPECT_TEST_SAVES to a clean gameplay fixture. Includes intentionally
unwrapped speech, off-screen speakers and oversized text; no player state changes.
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
import time

from PIL import Image
from check_aspect import Check, ROOT
from check_movies import start, restored

SENTENCE = ('This long dialogue should wrap inside the visible picture, even when '
            'the speaker stands beyond the edge of the screen.')


def capture(check, name, x, y, flags, text=SENTENCE):
    output = check.output
    probe = output / 'subtitle-probe.bin'
    temporary = output / 'subtitle-probe.tmp'
    temporary.write_bytes(struct.pack('<hhHH', x, y, flags, 1) + text.encode('ascii') + b'\n')
    temporary.replace(probe)
    # Wait for the new probe to be drawn before requesting the framebuffer.
    check.send('window')
    for filename in ('film-before.png', 'film-after.png', 'film-text.pgm', 'film-text.json'):
        (output / filename).unlink(missing_ok=True)
    check.send('film-capture')
    check.wait(lambda: (output / 'film-text.pgm').exists(), 'subtitle ink capture')
    check.send('window')  # Let the capture writers close.
    return inspect_frame(check, name, text == SENTENCE)


def inspect_frame(check, name, expect_wrap=False):
    output = check.output
    with Image.open(output / 'film-text.pgm') as mask:
        bounds = mask.getbbox()
        assert bounds is not None, (name, 'subtitle did not render')
        mask_w, mask_h = mask.size
    with Image.open(output / 'film-before.png') as frame:
        frame_w, frame_h = frame.size
    geometry = json.loads((output / 'film-text.json').read_text())
    left, top, width, height = geometry['screenRect']
    sx, sy, sw, sh = geometry['sourceRect']
    ink = [left + (bounds[0] / mask_w - sx) * width / sw,
           top + (bounds[1] / mask_h - sy) * height / sh,
           left + (bounds[2] / mask_w - sx) * width / sw,
           top + (bounds[3] / mask_h - sy) * height / sh]
    visible = [max(0, left), max(0, top), min(frame_w, left + width), min(frame_h, top + height)]
    # Independently project the captured glyph pixels into the actual display.
    # Require a 2% inset (implementation reserves 2.5%, including rounding and
    # the one-pixel antialiasing footprint in the text-protection mask).
    mx, my = (visible[2] - visible[0]) * .02, (visible[3] - visible[1]) * .02
    assert ink[0] >= visible[0] + mx and ink[1] >= visible[1] + my, (name, ink, visible)
    assert ink[2] <= visible[2] - mx and ink[3] <= visible[3] - my, (name, ink, visible)
    if expect_wrap:
        assert bounds[3] - bounds[1] > mask_h * .05, (name, 'long subtitle did not wrap')
    shutil.copyfile(output / 'film-before.png', output / f'{name}.png')
    print(f'PASS {name}: {ink}', flush=True)
    return {'ink': ink, 'visibleFrame': visible}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/subtitle-bounds/check')
    parser.add_argument('--rooms', type=int, nargs='+', default=(13, 15, 29, 40, 77),
                        help='Rooms covering wide art, panoramas, fixed, two-axis and vertical scrolling')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    grades = output / 'grades.json'
    shutil.copyfile(ROOT / 'data/color-grades.json', grades)
    check = Check(output, color_grades_path=grades, config_overrides={
        'comi': {'hd_gpu_effects': 'true', 'hd_font_size': '100', 'subtitles': 'true'},
        'scummvm': {'hd_film_enabled': 'true', 'hd_film_strength': '20'}})
    results = {}
    home = check.state()['room']
    try:
        for room in args.rooms:
            (output / 'subtitle-probe.bin').unlink(missing_ok=True)
            check.save_load(2, 0, home)
            check.jump(room)
            for width, height in ((1280, 720), (1280, 800), (1720, 720)):
                check.send(f'resize {width} {height}')
                # The capture mask includes object captions as well as speech.
                # Find empty scenery; black-bar moves are rejected and retain
                # the previous hover, while the picture center can be an object.
                window = check.window()
                for px, py in ((.5, .1), (.5, .9), (.25, .5), (.75, .5), (.5, .5)):
                    check.send(f'move {round(window["width"] * px)} {round(window["height"] * py)}')
                    if check.state().get('hoverObject') == 0:
                        break
                else:
                    raise AssertionError('No empty scenery to clear the object caption')
                for label, x, y, flags in (('top-left', -120, -80, 1), ('bottom-right', 1100, 700, 2)):
                    name = f'room-{room}-{width}x{height}-{label}'
                    results[name] = capture(check, name, x, y, flags)
        # A single unbreakable word must also be clipped by the HD glyph pass.
        results['oversized-word'] = capture(check, 'oversized-word', 0, 0, 0, 'W' * 160)
        (output / 'subtitle-probe.bin').unlink()
        check.send('key 111'); check.room(92)
        check.send('key 27'); check.room(args.rooms[-1])
        results['after-menu'] = capture(check, 'after-menu', 320, 460, 1)
        check.screenshot('after-menu')
        (output / 'subtitle-probe.bin').unlink()
        for width, height in ((1280, 720), (1280, 800), (1720, 720)):
            check.send(f'resize {width} {height}')
            start(check, 'SINKSHP.SAN')
            time.sleep(1)  # Opening speech uses the real cinematic subtitle path.
            for filename in ('film-before.png', 'film-after.png', 'film-text.pgm', 'film-text.json'):
                (output / filename).unlink(missing_ok=True)
            check.send('film-capture')
            check.wait(lambda: (output / 'film-text.pgm').exists(), 'cinematic subtitle ink capture')
            check.send('window')
            name = f'cinematic-{width}x{height}'
            results[name] = inspect_frame(check, name)
            check.send('key 27')
            restored(check, args.rooms[-1], 169)
    finally:
        (output / 'subtitle-probe.bin').unlink(missing_ok=True)
        check.close()
    (output / 'result.json').write_text(json.dumps({'passed': True, 'cases': results}, indent=2) + '\n')


if __name__ == '__main__':
    main()
