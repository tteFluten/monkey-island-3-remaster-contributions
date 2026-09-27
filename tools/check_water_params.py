#!/usr/bin/env python3
"""Check water tuning, visual effects and persistence in an isolated native 16:9 session."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from check_aspect import Check, ROOT

CONTROLS = [('waterRed', 5, 5), ('waterGreen', 6, 5), ('waterBlue', 7, 5),
            ('waterLight', 8, 10), ('waterLightDirection', 9, 5),
            ('waterGloss', 10, 5), ('waterScale', 11, 5)]
OVERRIDES = {'comi': {'hd_gpu_effects': 'true', 'hd_water_shader': 'true'},
             'scummvm': {'hd_film_enabled': 'false'}}


def error(a, b, region):
    box = tuple(round(v * (a.width if i % 2 == 0 else a.height)) for i, v in enumerate(region))
    return max(ImageStat.Stat(ImageChops.difference(a.crop(box), b.crop(box))).mean)


def capture(check, name):
    check.screenshot(name)
    return Image.open(check.output / (name + '.png')).convert('RGB')


def button(check, row):
    check.click_game(check.state()['viewportWidth'] - 308 + 281, 19 + (row + 2) * 16)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/water-params/check')
    parser.add_argument('--baseline-engine', type=Path, help='Optional pre-change binary for neutral appearance comparison')
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    (out / 'result.json').unlink(missing_ok=True)
    grades = out / 'grades.json'
    original = {'schemaVersion': 2, 'global': {'waterSpeed': 0},
                'rooms': {'75': {'brightness': 4, 'shadowBlue': 31}, '10': {'waterWaves': 30}}}
    grades.write_text(json.dumps(original))
    saved = lambda: json.loads(grades.read_text())
    wet, dry = (.02, .77, .25, .96), (.86, .85, .98, .97)
    report = {'controls': []}
    before = None
    if args.baseline_engine:
        check = Check(out / 'before', color_grades_path=grades,
                      engine_path=args.baseline_engine.resolve(), config_overrides=OVERRIDES)
        try:
            check.jump(75)
            before = capture(check, 'neutral')
        finally:
            check.close()
    check = Check(out / 'current', color_grades_path=grades, config_overrides=OVERRIDES)
    try:
        check.jump(75)
        check.wait(lambda: check.state().get('waterBackend') == 'opengl-shader', 'water shader')
        neutral = capture(check, 'neutral')
        if before:
            report['neutralError'] = error(before, neutral, wet)
            assert report['neutralError'] < .1, report
        assert saved() == original, 'Merely loading old settings changed them'
        check.send('key 119')
        capture(check, 'water-panel')
        for key, row, step in CONTROLS:
            button(check, row)
            for _ in range(5):
                check.send('key 1073741903')  # Five additional Right steps.
            expected = (0 if key == 'waterLightDirection' else 100) + 6 * step
            assert saved()['rooms']['75'][key] == expected, saved()
            changed = capture(check, key)
            water_error, dry_error = error(neutral, changed, wet), error(neutral, changed, dry)
            assert water_error > .1, (key, water_error)
            assert dry_error < .1, (key, 'dry scenery changed', dry_error)
            report['controls'].append({'key': key, 'waterChange': water_error, 'dryChange': dry_error})
            check.send('key 114')  # Reset water only, preserving color and shadow overrides.
            assert saved()['rooms']['75'] == original['rooms']['75'], saved()
            assert saved()['rooms']['10'] == original['rooms']['10'], saved()
            print(f'PASS {key}: saved and visible only on water', flush=True)
        # A room override can return to the edited global value.
        check.send('key 103')
        button(check, 5)
        assert saved()['global']['waterRed'] == 105
        check.send('key 103')
        button(check, 5)
        assert saved()['rooms']['75']['waterRed'] == 110
        check.send('key 8')
        assert 'waterRed' not in saved()['rooms']['75']
        # Persist every new control, including one degree-valued parameter.
        for key, row, step in CONTROLS:
            button(check, row)
        persistent = dict(saved()['rooms']['75'])
        capture(check, 'saved-water-panel')
        check.send('key 27')
        capture(check, 'custom-water')
        # The full-surface room retains its final reflection control; all rows fit.
        home = 10
        check.save_load(2, 0, home)
        check.send('key 119')
        capture(check, 'full-surface-water-panel')
    finally:
        check.close()
    check = Check(out / 'restart', color_grades_path=grades, config_overrides=OVERRIDES)
    try:
        check.jump(75)
        check.send('key 119')
        for key, row, step in CONTROLS:
            button(check, row)
            assert saved()['rooms']['75'][key] == persistent[key] + step, saved()
        assert saved()['rooms']['75']['shadowBlue'] == 31
        # Shadow settings now occupy high mask bits. Exercise their real JSON/UI path.
        for _ in range(3):
            check.send('key 9')  # Water -> Scene Look -> Film -> Shadows.
        button(check, 7)
        assert saved()['rooms']['75']['shadowBlue'] == 32, saved()
        assert saved()['rooms']['75']['waterRed'] == persistent['waterRed'] + 5
        report['passed'] = True
        (out / 'result.json').write_text(json.dumps(report, indent=2))
        print('PASS restart, global inheritance, water reset and independent shadow settings', flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
