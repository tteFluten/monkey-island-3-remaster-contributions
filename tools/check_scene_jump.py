#!/usr/bin/env python3
"""Exercise the J picker with isolated saves and engine-local keyboard/mouse input.

Requires a built .playtest runtime and a cannon save in MI3_ASPECT_TEST_SAVES.
Screenshots and test saves are written only below .context/scene-jump/native.
"""
import argparse
import json
from pathlib import Path

from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/scene-jump/native')
    args = parser.parse_args()
    aspect = 169
    output = args.output / str(aspect)
    output.mkdir(parents=True, exist_ok=True)
    grades = output / 'color-grades.json'
    grades.write_text('{"schemaVersion":2,"global":{},"rooms":{}}')
    check = Check(output, aspect, color_grades_path=grades)
    key = lambda code: check.send(f'key {code}')
    try:
        check.jump(9)
        key(106)  # J
        check.screenshot('cannon-picker')
        # Other overlay and gameplay keys cannot reach the game.
        for code in (105, 111, 1073741886, 117):  # I, O, F5, U
            key(code)
            assert check.state()['room'] == 9 and not check.state()['inventoryOpen']
        key(13)  # Current room closes, without re-entering its script.
        check.room(9)
        key(106); key(27); key(106); key(106)  # Esc and J both close.
        key(117); key(106)  # Replace Scene Look with J.
        check.screenshot('replaces-look-panel')
        # The next row is room 10. Wheel down then up must return to room 9.
        check.send('wheel -1'); check.send('wheel 1')
        for _ in range(6): key(1073741905)  # Down to town (room 15).
        key(13)
        check.room(15)
        check.screenshot('town-after-keyboard-jump')
        key(106)
        check.screenshot('panorama-picker')
        # Opening selected town keeps the first page visible. Click cannon.
        check.click_game(check.state()['viewportWidth'] / 2, 84 + 4 + 3 * 16 + 8)
        check.room(9)
        # Page navigation reaches a later chapter; current 9 -> 57 -> 61.
        key(106)
        for _ in range(4): key(1073741902)  # Page Down, 12 entries each.
        for _ in range(4): key(1073741905)
        key(13)
        check.room(61)
        key(106)
        check.screenshot('hotel-picker')
        key(27)
        # Outside the picker, inventory and options retain normal behavior.
        key(105)
        check.wait(lambda: check.state().get('inventoryOpen'), 'inventory opens')
        key(106)
        assert check.state()['inventoryOpen']
        key(105)
        check.wait(lambda: not check.state().get('inventoryOpen'), 'inventory closes')
        key(111)
        check.wait(lambda: check.state().get('room') == 92, 'options book opens')
        key(106)
        assert check.state()['room'] == 92
        key(27)
        check.room(61)
        # Existing workshop jumps remain functional with the picker open.
        key(106)
        check.jump(9)
        key(106)
        check.screenshot('picker-after-workshop-jump')
        key(27)
        (output / 'result.json').write_text(json.dumps({'passed': True, 'aspect': aspect}))
        print(f'PASS: {aspect} keyboard, mouse, wheel, pages, overlay isolation and repeated jumps', flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
