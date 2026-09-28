#!/usr/bin/env python3
"""Native soft-follow regression checks, with copied saves and engine-local input."""
import argparse
import csv
import json
import time
from pathlib import Path

from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/camera-check')
    parser.add_argument('--cpu', action='store_true')
    parser.add_argument('--disabled', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    grades = output / 'grades.json'
    grades.write_text(json.dumps({'schemaVersion': 2, 'global': {}, 'rooms': {}}))
    check = Check(output, color_grades_path=grades, config_overrides={
        'comi': {'hd_gpu_effects': str(not args.cpu).lower(), 'hd_smooth_motion': str(not args.disabled).lower()},
        'scummvm': {'vsync': 'true', 'hd_film_enabled': 'false'}})
    passed = []
    enabled = not args.disabled

    def actor():
        return next(a for a in check.state()['actors'] if a['id'] == 1)

    def walk(x, y):
        before = (actor()['x'], actor()['y'])
        (output / 'walk-to.txt').write_text(f'{x} {y}\n')
        check.wait(lambda: not (output / 'walk-to.txt').exists(), 'walk command')
        check.wait(lambda: (actor()['x'], actor()['y']) != before, 'walker started')

    def settle():
        previous, since = None, time.monotonic()
        def stable():
            nonlocal previous, since
            state, guybrush = check.state(), actor()
            key = (guybrush['x'], guybrush['y'], state['visualCameraLeft'], state['visualCameraTop'])
            if key != previous:
                previous, since = key, time.monotonic()
            return (not state['cameraSettling']
                    and time.monotonic() - since > .5)
        check.wait(stable, 'walker and camera settled', 35)

    def record(name, seconds):
        (output / 'benchmark-start').touch()
        check.wait(lambda: not (output / 'benchmark-start').exists(), 'start camera samples')
        time.sleep(seconds)
        (output / 'benchmark-stop').touch()
        check.wait(lambda: not (output / 'benchmark-stop').exists() and (output / 'frames.csv').exists(), 'camera samples')
        path = output / f'{name}.csv'
        (output / 'frames.csv').replace(path)
        return list(csv.DictReader(path.open()))[1:]

    try:
        home = check.state()['room']
        check.jump(15)
        walk(650, 430)
        settle()
        assert check.state()['cameraFollow'] == enabled, check.state()
        settled = record('settled', 1)
        assert max(float(r['visual_camera_x']) for r in settled) - min(float(r['visual_camera_x']) for r in settled) < .01
        passed.append('settled camera stays at its displayed position across native ticks')
        walk(1450, 430)
        rows = record('walk', 4)
        poses = [float(r['visual_camera_x']) for r in rows]
        assert max(poses) - min(poses) > 50
        assert all(0 <= x <= 2096 - 864 for x in poses)
        if enabled:
            assert sum(abs(x - round(x)) > .0001 for x in poses) > len(poses) * .8
            assert all(r['camera_follow'] == '1' for r in rows)
        passed.append('walking stays within panorama bounds, with fractional motion when enabled')
        # Pointer mapping uses the displayed camera even while it differs from native.
        window = check.window()
        scale = min(window['height'], window['width'] * 9 / 16) / 480
        left = (window['width'] - 864 * scale) / 2
        for x in (window['width']//3, 2*window['width']//3):
            check.send(f'move {x} {window["height"]//2}')
            state = check.state()
            expected = state['inputCameraLeft'] + state['inputMouseX']
            assert abs(state['inputMouseX'] - (x-left)/scale) <= 2
            assert abs(state['mouseRoomX'] - expected) <= 3, (state, expected)
        passed.append('mouse-to-room mapping follows displayed camera during walking')
        # Reverse while moving, then wait for the native walker and spring independently.
        walk(650, 430)
        settle()
        check.screenshot('panorama')
        passed.append('direction reversal and stopping settle without lingering motion')
        check.save_load(1, 7, 15)
        check.send('key 105')
        check.wait(lambda: check.state()['inventoryOpen'], 'inventory')
        assert not check.state()['cameraFollow']
        check.send('key 105')
        check.wait(lambda: not check.state()['inventoryOpen'], 'inventory closed')
        check.jump(77)
        start = check.state()['visualCameraTop']
        (output / 'camera-sweep').touch()
        check.wait(lambda: abs(check.state()['visualCameraTop']-start)>30, 'vertical scripted pan', 30)
        assert not check.state()['cameraFollow']
        vertical = record('vertical', 2)
        assert len({r['visual_camera_y'] for r in vertical}) > 5
        if enabled:
            (output / 'motion-check').touch()
            check.wait(lambda: (output / 'motion-check.json').exists(), 'native endpoint replay', 30)
            assert json.loads((output / 'motion-check.json').read_text())['different_pixels'] == 0
        (output / 'camera-sweep').unlink()
        check.screenshot('vertical-water')
        passed.append('scripted vertical pan retains ownership and aligned native replay')
        check.save_load(2, 7, 15)
        settle()
        assert check.state()['cameraFollow'] == enabled
        check.save_load(2, 0, home)
        assert not check.state()['cameraFollow']
        passed.append('inventory, room transitions and save/load reset follow state')
        print(json.dumps({'passed': True, 'checks': passed}), flush=True)
    finally:
        (output / 'result.json').write_text(json.dumps({'passed': len(passed) == 6, 'checks': passed,
                                                       'state': check.state()}, indent=2))
        check.close()


if __name__ == '__main__':
    main()
