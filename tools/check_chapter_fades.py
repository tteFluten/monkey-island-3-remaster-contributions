#!/usr/bin/env python3
"""Check chapter-card fades through native framebuffer captures and copied saves.

Requires a built .playtest runtime and a playable slot-0 save. Room jumps check
presentation only; they do not validate chapter progression or alter user saves.
"""
import argparse
import json
from pathlib import Path
import time

from PIL import Image, ImageStat

from check_aspect import Check, ROOT

CHAPTER_ROOMS = (4, 5, 6, 7, 8, 88)


def captures(check, seconds):
    rows = []
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        before = set(check.output.glob('scummvm*.png'))
        (check.output / 'test-input.txt').write_text('screenshot\n')
        check.wait(lambda: bool(set(check.output.glob('scummvm*.png')) - before), 'framebuffer capture')
        path = next(iter(set(check.output.glob('scummvm*.png')) - before))
        # The file appears before PNG encoding finishes. Only measure complete images.
        def decoded():
            try:
                with Image.open(path) as image:
                    image.load()
                return True
            except OSError:
                return False
        check.wait(decoded, 'complete PNG')
        with Image.open(path) as image:
            brightness = ImageStat.Stat(image.convert('L')).mean[0]
        rows.append(dict(file=path.name, seconds=time.monotonic() - started,
                         brightness=brightness, room=check.state().get('room')))
        time.sleep(.05)
    return rows


def jump(check, room):
    command = dict(id=check.state().get('commandId', 0) + 1, action='jump', room=room)
    (check.output / 'command.json').write_text(json.dumps(command))


def run(output, room, aspect):
    check = Check(output, aspect, config_overrides={
        'comi': {'hd_gpu_effects': 'true'}, 'scummvm': {'hd_film_enabled': 'false'}})
    try:
        home = check.state()['room']
        assert home not in CHAPTER_ROOMS, 'Use a playable gameplay save as the fixture'
        # Smaller window keeps screenshot encoding from consuming the whole fade.
        check.send('resize 640 360')
        jump(check, room)
        check.wait(lambda: check.state().get('room') == room, 'chapter card')
        entering = captures(check, 2)
        check.room(room)
        assert check.state()['renderBackend'] == 'opengl-shaders'
        jump(check, home)
        leaving = captures(check, 3)
        check.room(home)
        report = dict(room=room, aspect=aspect, entering=entering, leaving=leaving)
        (output / 'samples.json').write_text(json.dumps(report, indent=2))
        peak = max(r['brightness'] for r in entering)
        assert peak > 10, (room, aspect, 'chapter card remained black')
        assert entering[0]['brightness'] < peak * .35, (room, aspect, 'entry did not start dark')
        assert entering[-1]['brightness'] > peak * .9, (room, aspect, 'entry did not finish')
        assert any(peak * .15 < r['brightness'] < peak * .85 for r in entering), (room, aspect, 'entry cut instead of fading')
        assert min(r['brightness'] for r in leaving) < peak * .15, (room, aspect, 'exit did not fade to black')
        assert any(r['room'] == home and r['brightness'] > 10 for r in leaving), (room, aspect, 'destination did not appear')
        assert any(r['room'] == room and peak * .15 < r['brightness'] < peak * .85 for r in leaving), (room, aspect, 'exit cut instead of fading')
        print(f'PASS chapter room {room:04}, aspect {aspect}: fade in, fade out, gameplay restored', flush=True)
        return dict(room=room, aspect=aspect, passed=True)
    finally:
        check.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/chapter-fades/native')
    parser.add_argument('--rooms', type=int, nargs='+', choices=CHAPTER_ROOMS, default=CHAPTER_ROOMS)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'result.json').unlink(missing_ok=True)
    results = []
    aspect = 169
    for room in args.rooms:
        results.append(run(output / f'{room:04}-{aspect}', room, aspect))
    (output / 'result.json').write_text(json.dumps(dict(passed=True, cases=results), indent=2))


if __name__ == '__main__':
    main()
