#!/usr/bin/env python3
"""Exercise the native aspect controls using isolated saves and engine-local input.

Requires an existing .playtest runtime. Never sends OS-wide input, stages art,
changes the regular Playtest config, or modifies the user's saves.
"""
import argparse
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


class Check:
    def __init__(self, output, aspect=43):
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        for name in ('status.json', 'test-input.txt', 'test-window.json', 'command.json', 'save-load.txt'):
            (self.output / name).unlink(missing_ok=True)
        save_source = Path(os.environ.get('MI3_ASPECT_TEST_SAVES', str(ROOT / '.playtest/saves')))
        shutil.copytree(save_source, self.output / 'saves', dirs_exist_ok=True)
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read(ROOT / '.playtest/scummvm.ini')
        self.config['scummvm'].update({'savepath': str(self.output / 'saves'), 'screenshotpath': str(self.output),
                                      'fullscreen': 'false', 'last_window_width': '1280',
                                      'last_window_height': '720' if aspect == 169 else '960'})
        self.config['comi'].update({'savepath': str(self.output / 'saves'), 'playtest_session': str(self.output),
                                   'hd_aspect_ratio': str(aspect), 'hd_aspect_test_input': 'true',
                                   'hd_aspect_ui_path': str(ROOT / 'extracted/objects')})
        with (self.output / 'scummvm.ini').open('w') as handle:
            self.config.write(handle)
        self.log = (self.output / 'engine.log').open('w')
        self.process = subprocess.Popen([str(ROOT / '.playtest/engine/build/scummvm'),
            '--config=' + str(self.output / 'scummvm.ini'), '--save-slot=0', 'comi'], cwd=self.output,
            stdout=self.log, stderr=self.log, env=dict(os.environ, MI3_ENGINE_TEST_INPUT='1', MI3_ENGINE_TEST_EXCLUSIVE='1'))
        try:
            self.wait(lambda: self.state().get('ready'), 'engine ready', 45)
        except BaseException:
            self.close()
            raise

    def state(self):
        try:
            return json.loads((self.output / 'status.json').read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def wait(self, condition, description, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise AssertionError(f'Engine exited ({self.process.returncode}): {self.output / "engine.log"}')
            if condition():
                return
            time.sleep(.1)
        raise AssertionError(f'Timed out: {description}; {self.state()}')

    def send(self, text):
        p = self.output / 'test-input.txt'
        p.write_text(text + '\n')
        self.wait(lambda: not p.exists(), text)
        time.sleep(.35)

    def window(self):
        self.send('window')
        return json.loads((self.output / 'test-window.json').read_text())

    def click_game(self, x, y):
        window = self.window()
        aspect = self.state()['aspectRatio']
        h = min(window['height'], window['width'] * (9 / 16 if aspect == 169 else 3 / 4))
        width = self.state()['viewportWidth'] * h / 480
        left, top = (window['width'] - width) / 2, (window['height'] - h) / 2
        px, py = round(left + x * h / 480), round(top + y * h / 480)
        self.send(f'down {px} {py}')
        self.send(f'up {px} {py}')

    def room(self, room):
        self.wait(lambda: self.state().get('ready') and self.state().get('room') == room, f'room {room}')

    def jump(self, room):
        command = {'id': self.state().get('commandId', 0) + 1, 'action': 'jump', 'room': room}
        (self.output / 'command.json').write_text(json.dumps(command))
        self.wait(lambda: self.state().get('commandId') == command['id'], 'jump acknowledged')
        self.room(room)
        time.sleep(.8)

    def screenshot(self, name):
        time.sleep(2)  # Let the preceding screenshot's OSD disappear.
        before = set(self.output.glob('scummvm*.png'))
        self.send('screenshot')
        self.wait(lambda: bool(set(self.output.glob('scummvm*.png')) - before), 'screenshot')
        source = next(iter(set(self.output.glob('scummvm*.png')) - before))
        time.sleep(.5)
        shutil.copyfile(source, self.output / (name + '.png'))

    def save_load(self, action, slot, room):
        path = self.output / 'save-load.txt'
        path.write_text(f'{action} {slot}\n')
        self.wait(lambda: not path.exists(), 'save/load consumed')
        consumed_at = time.time_ns()
        self.wait(lambda: (self.output / 'status.json').stat().st_mtime_ns > consumed_at,
                  'save/load completed')
        time.sleep(.5)
        self.room(room)

    def select(self, aspect, key=111):
        room = self.state()['room']
        self.send(f'key {key}')
        self.room(92)
        assert self.state()['viewportWidth'] == 640, self.state()
        self.click_game(155 if aspect == 43 else 225, 412)
        self.wait(lambda: self.state().get('aspectRatio') == aspect, f'select {aspect}')
        self.config.read(self.output / 'scummvm.ini')
        assert self.config.getint('comi', 'hd_aspect_ratio') == aspect
        self.screenshot(f'menu-{aspect}')
        self.send('key 27')
        self.room(room)

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.log.close()


def interactions(check):
    check.jump(15)
    time.sleep(3)
    assert check.state()['viewportWidth'] == 864
    check.save_load(1, 7, 15)
    assert (check.output / 'saves/comi.s07').is_file()
    check.select(43)
    check.save_load(2, 7, 15)
    assert check.state()['viewportWidth'] == 640
    check.select(169)
    check.save_load(2, 0, 9)
    check.save_load(2, 7, 15)
    assert check.state()['viewportWidth'] == 864
    print('PASS: native save/load across both modes and menu restoration', flush=True)
    window = check.window()
    h = min(window['height'], window['width'] * 9 / 16)
    scale = h / 480
    left = (window['width'] - 864 * scale) / 2
    for x in (1, window['width'] - 2):
        check.send(f'move {x} {round(window["height"] / 2)}')
        state = check.state()
        expected = state['cameraLeft'] + (x - left) / scale
        assert abs(state['mouseRoomX'] - expected) <= 2, (state, expected)
    actor = next(a for a in check.state()['actors'] if a['id'] == 1)
    start_x = actor['x']
    target = 1450 if start_x < 1000 else 650
    (check.output / 'walk-to.txt').write_text(f'{target} 430\n')
    check.wait(lambda: any(a['id'] == 1 and abs(a['x'] - start_x) > 20
                          for a in check.state().get('actors', [])), 'native actor walking')
    (check.output / 'motion-check').write_text('')
    check.wait(lambda: (check.output / 'motion-check.json').exists(), 'interpolated replay', 30)
    replay = json.loads((check.output / 'motion-check.json').read_text())
    assert replay['different_pixels'] == 0, replay
    check.screenshot('panorama-walking')
    print('PASS: panorama edge input, native walking, pixel-identical motion replay', flush=True)
    check.send('key 105')  # Original inventory shortcut.
    check.wait(lambda: check.state()['viewportWidth'] == 640, 'centered inventory')
    check.screenshot('inventory-169')
    check.send('key 105')
    check.wait(lambda: check.state()['viewportWidth'] == 864, 'panorama after inventory')
    check.send('resize 960 800')
    check.screenshot('resized-169')
    check.send('fullscreen 1')
    check.screenshot('fullscreen-169')
    check.send('fullscreen 0')
    check.send('resize 1280 720')
    assert check.state()['viewportWidth'] == 864
    print('PASS: inventory shortcut, resize, fullscreen and return', flush=True)
    movie = check.output / 'movie.txt'
    movie.write_text('SB020.SAN\n')
    check.wait(lambda: not movie.exists(), 'movie consumed')
    check.send('screenshot')
    time.sleep(5)
    check.room(15)
    assert check.state()['viewportWidth'] == 864
    assert 'HD video: playing' in (check.output / 'engine.log').read_text()
    check.screenshot('movie-return-169')
    print('PASS: cinematic framing and restored panorama', flush=True)
    check.save_load(2, 0, 9)
    # Drag release must pair with its center press even outside the game area.
    check.send('down 640 600')
    check.send('up 10 200')
    lines = [line for line in (check.output / 'engine.log').read_text().splitlines()
             if 'HD-ASPECT input' in line]
    assert 'accepted type=5' in lines[-1], lines[-2:]
    check.screenshot('cannon-final-169')
    print('PASS: center press released in margin', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/widescreen/native')
    parser.add_argument('--all-panoramas', action='store_true')
    parser.add_argument('--rooms', type=int, nargs='+', help='Check only these rooms, starting in 16:9')
    parser.add_argument('--interactions', action='store_true', help='Save/load, movement, movie and window checks')
    args = parser.parse_args()
    check = Check(args.output, 169 if args.rooms or args.interactions else 43)
    try:
        if args.interactions:
            interactions(check)
            (check.output / 'result.json').write_text(json.dumps({'passed': True, 'interactions': True}))
            return
        if args.rooms:
            for room in args.rooms:
                check.save_load(2, 0, 9)
                check.jump(room)
                check.screenshot(f'room-{room}-169')
                assert check.state()['backgroundLoaded'], check.state()
                print(f'PASS: room {room}: {check.state()["viewportWidth"]}, HD background loaded', flush=True)
            (check.output / 'result.json').write_text(json.dumps({'passed': True, 'rooms': args.rooms}, indent=2))
            return
        check.jump(9)
        check.screenshot('cannon-43')
        check.select(169)
        assert check.state()['viewportWidth'] == 640
        check.screenshot('cannon-169')
        print('PASS: cannon, O/options, 16:9 preference, Escape', flush=True)
        check.send('move 10 200')
        check.send('down 10 200')
        check.send('up 10 200')
        assert 'HD-ASPECT input blocked' in (check.output / 'engine.log').read_text()
        check.screenshot('margin-cursor')
        check.jump(15)
        assert check.state()['viewportWidth'] == 864
        assert 0 <= check.state()['cameraLeft'] <= 2096 - 864
        check.screenshot('puerto-169')
        check.select(43, 1073741886)
        assert check.state()['viewportWidth'] == 640
        check.screenshot('puerto-43')
        check.select(169)
        assert check.state()['viewportWidth'] == 864
        print('PASS: Puerto Pollo, F5/options, both viewports, restored HD background', flush=True)
        rooms = [(14, 864), (53, 864), (77, 640), (40, 640), (9, 640)]
        if args.all_panoramas:
            rooms = []
            for path in (ROOT / 'data/scenes').glob('*.json'):
                manifest = json.loads(path.read_text())
                for asset in manifest.get('assets', {}).values():
                    if asset.get('type') == 'background' and asset.get('width', 0) >= 864 and asset.get('height') == 480:
                        rooms.append((manifest['scene']['roomNumber'], 864))
            rooms = sorted(set(rooms)) + [(77, 640), (40, 640), (9, 640)]
        for room, width in rooms:
            # Debugger room jumps do not initialize chapter/puzzle state.
            # Reload the copied known save between unrelated scenes.
            check.save_load(2, 0, 9)
            check.jump(room)
            assert check.state()['viewportWidth'] == width, check.state()
            assert check.state()['backgroundLoaded'], check.state()
            check.screenshot(f'room-{room}-169')
            print(f'PASS: room {room}, viewport {width}, HD background loaded', flush=True)
        (check.output / 'result.json').write_text(json.dumps({'passed': True, 'rooms': rooms}, indent=2))
    finally:
        check.close()


if __name__ == '__main__':
    main()
