#!/usr/bin/env python3
"""Check inventory centering and stable presentation using isolated copied saves.

Uses the native engine-local input hook; never sends desktop-wide input.
MI3_ASPECT_TEST_SAVES selects the fixture directory containing comi.s00.
"""
import argparse
import json
from pathlib import Path

from check_aspect import Check, ROOT
from check_wide_background import sides


def toggle(check, opened):
    check.send('key 105')
    check.wait(lambda: check.state().get('inventoryOpen') == opened, 'inventory toggle')


def cycle(check, name, wide_sides=False):
    backend = 'opengl-shaders' if check.config['comi'].getboolean('hd_gpu_effects') else 'cpu-effects'
    check.wait(lambda: check.state()['renderBackend'] == backend, 'presentation ready')
    window = check.window()
    before = check.state()
    toggle(check, True)
    after = check.state()
    for key in ('aspectRatio', 'outputWidth', 'outputHeight', 'viewportWidth',
                'viewportHeight', 'cameraLeft', 'cameraTop', 'renderBackend'):
        assert after[key] == before[key], (name, key, before[key], after[key])
    assert check.window() == window, name
    expected_offset = max(0, (after['viewportWidth'] - 640) // 2)
    assert after['inventoryOffset'] == expected_offset
    # In 1280x720 the physical center maps to native inventory x=320,
    # even when the room viewport is 864 pixels wide.
    if window['width'] == 1280 and window['height'] == 720:
        check.send('move 640 360')
        assert abs(check.state()['mouseScriptX'] - 320) <= 1, check.state()
    if wide_sides:
        sides(check, name)
    else:
        check.screenshot(name)
    toggle(check, False)
    assert check.state()['viewportWidth'] == before['viewportWidth']
    assert check.state()['inventoryOffset'] == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/inventory-check')
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    grades = output / 'color-grades.json'
    grades.write_text(json.dumps({'schemaVersion': 1, 'rooms': {}}))
    check = Check(output, 169, color_grades_path=grades,
                  config_overrides={'comi': {'hd_gpu_effects': str(not args.cpu).lower()}})
    try:
        if check.state()['room'] != 9:
            check.jump(9)
        if check.state()['inventoryOpen']:
            toggle(check, False)
        cycle(check, 'cannon-169', wide_sides=True)
        check.send('resize 960 800')
        cycle(check, 'cannon-tall-window')
        check.send('fullscreen 1')
        cycle(check, 'cannon-fullscreen')
        check.send('fullscreen 0')
        check.send('resize 1280 720')
        check.select(43)
        cycle(check, 'cannon-43')
        check.select(169)
        check.jump(15)
        check.wait(lambda: check.state()['viewportWidth'] == 864, 'panorama')
        cycle(check, 'panorama-169')
        cycle(check, 'panorama-reopened')
        (output / 'result.json').write_text(json.dumps({'ok': True, 'gpu': not args.cpu,
            'checks': ['unchanged framing and camera', 'centered inventory input', 'wide background retained',
                       'tall window', 'fullscreen', '4:3', 'panorama', 'reopen']}, indent=2) + '\n')
        print('PASS: centered inventory, stable presentation and pointer mapping')
    finally:
        check.close()


if __name__ == '__main__':
    main()
