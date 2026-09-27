#!/usr/bin/env python3
"""Audit every water room in the native 16:9 renderer, using copied saves/settings."""
import argparse
import json
from pathlib import Path

from check_aspect import Check, ROOT

CATALOG = ROOT / 'tools/engine/water_regions.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/water-check')
    parser.add_argument('--rooms', type=int, nargs='+')
    parser.add_argument('--screenshots', action='store_true')
    parser.add_argument('--interactions', action='store_true', help='Check water controls and tall-room camera movement')
    parser.add_argument('--fallback', action='store_true', help='Verify the shader-disabled rendering path')
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text())
    rooms = args.rooms or sorted(map(int, [*catalog['existing'], *catalog['regions']]))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    grades = output / 'grades.json'
    grades.write_text(json.dumps({'schemaVersion': 2, 'global': {}, 'rooms': {}}))
    check = Check(output, color_grades_path=grades, config_overrides={
        'comi': {'hd_gpu_effects': 'true', 'hd_water_shader': str(not args.fallback).lower()},
        'scummvm': {'hd_film_enabled': 'false'}})
    expected = 'original-overlays' if args.fallback else 'opengl-shader'
    home = check.state()['room']
    results = []
    try:
        for room in rooms:
            check.save_load(2, 0, home)
            command = {'id': check.state().get('commandId', 0) + 1, 'action': 'jump', 'room': room}
            (output / 'command.json').write_text(json.dumps(command))
            check.wait(lambda: check.state().get('commandId') == command['id'], 'jump acknowledged')
            check.wait(lambda: check.state().get('room') == room and
                       check.state().get('waterBackend') == expected, f'room {room} {expected}', 30)
            state = check.state()
            assert not state.get('error'), state
            assert state['backgroundLoaded'] and state['renderBackend'] == 'opengl-shaders', state
            if args.screenshots:
                check.screenshot(f'water-{room:04}')
            if args.interactions:
                check.send('key 119')  # W: water page, including newly mapped rooms.
                check.send('key 1073741904')  # SDL Left: reduce strength from its inherited default.
                saved = json.loads(grades.read_text())
                assert saved['rooms'][str(room)]['waterOpacity'] == 95, saved
                if args.screenshots:
                    check.screenshot(f'controls-{room:04}')
                check.send('key 114')  # R restores water inheritance only.
                saved = json.loads(grades.read_text())
                assert 'waterOpacity' not in saved['rooms'].get(str(room), {}), saved
                check.send('key 27')
                if room == 77:
                    start = check.state()['cameraTop']
                    (output / 'camera-sweep').touch()
                    try:
                        check.wait(lambda: abs(check.state()['cameraTop'] - start) > 100,
                                   'vertical water coverage follows camera', 30)
                        assert check.state()['waterBackend'] == expected, check.state()
                        if args.screenshots:
                            check.screenshot('water-0077-scrolled')
                    finally:
                        (output / 'camera-sweep').unlink(missing_ok=True)
            results.append({'room': room, 'waterBackend': state['waterBackend'],
                            'viewportWidth': state['viewportWidth'], 'cameraTop': state['cameraTop']})
            print(f'PASS room {room}: {expected}, viewport {state["viewportWidth"]}', flush=True)
    finally:
        check.close()
        (output / 'result.json').write_text(json.dumps({'passed': len(results) == len(rooms),
                                                      'requested': rooms, 'rooms': results}, indent=2))


if __name__ == '__main__':
    main()
