#!/usr/bin/env python3
"""Reproduce new-game fullscreen menu transitions with isolated settings/saves.

Requires an installed .playtest runtime. Loading a cannon save skips the
opening's GPU bootstrap updates and does not reproduce the scheduling bug.
"""
import argparse
import configparser
import json
import os
from pathlib import Path
import subprocess
import time

from check_aspect import Check, ROOT


class FreshGame(Check):
    def __init__(self, output, engine):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        saves = self.output / 'saves'
        saves.mkdir(exist_ok=True)
        for name in ('status.json', 'test-input.txt', 'test-window.json', 'film-before.png', 'result.json'):
            (self.output / name).unlink(missing_ok=True)
        config = configparser.ConfigParser(interpolation=None)
        config.read(ROOT / '.playtest/scummvm.ini')
        config['scummvm'].update(fullscreen='true', savepath=str(saves), screenshotpath=str(self.output))
        config['comi'].update(savepath=str(saves), playtest_session=str(self.output),
                              hd_color_grades_path=str(self.output / 'color-grades.json'))
        with (self.output / 'scummvm.ini').open('w') as handle:
            config.write(handle)
        self.log = (self.output / 'engine.log').open('w')
        environment = dict(os.environ, MI3_ENGINE_TEST_INPUT='1', MI3_ENGINE_TEST_EXCLUSIVE='1')
        environment.pop('MI3_ENGINE_TEST_WINDOWED', None)
        self.process = subprocess.Popen([str(engine.resolve()),
            '--config=' + str(self.output / 'scummvm.ini'), 'comi'], cwd=self.output,
            env=environment, stdout=self.log, stderr=self.log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/menu-fullscreen')
    parser.add_argument('--engine', type=Path, default=ROOT / '.playtest/engine/build/scummvm')
    args = parser.parse_args()
    check = FreshGame(args.output, args.engine)
    try:
        check.wait(lambda: check.state().get('room') == 87, 'difficulty screen', 40)
        window = check.window()
        assert window['fullscreen'], 'Regression must run in actual fullscreen'
        time.sleep(2)
        # The fullscreen difficulty painting fills the display vertically.
        # Let its script observe the hover before pressing the button.
        x, y = window['width'] // 2, round(window['height'] * 120 / 480)
        # Room 87 is reported before its introductory scripts enable clicks.
        for _ in range(10):
            check.send(f'move {x} {y}')
            check.send(f'down {x} {y}')
            check.send(f'up {x} {y}')
            if check.state().get('room') != 87:
                break
            time.sleep(.5)
        check.wait(lambda: check.state().get('room') != 87, 'start new game')
        deadline = time.monotonic() + 45
        while check.state().get('room') != 9 and time.monotonic() < deadline:
            check.send('key 27')  # Skip the opening movie/chapter card normally.
            time.sleep(1)
        assert check.state().get('room') == 9, check.state()
        for index, key in enumerate((111, 1073741886, 111)):  # O, F5, O again
            check.send(f'key {key}')
            check.room(92)
            # Entering room 92 alone is insufficient: the broken engine keeps
            # running menu scripts while leaving the gameplay frame onscreen.
            # This request is fulfilled only when the backend draws a frame.
            capture = check.output / 'film-before.png'
            capture.unlink(missing_ok=True)
            check.send('film-capture')
            check.wait(capture.exists, 'menu frame actually presented', 5)
            if index == 0:
                check.screenshot('fullscreen-options')
            check.send('key 27')
            check.wait(lambda: check.state().get('room') == 9, 'return to cannon')
        (check.output / 'result.json').write_text(json.dumps({'passed': True, 'fullscreen': True}))
        print('PASS: new-game fullscreen O/F5/repeated O visibly render the menu and return to room 0009')
    finally:
        check.close()


if __name__ == '__main__':
    main()
