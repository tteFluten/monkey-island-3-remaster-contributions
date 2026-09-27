#!/usr/bin/env python3
"""Check native movie presentation using isolated configs, saves and HD overlays."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

from PIL import Image, ImageChops

from check_aspect import Check, ROOT


def capture(check, name):
    for stage in ('before', 'after'):
        (check.output / f'film-{stage}.png').unlink(missing_ok=True)
    check.send('film-capture')
    check.wait(lambda: (check.output / 'film-after.png').exists(), 'final framebuffer capture')
    check.send('window')  # Both PNGs are closed before the next input command.
    before = Image.open(check.output / 'film-before.png').convert('RGB')
    after = Image.open(check.output / 'film-after.png').convert('RGB')
    assert ImageChops.difference(before, after).getbbox(), (name, 'film effect inactive')
    # Existing film tuning is independent of aspect; verify that it still
    # affects the image while keeping presentation bars/encoded black intact.
    r, g, b = before.point(lambda value: 255 if value == 0 else 0).split()
    black = ImageChops.multiply(ImageChops.multiply(r, g), b)
    for channel in after.split():
        assert not ImageChops.multiply(channel, black).getbbox(), (name, 'black bars changed')
    for stage in ('before', 'after'):
        shutil.copyfile(check.output / f'film-{stage}.png', check.output / f'{name}-{stage}.png')
    print(f'PASS {name}: {before.size}, film active, black preserved', flush=True)


def start(check, name):
    command = check.output / 'movie.txt'
    command.write_text(name + '\n')
    check.wait(lambda: not command.exists(), 'movie command consumed')
    check.wait(lambda: check.window()['movieActive'], 'movie presentation active')


def restored(check, room, aspect):
    check.wait(lambda: not check.window()['movieActive'], 'movie presentation released', 30)
    check.room(room)
    expected = 864 if room == 15 else 640
    check.wait(lambda: check.state().get('viewportWidth') == expected, 'room viewport restored')
    assert 'hd_movie_active' not in (check.output / 'scummvm.ini').read_text()


def picture(check, name, aspect):
    capture(check, name)
    image = Image.open(check.output / f'{name}-before.png').convert('RGB')
    # SB020 fills the source frame. Detect its visible bounds independently
    # from the geometry helper to catch backend integration/pillarbox errors.
    bounds = image.point(lambda value: 255 if value > 8 else 0).getbbox()
    width, height = image.size
    numerator, denominator = (16, 9)
    w, h = width, width * denominator // numerator
    if h > height:
        h, w = height, height * numerator // denominator
    x, y = (width - w) // 2, (height - h) // 2
    expected = (x, y, x + w, y + h)
    assert bounds and all(abs(a - b) <= 2 for a, b in zip(bounds, expected)), (name, bounds, expected)
    return {'size': image.size, 'pictureBounds': bounds}


def hd_overlay(output, invalid=False):
    """Retain normal artwork without touching installed movie files."""
    output.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / '.playtest/hd').iterdir():
        destination = output / source.name
        if source.name != 'videos' and not destination.exists():
            destination.symlink_to(source.resolve(), target_is_directory=source.is_dir())
    (output / 'videos').mkdir(exist_ok=True)
    # A valid second movie checks recovery after an unavailable HD clip.
    movie = output / 'videos/BBSAN.mp4'
    if not movie.exists():
        movie.symlink_to(ROOT / '.playtest/hd/videos/BBSAN.mp4')
    if invalid:
        (output / 'videos/SB020.mp4').write_bytes(b'intentionally invalid decoder fixture')
    return output


def unavailable(check, room, aspect, source):
    marker = 'HD movie unavailable:' if source == 'missing' else 'HD video decode failed; skipping cinematic'
    log_path = check.output / 'engine.log'
    previous = log_path.read_text().count(marker)
    command = check.output / 'movie.txt'
    command.write_text('SB020.SAN\n')
    check.wait(lambda: not command.exists(), 'unavailable movie consumed')
    check.wait(lambda: log_path.read_text().count(marker) > previous, 'HD-only failure reported')
    check.wait(lambda: not check.window()['movieActive'], 'failed movie released before message')
    check.screenshot(f'{source}-message-room-{room}')
    check.send('key 13')  # Dismiss the clear, user-visible skip message.
    restored(check, room, aspect)
    assert 'using original movie' not in log_path.read_text()


def decoder_failure(output, grades):
    # Exercise a decoder that emits valid frames and then exits unsuccessfully.
    # This must skip with a message, rather than treating the failure as clean EOF.
    decoder = output / 'failing-decoder.py'
    decoder.write_text(f'#!{sys.executable}\n' + '''import sys
scale = sys.argv[sys.argv.index('-vf') + 1].split('=')[1].split(':')
width, height = map(int, scale[:2])
frame = bytes((24, 56, 96, 255)) * width * height
for _ in range(2):
    sys.stdout.buffer.write(frame)
sys.stdout.buffer.flush()
sys.exit(1)
''')
    decoder.chmod(0o755)
    check = Check(output / 'decoder-error', 169, color_grades_path=grades,
                  config_overrides={'comi': {'ffmpeg_path': str(decoder)}})
    try:
        check.jump(9)
        unavailable(check, 9, 169, 'decoder-error')
        assert 'retaining last image until native movie ends' not in (check.output / 'engine.log').read_text()
        print('PASS decoder error after valid frames: skipped with message, room restored', flush=True)
    finally:
        check.close()
    return {'skippedWithMessage': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/movie-check')
    parser.add_argument('--sources', nargs='+', choices=('hd', 'missing', 'invalid'),
                        default=('hd', 'missing', 'invalid'))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'result.json').unlink(missing_ok=True)
    grades = output / 'grades.json'
    shutil.copyfile(ROOT / 'data/color-grades.json', grades)
    results = {}
    for source in args.sources:
        hd_path = None if source == 'hd' else hd_overlay(output / f'{source}-assets', source == 'invalid')
        aspect = 169
        name = f'{source}-{aspect}'
        check = Check(output / name, aspect, hd_path=hd_path, color_grades_path=grades,
                      config_overrides={'scummvm': {'hd_film_enabled': 'true', 'hd_film_strength': '20'},
                                        'comi': {'subtitles': 'true'}})
        try:
            check.jump(9)
            check.send('resize 1280 720')
            if source == 'hd':
                start(check, 'SB020.SAN')
                results[name] = picture(check, 'movie', aspect)
                restored(check, 9, aspect)  # Native end of file, no skip.
                assert 'HD video: playing' in (check.output / 'engine.log').read_text()
                # Valid supplied clip omits ten trailing black frames.
                start(check, 'FG010GP.SAN')
                restored(check, 9, aspect)
                assert 'retaining last image until native movie ends' in (check.output / 'engine.log').read_text()
            else:
                unavailable(check, 9, aspect, source)
                results[name] = {'skippedWithMessage': True}
            # Immediately play another movie, then skip its long timeline.
            start(check, 'BBSAN.SAN')
            time.sleep(2)
            picture(check, 'second-movie', aspect)
            check.send('key 27')
            restored(check, 9, aspect)
            capture(check, 'fixed-room-return')
            check.jump(15)
            if source == 'hd':
                start(check, 'SB020.SAN')
                picture(check, 'from-panorama', aspect)
                restored(check, 15, aspect)
            else:
                unavailable(check, 15, aspect, source)
            capture(check, 'panorama-return')
            # Test fit on a taller window while a long movie is active.
            start(check, 'BBSAN.SAN')
            check.send('resize 960 800')
            picture(check, 'taller-window', aspect)
            check.send('fullscreen 1')
            picture(check, 'fullscreen', aspect)
            check.send('key 27')
            restored(check, 15, aspect)
            check.send('fullscreen 0')
            # Failed native open never enters the movie presentation.
            command = check.output / 'movie.txt'
            command.write_text('MISSING.SAN\n')
            check.wait(lambda: not command.exists(), 'missing movie consumed')
            restored(check, 15, aspect)
            print(f'PASS {name}: completion, skip, consecutive movies, room restoration, resize/fullscreen', flush=True)
        finally:
            check.close()
    results['decoder-error'] = decoder_failure(output, grades)
    (output / 'result.json').write_text(json.dumps({'passed': True, 'cases': results}, indent=2))


if __name__ == '__main__':
    main()
