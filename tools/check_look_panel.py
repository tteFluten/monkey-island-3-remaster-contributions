#!/usr/bin/env python3
"""Exercise U, clickable scene controls, vignette, and persistence on copied saves.

Uses isolated color grades; never changes the project's authored presets.
Requires Pillow and a cannon-room fixture via MI3_ASPECT_TEST_SAVES.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageStat
from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/look-panel/native')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    grades = out / 'color-grades.json'
    grades.write_text(json.dumps({'schemaVersion': 1, 'rooms': {'61': {'warmth': 6}, '15': {'contrast': 4}}}))
    check = Check(out, 169, color_grades_path=grades)
    def grade(room=61):
        return json.loads(grades.read_text())['rooms'].get(str(room), {})
    def button(row, plus=True):
        left = check.state()['viewportWidth'] - 300 - 8
        line = row + 2 + (row >= 6) + (row >= 11)
        check.click_game(left + (281 if plus else 255), 8 + 4 + line * 16 + 7)
    try:
        check.jump(61)
        check.send('key 117')  # U
        check.screenshot('good-soup-panel')
        check.send('key 1073741903')  # Right: brightness +2.
        assert grade()['brightness'] == 2
        check.send('key 1073741905')  # Down, then Right: contrast +2.
        check.send('key 1073741903')
        assert grade()['contrast'] == 2 and grade()['warmth'] == 6
        button(2)  # Saturation via mouse.
        assert grade()['saturation'] == 5
        button(6, False)  # Focus level down.
        check.config.read(out / 'scummvm.ini')
        assert check.config.getint('comi', 'hd_depth_of_field') == 1
        button(10)  # Scene depth.
        check.config.read(out / 'scummvm.ini')
        assert check.config.getint('comi', 'hd_dof_depth') == 2
        button(11); button(12); button(13); button(14)
        g = grade()
        assert (g['vignetteEnabled'], g['vignetteAmount'], g['vignetteRadius'], g['vignetteSoftness']) == (1, 45, 65, 55)
        check.screenshot('good-soup-vignette-controls')
        button(11, False)
        assert grade()['vignetteEnabled'] == 0 and grade()['vignetteAmount'] == 45
        button(11)
        check.send('key 117')  # U closes; panel no longer consumes movement keys.
        check.screenshot('good-soup-vignette-on')
        check.send('key 117'); button(11, False); check.send('key 117')
        check.screenshot('good-soup-vignette-off')
        on = Image.open(out / 'good-soup-vignette-on.png').convert('RGB')
        off = Image.open(out / 'good-soup-vignette-off.png').convert('RGB')
        w, h = on.size
        box = (0, 0, w // 12, h // 5)
        assert sum(ImageStat.Stat(on.crop(box)).mean) < sum(ImageStat.Stat(off.crop(box)).mean) * .9
        check.send('key 117'); button(11); check.send('key 27')
        assert grade()['vignetteEnabled'] == 1
        assert grade(15)['contrast'] == 4  # Other room preset preserved.
        # B bypass leaves the persisted settings untouched; Escape closes.
        check.send('key 117'); check.send('key 98')
        check.screenshot('good-soup-bypass')
        assert grade()['vignetteEnabled'] == 1
        check.send('key 98'); check.send('key 27')
        # Reset selected softness without changing the other vignette settings.
        check.send('key 117'); button(14); check.send('key 8')
        assert grade()['vignetteSoftness'] == 50 and grade()['vignetteAmount'] == 45
        check.send('key 27')
        print('PASS: U, keyboard/mouse controls, depth, vignette toggle/shape, bypass, reset, room persistence', flush=True)
    finally:
        check.close()
    # Reopen the native engine and verify the same room treatment is loaded.
    check = Check(out / 'restart', 169, color_grades_path=grades)
    try:
        check.jump(61)
        check.send('key 117')
        check.screenshot('persisted-panel')
        check.send('key 117')
        check.screenshot('persisted-vignette')
        image = Image.open(check.output / 'persisted-vignette.png').convert('RGB')
        assert sum(ImageStat.Stat(image.crop(box)).mean) < sum(ImageStat.Stat(off.crop(box)).mean) * .9
        (out / 'result.json').write_text(json.dumps({'passed': True}))
        print('PASS: legacy presets load, vignette persists across restart', flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
