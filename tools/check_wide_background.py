#!/usr/bin/env python3
"""Native cannon extension checks using copied saves and isolated side artwork.

Requires a staged wide cannon variant, Pillow, and a cannon-room slot-0 fixture.
MI3_ASPECT_TEST_SAVES may point at a fixture directory. User saves/art are intact.
"""
import argparse
import json
from pathlib import Path
import shutil

from PIL import Image, ImageChops, ImageStat
from check_aspect import Check, ROOT


def sides(check, name, expected=True):
    check.screenshot(name)
    actual = Image.open(check.output / (name + '.png')).convert('RGB')
    w, h = actual.size
    # Match the centered 16:9 presentation within any window aspect ratio.
    fh = min(h, w * 9 // 16)
    fw = fh * 16 // 9
    x, y = (w - fw) // 2, (h - fh) // 2
    reference = (Image.open(check.config['comi']['hd_path'] + '/widescreen/bg_0009.png')
                 .convert('RGB').resize((fw, fh), Image.Resampling.BILINEAR)) if expected else None
    # Stay a few pixels inside the sides to allow integer rounding at odd sizes.
    for left, right in ((4, fw // 8 - 4), (fw * 7 // 8 + 4, fw - 4)):
        region = actual.crop((x + left, y + 4, x + right, y + fh - 4))
        if expected:
            wanted = reference.crop((left, 4, right, fh - 4))
            difference = max(ImageStat.Stat(ImageChops.difference(region, wanted)).mean)
            assert difference < 3, (name, difference)
        else:
            assert max(ImageStat.Stat(region).mean) < 1, name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/widescreen/cannon')
    args = parser.parse_args()
    output = args.output.resolve()
    hd = output / 'hd'
    hd.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / '.playtest/hd').iterdir():
        if source.name != 'widescreen' and not (hd / source.name).exists():
            (hd / source.name).symlink_to(source, target_is_directory=source.is_dir())
    (hd / 'widescreen').mkdir(exist_ok=True)
    wide = hd / 'widescreen/bg_0009.png'
    shutil.copyfile(ROOT / '.playtest/hd/widescreen/bg_0009.png', wide)
    # Compare the artwork itself, independently of the player's saved scene look.
    grades = output / 'color-grades.json'
    grades.write_text(json.dumps({'schemaVersion': 1, 'rooms': {}}))
    check = Check(output, 169, hd_path=hd, color_grades_path=grades)
    try:
        check.room(9)
        assert check.state()['viewportWidth'] == 640
        sides(check, 'cannon-full-169')
        # Pointer mapping remains in the original room coordinates.
        check.send('move 640 450')
        assert abs(check.state()['mouseRoomX'] - 320) <= 1
        assert abs(check.state()['mouseRoomY'] - 300) <= 1
        check.send('down 10 200'); check.send('up 10 200')
        assert 'HD-ASPECT input blocked' in (output / 'engine.log').read_text()
        check.select(43)
        check.screenshot('cannon-center-43')
        assert check.state()['viewportWidth'] == 640
        check.select(169)
        sides(check, 'cannon-restored-169')
        check.send('key 105')
        sides(check, 'inventory-169', expected=False)
        check.send('key 105')
        sides(check, 'inventory-closed-169')
        check.send('resize 960 800')
        sides(check, 'resized-169')
        check.send('fullscreen 1')
        sides(check, 'fullscreen-169')
        check.send('fullscreen 0')
        check.send('resize 1280 720')
        # Invalid/missing sidecar must clear cached art without affecting gameplay.
        backup = wide.read_bytes()
        for contents, name in ((b'bad png', 'invalid'), (None, 'missing')):
            if contents is None:
                wide.unlink()
            else:
                wide.write_bytes(contents)
            command = {'id': check.state()['commandId'] + 1, 'action': 'reload', 'room': 9}
            (output / 'command.json').write_text(json.dumps(command))
            check.wait(lambda: check.state()['commandId'] == command['id'], 'reload')
            sides(check, name + '-fallback', expected=False)
        wide.write_bytes(backup)
        command = {'id': check.state()['commandId'] + 1, 'action': 'reload', 'room': 9}
        (output / 'command.json').write_text(json.dumps(command))
        check.wait(lambda: check.state()['commandId'] == command['id'], 'restored reload')
        sides(check, 'restored-art-169')
        check.save_load(1, 7, 9)
        check.jump(15)
        assert check.state()['viewportWidth'] == 864
        check.save_load(2, 7, 9)
        sides(check, 'save-restored-169')
        movie = output / 'movie.txt'
        movie.write_text('SB020.SAN\n')
        check.wait(lambda: not movie.exists(), 'movie consumed')
        sides(check, 'movie-169', expected=False)
        check.wait(lambda: check.state().get('ready'), 'movie return', 30)
        check.room(9)
        sides(check, 'movie-restored-169')
        (output / 'result.json').write_text(json.dumps({'passed': True}))
        print('PASS: full image, mode switching, pointer alignment, inventory, resize, fullscreen, fallback, reload, save/room restoration, cinematic return', flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
