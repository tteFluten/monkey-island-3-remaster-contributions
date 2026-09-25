#!/usr/bin/env python3
"""Check room 0087 Scene Look using copied saves and isolated look settings."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageStat
from check_aspect import Check, ROOT


class DifficultyCheck(Check):
    def room(self, room):
        # Difficulty selection intentionally isn't marked ready for gameplay.
        if room == 87:
            self.wait(lambda: self.state().get('room') == 87, 'difficulty screen')
        else:
            super().room(room)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', action='store_true')
    parser.add_argument('--aspect', type=int, choices=(43, 169), default=169)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/difficulty-look')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    grades = out / 'color-grades.json'
    original = {'schemaVersion': 2, 'global': {'contrast': 4}, 'rooms': {'9': {'warmth': 6}}}
    grades.write_text(json.dumps(original))
    overrides = {'comi': {'hd_gpu_effects': str(not args.cpu).lower()}}

    def saved():
        return json.loads(grades.read_text())

    def button(check, row, plus=True):
        left = check.state()['viewportWidth'] - 308
        line = row + 2 + (row >= 6) + (row >= 11)
        check.click_game(left + (281 if plus else 255), 19 + line * 16)
        assert check.state()['room'] == 87, 'Look click reached the difficulty controls'

    check = DifficultyCheck(out, args.aspect, color_grades_path=grades, config_overrides=overrides)
    try:
        check.jump(87)
        backend = 'cpu-effects' if args.cpu else 'opengl-shaders'
        check.wait(lambda: check.state().get('renderBackend') == backend, backend)
        check.send('key 117')  # U opens the panel on the difficulty screen.
        check.send('key 1073741903')  # Right: brightness +2.
        assert saved()['rooms']['87']['brightness'] == 2
        button(check, 2)  # Saturation via mouse.
        button(check, 11)  # Vignette on.
        button(check, 12)  # Strength +5.
        room = saved()['rooms']['87']
        assert room['saturation'] == 5 and room['vignetteEnabled'] == 1
        assert room['vignetteAmount'] == 45
        assert saved()['rooms']['9'] == original['rooms']['9']
        assert saved()['global']['contrast'] == 4
        check.screenshot('difficulty-look-panel')
        check.send('key 117')
        check.screenshot('vignette-on')
        check.send('key 117'); button(check, 11, False); check.send('key 117')
        check.screenshot('vignette-off')
        on = Image.open(out / 'vignette-on.png').convert('RGB')
        off = Image.open(out / 'vignette-off.png').convert('RGB')
        w, h = on.size
        box = (0, 0, w // 12, h // 5)
        off_light = sum(ImageStat.Stat(off.crop(box)).mean)
        assert sum(ImageStat.Stat(on.crop(box)).mean) < off_light * .9
        check.send('key 117'); button(check, 11); check.send('key 27')
        assert saved()['rooms']['87']['vignetteEnabled'] == 1
        assert not check.state()['error']
    finally:
        check.close()

    check = DifficultyCheck(out / 'restart', args.aspect, color_grades_path=grades, config_overrides=overrides)
    try:
        check.jump(87)
        check.screenshot('persisted-vignette')
        image = Image.open(check.output / 'persisted-vignette.png').convert('RGB')
        assert sum(ImageStat.Stat(image.crop(box)).mean) < off_light * .9
        assert not check.state()['error']
        (out / 'result.json').write_text(json.dumps({'passed': True, 'backend': backend, 'aspect': args.aspect}))
        print('PASS: difficulty Scene Look, keyboard/mouse, vignette rendering, isolated room settings, restart persistence')
    finally:
        check.close()


if __name__ == '__main__':
    main()
