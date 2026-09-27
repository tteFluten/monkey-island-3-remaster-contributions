#!/usr/bin/env python3
"""Native map input/transition checks using isolated saves, config and artwork.

Use a clean gameplay fixture (e.g. a cannon save) via MI3_ASPECT_TEST_SAVES.
Never changes player saves, workspace selections or Scene Look settings.
"""
import argparse
import json
from pathlib import Path
import shutil

from check_aspect import Check, ROOT

LANDMARKS = [('cove', 230, 350, 156, 168), ('swamp', 355, 587, 236, 276),
             ('beach', 795, 548, 564, 252), ('club', 867, 466, 616, 204),
             ('town-west', 577, 435, 392, 216), ('town-upper', 637, 334, 450, 138),
             ('town-east', 700, 412, 516, 168), ('fort', 654, 703, 456, 328)]
ROOMS = {'cove': 33, 'swamp': 29, 'beach': 28, 'club': 26,
         'town-west': 15, 'town-upper': 15, 'town-east': 15, 'fort': 14}


def artwork(output, wide):
    hd = output / 'hd'
    hd.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / '.playtest/hd').iterdir():
        target = hd / source.name
        if source.name in ('backgrounds', 'widescreen'):
            target.mkdir(exist_ok=True)
            for child in source.iterdir():
                if child.name.startswith('bg_0013.png'): continue
                dest = target / child.name
                if not dest.exists(): dest.symlink_to(child)
        elif not target.exists(): target.symlink_to(source)
    # The original art is reference-only. Export a local 4x fallback, leaving
    # the selected master and all installed runtime artwork untouched.
    if not wide:
        from PIL import Image
        with Image.open(ROOT / 'extracted/backgrounds/0013_plndrmap.png') as source:
            source.convert('RGBA').resize((2560, 1920), Image.Resampling.NEAREST).save(hd / 'backgrounds/bg_0013.png')
        (hd / 'backgrounds/bg_0013.png.stamp').write_text('original-reference')
    else:
        for name in ('backgrounds/bg_0013.png', 'backgrounds/bg_0013.png.stamp', 'widescreen/bg_0013.png'):
            shutil.copyfile(ROOT / 'assets/runtime' / name, hd / name)
    return hd


def screen_point(check, x, y):
    window = check.window()
    height = max(window['height'], window['width'] * 9 / 16)
    width = height * 16 / 9
    return round((window['width'] - width) / 2 + x * width / 1000), round((window['height'] - height) / 2 + y * height / 1000)


def hover(check, x, y):
    px, py = screen_point(check, x, y)
    check.send(f'move {px} {py}')
    return check.state()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/plunder-map/check')
    parser.add_argument('--transitions', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    grades = output / 'grades.json'
    grades.write_text('{"schemaVersion":2,"global":{},"rooms":{}}')
    results = {'destinations': {}, 'sizes': [], 'transitions': {}}
    fallback = output / 'fallback'
    check = Check(fallback, hd_path=artwork(fallback, False), color_grades_path=grades)
    try:
        check.jump(13)
        assert not check.state()['plunderMap']
        for name, _, _, sx, sy in LANDMARKS:
            check.send(f'move {round(160 + sx * 1.5)} {round(sy * 1.5)}')
            results['destinations'][name] = check.state()['hoverObject']
    finally:
        check.close()
    wide = output / 'wide'
    check = Check(wide, hd_path=artwork(wide, True), color_grades_path=grades)
    try:
        home = check.state()['room']
        check.jump(13)
        check.wait(lambda: check.state().get('plunderMapInput'), 'registered map')
        for width, height in [(1280, 720), (1280, 800), (1720, 720)]:
            check.send(f'resize {width} {height}')
            for name, x, y, sx, sy in LANDMARKS:
                state = hover(check, x, y)
                assert (state['mouseRoomX'], state['mouseRoomY']) == (sx, sy), (name, state)
                assert state['hoverObject'] == results['destinations'][name], (name, state)
            for x, y in [(100, 500), (900, 500), (500, 250), (500, 750)]:
                assert hover(check, x, y)['hoverObject'] == 0
            check.screenshot(f'map-{width}x{height}')
            results['sizes'].append([width, height])
        check.send('resize 1280 720')
        hover(check, 654, 703)
        check.screenshot('fort-hover')
        check.send('key 111')
        check.room(92)
        assert not check.state()['plunderMapInput']
        check.send('key 27'); check.room(13)
        check.wait(lambda: check.state()['plunderMapInput'], 'map input restored')
        check.send('key 106')
        check.wait(lambda: not check.state()['plunderMapInput'], 'picker input')
        check.send('key 27')
        check.wait(lambda: check.state()['plunderMapInput'], 'picker closed')
        check.send('key 117')
        check.wait(lambda: not check.state()['plunderMapInput'], 'Look input')
        check.send('key 27')
        check.wait(lambda: check.state()['plunderMapInput'], 'Look closed')
        if args.transitions:
            for name, x, y, _, _ in LANDMARKS:
                if not results['destinations'][name]:
                    results['transitions'][name] = 'story-locked (matches original)'
                    continue
                check.save_load(2, 0, home)
                check.jump(13)
                check.wait(lambda: check.state()['plunderMapInput'], 'map input')
                state = hover(check, x, y)
                assert state['hoverObject'] == results['destinations'][name], (name, state)
                px, py = screen_point(check, x, y)
                check.send(f'click {px} {py}')
                check.wait(lambda: check.state()['room'] != 13, f'{name} travel', 45)
                assert check.state()['room'] == ROOMS[name], (name, check.state())
                results['transitions'][name] = check.state()['room']
                print(f'PASS {name} -> room {check.state()["room"]}', flush=True)
        check.save_load(2, 0, home)
        assert not check.state()['plunderMap'] and not check.state()['plunderMapInput']
    finally:
        check.close()
        (output / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
    # Removing the legacy map overlay must not require a shader mask. Exercise
    # both GPU water-off and the CPU fallback from a fresh engine allocation.
    results['renderModes'] = []
    for gpu in (True, False):
        check = Check(output / ('water-off-gpu' if gpu else 'water-off-cpu'),
                      hd_path=wide / 'hd', color_grades_path=grades,
                      config_overrides={'comi': {'hd_water_shader': 'false',
                                                 'hd_gpu_effects': str(gpu).lower()}})
        try:
            check.jump(13)
            check.wait(lambda: check.state().get('plunderMapInput'), 'map without water')
            assert hover(check, 355, 587)['hoverObject'] == results['destinations']['swamp']
            check.screenshot('swamp-hover')
            results['renderModes'].append('water-off-gpu' if gpu else 'water-off-cpu')
        finally:
            check.close()
            (output / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
    results['passed'] = True
    (output / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
