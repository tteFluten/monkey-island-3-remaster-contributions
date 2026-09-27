#!/usr/bin/env python3
"""Native options-book checks: 16:9 artwork, layout, controls, Quit prompt, pages.

Uses copied saves, an isolated config and engine-local input (see check_aspect).
Requires an installed room 92 widescreen sidecar and a cannon-room slot-0 save.
Positions are the book's new layout (tools/engine/hd_book_layout.h), in
original 640x480 coordinates.
"""
import argparse
import configparser
import json
from pathlib import Path
import time

from PIL import Image, ImageChops, ImageDraw, ImageStat
from check_aspect import Check, ROOT
from check_wide_background import sides

SAVE, LOAD, QUIT = (496, 197), (496, 245), (496, 341)


def tile(number):
    """Save/Load spread tile 1-6: (click point, thumbnail box, number box)."""
    left, top = (83, 445)[(number - 1) // 3], (56, 184, 312)[(number - 1) % 3]
    return (left + 72, top + 56), (left + 1, top + 1, left + 139, top + 104), (left - 34, top, left - 6, top + 18)
TEXT_BOX = (160, 358, 184, 382)          # [x] Text, beside [x] Voice
EFFECTS_KNOB_Y = 103                     # Effects Volume knob centre row
SIZE_Y = 333                             # Text Size slider bar

PROMPT = (120, 190, 520, 281)  # COMI quit prompt box.
CAPTION = (0, 420, 640, 480)   # Hover caption ("object line") band.


def size_x(percent):
    return 48 + (percent - 25) * 184 // 75 + 8


def game_rect(image):
    """Screenshot rectangle of the centered 640x480 gameplay surface."""
    w, h = image.size
    fh = min(h, w * 9 // 16)
    return (w - fh * 4 // 3) / 2, (h - fh) / 2, fh / 480


def region(image, box):
    left, top, scale = game_rect(image)
    x0, y0, x1, y1 = box
    return image.crop((round(left + x0 * scale), round(top + y0 * scale), round(left + x1 * scale), round(top + y1 * scale)))


def difference(a, b):
    return max(ImageStat.Stat(ImageChops.difference(a, b)).mean)


def masked_difference(a, b, *exclude):
    """Mean RGB difference with native-coordinate rectangles blanked out."""
    a, b = a.copy(), b.copy()
    left, top, scale = game_rect(a)
    for x0, y0, x1, y1 in exclude:
        box = (left + x0 * scale, top + y0 * scale, left + x1 * scale, top + y1 * scale)
        for image in (a, b):
            ImageDraw.Draw(image).rectangle(box, fill=0)
    return difference(a, b)


def painting_difference(check, image, box, art='backgrounds/bg_0092.png', origin=(0, 0)):
    """Mean RGB difference between a native-coordinate box and HD artwork."""
    actual = region(image, box)
    painting = Image.open(check.config['comi']['hd_path'] + '/' + art).convert('RGB')
    x0, y0, x1, y1 = box
    ox, oy = origin
    wanted = painting.crop(((x0 - ox) * 4, (y0 - oy) * 4, (x1 - ox) * 4, (y1 - oy) * 4)).resize(actual.size, Image.Resampling.BILINEAR)
    return difference(actual, wanted)


def shot(check, name):
    check.screenshot(name)
    return Image.open(check.output / (name + '.png')).convert('RGB')


def cursor(point, radius=40):
    return point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius


def window_point(check, point):
    window = check.window()
    h = min(window['height'], window['width'] * 9 / 16)
    width = check.state()['viewportWidth'] * h / 480
    return round((window['width'] - width) / 2 + point[0] * h / 480), round((window['height'] - h) / 2 + point[1] * h / 480)


def hover(check, point):
    px, py = window_point(check, point)
    check.send(f'move {px} {py}')
    time.sleep(1)  # Book scripts pick the hovered object on a later tick.
    return px, py


def hover_click(check, point):
    px, py = hover(check, point)
    check.send(f'down {px} {py}')
    time.sleep(.3)
    check.send(f'up {px} {py}')


def drag(check, start, end):
    px, py = hover(check, start)
    check.send(f'down {px} {py}')
    time.sleep(.3)
    for step in range(1, 5):
        x = start[0] + (end[0] - start[0]) * step // 4
        y = start[1] + (end[1] - start[1]) * step // 4
        qx, qy = window_point(check, (x, y))
        check.send(f'move {qx} {qy}')
    check.send(f'up {qx} {qy}')
    time.sleep(1)


def config_value(check, key):
    config = configparser.ConfigParser(interpolation=None)
    config.read(check.output / 'scummvm.ini')
    return config.get('comi', key, fallback=None)


def log_lines(check, text):
    return [line for line in (check.output / 'engine.log').read_text().splitlines() if text in line]


def open_book(check):
    check.send('key 111')
    check.room(92)
    time.sleep(1)


def leave_book(check, room):
    for _ in range(3):
        check.send('key 27')
        try:
            check.room(room)
            return
        except AssertionError:
            pass
    raise AssertionError('Options book did not close')


def prompt_shot(check, name):
    # A paused, unchanged frame is not redrawn, and ScummVM captures on redraw:
    # nudge the pointer one pixel (inside the cursor mask) first.
    hover(check, (QUIT[0] + 1, QUIT[1]))
    return shot(check, name)


def quit_prompt(check):
    count = len(log_lines(check, 'HD banner: retained frame'))
    for _ in range(2):  # The harness's first synthetic click can miss a script tick.
        hover_click(check, QUIT)
        time.sleep(1.5)
        if len(log_lines(check, 'HD banner: retained frame')) > count: break
    prompt = prompt_shot(check, 'quit-prompt')
    assert len(log_lines(check, 'HD banner: retained frame')) > count, 'Quit prompt did not open'
    assert not log_lines(check, 'no retained frame'), 'Banner fell back to a fresh composite'
    return prompt


def layout(check, book):
    # Painted margins, and the painting's own gutter: no bookmark ribbon over it.
    assert painting_difference(check, book, (8, 100, 40, 300)) < 8, 'left margin differs from the HD painting'
    assert painting_difference(check, book, (250, 0, 302, 480)) < 8, 'gutter differs from the HD painting'
    # Under the table of contents only the language row; no Display/3D rows below the toggles.
    assert painting_difference(check, book, (404, 380, 428, 404)) > 8, 'language row missing'
    assert painting_difference(check, book, (384, 408, 624, 418)) < 8, 'right page below the language row is not empty'
    assert painting_difference(check, book, (40, 414, 240, 420)) < 8, 'left page below the toggles is not empty'
    # Text Size slider is drawn like the other sliders: bar across, knob on it.
    bar = region(book, (60, SIZE_Y - 4, 140, SIZE_Y + 4))  # Left of both knobs.
    speed = region(book, (60, 273, 140, 281))              # Text Speed bar.
    assert difference(bar.resize(speed.size), speed) < 30, 'Text Size bar does not match the book sliders'
    print('PASS: options layout, painted margins and gutter, removed rows', flush=True)


def text_offset(image, box):
    """Native-pixel offset of the yellow banner text's centre from the box centre."""
    left, top, scale = game_rect(image)
    crop = region(image, box)
    ink = crop.point(lambda v: 255 if v > 170 else 0).split()[1]  # Yellow glyph fill: high green.
    ink = ImageChops.multiply(ink, crop.split()[0].point(lambda v: 255 if v > 200 else 0))
    bounds = ink.getbbox()
    assert bounds, ('no banner text in', box)
    return ((bounds[0] + bounds[2]) / 2 - crop.width / 2) / scale, ((bounds[1] + bounds[3]) / 2 - crop.height / 2) / scale


def prompt_checks(check, book):
    window = check.window()
    check.send(f'move {window["width"] // 2} {window["height"] // 2}')
    prompt = quit_prompt(check)
    diff = masked_difference(book, prompt, PROMPT, cursor(QUIT), cursor((320, 240)), CAPTION)
    assert diff < 2, ('book changed behind the quit prompt', diff)
    # Message centred above the buttons; labels centred in Yes and No (inside bevels).
    for name, box in (('message', (121, 191, 519, 240)), ('Yes', (161, 241, 279, 269)), ('No', (361, 241, 479, 269))):
        dx, dy = text_offset(prompt, box)
        assert abs(dx) <= 1.5 and abs(dy) <= 1.5, (name, 'banner text off centre', dx, dy)
    print('PASS: Quit prompt text centred in its box and buttons', flush=True)
    again = prompt_shot(check, 'quit-prompt-again')
    # ScummVM's screenshot notice can overlap the prompt; the book must not move.
    assert masked_difference(prompt, again, PROMPT, cursor(QUIT)) < 1, 'paused frame changed'
    check.send('key 110')  # "n": No.
    time.sleep(2.5)
    after = shot(check, 'quit-no')
    assert check.state().get('room') == 92 and check.process.poll() is None
    diff = masked_difference(book, after, cursor(QUIT), cursor((320, 240)), CAPTION)
    assert diff < 2, ('book not restored after No', diff)
    print(f'PASS: book intact behind the Quit prompt and after No ({diff:.3f})', flush=True)
    # A click elsewhere (on the Text Size slider) answers No and must not
    # reach the book behind the prompt.
    size = config_value(check, 'hd_font_size')
    quit_prompt(check)
    hover_click(check, (size_x(100), SIZE_Y))
    time.sleep(2.5)
    assert config_value(check, 'hd_font_size') == size, 'Text Size changed behind the prompt'
    assert check.state().get('room') == 92
    print('PASS: the prompt blocks book controls', flush=True)


def pages(check):
    for name, point in (('save', SAVE), ('load', LOAD)):
        hover_click(check, point)
        time.sleep(2)
        page = shot(check, f'{name}-page')
        # The HD painting replaces the native Save/Load spread, and no options
        # control is drawn over the slots.
        for box in ((8, 100, 50, 300), (290, 120, 350, 300), (8, 324, 50, 455), (600, 330, 632, 360)):
            diff = painting_difference(check, page, box)
            assert diff < 8, (name, 'page area differs from the HD painting', box, diff)
        sides(check, f'{name}-page-169')
        leave_book(check, 9)
        open_book(check)
    print('PASS: Save and Load pages open from their new positions', flush=True)
    save_round_trip(check)


def save_round_trip(check):
    # Save into slot 2 through the book: its HD thumbnail is written beside the
    # save and shown, smooth and full resolution, on the Load page.
    saves = check.output / 'saves'
    for old in saves.glob('comi.s02*'):
        old.unlink()
    hover_click(check, SAVE)
    time.sleep(2)
    hover_click(check, tile(2)[0])
    time.sleep(2)
    for key in 'hd':
        check.send(f'key {ord(key)}')
    check.send('key 13')
    check.room(9)
    time.sleep(1)
    thumbs = sorted(saves.glob('comi.s02.hd.*.png'))
    assert (saves / 'comi.s02').is_file() and len(thumbs) == 1, sorted(p.name for p in saves.iterdir())
    open_book(check)
    hover_click(check, LOAD)
    time.sleep(2)
    hover(check, (320, 20))
    page = shot(check, 'load-hd-thumbnail')
    actual = region(page, tile(3)[1])  # The Load page lists the autosave first.
    image = Image.open(thumbs[0]).convert('RGB').resize(actual.size, Image.Resampling.BILINEAR)
    diff = min(difference(actual, image.point(lambda v, f=f: v * f // 255)) for f in (175, 255))
    assert diff < 12, ('slot 2 does not show its HD thumbnail', diff)
    print(f'PASS: book save writes an HD thumbnail and the Load page shows it ({diff:.2f})', flush=True)
    # The page corner still turns to slots 7-12, and back.
    numbers = region(page, (410, 50, 440, 72))
    hover_click(check, (620, 250))
    time.sleep(2)
    hover(check, (320, 20))
    turned = shot(check, 'load-page-2')
    assert difference(numbers, region(turned, (410, 50, 440, 72))) > 2, 'page corner did not turn the page'
    hover_click(check, (20, 250))
    time.sleep(2)
    hover(check, (320, 20))
    back = shot(check, 'load-page-1')
    assert difference(numbers, region(back, (410, 50, 440, 72))) < 2, 'left page corner did not turn back'
    print('PASS: page corners turn the slot pages both ways', flush=True)
    leave_book(check, 9)
    open_book(check)


def autosave(check):
    # A chapter card followed by a playable room writes the autosave (slot 0)
    # with its HD thumbnail; the Load page lists it first, without a number,
    # and loads it. The Save page keeps its numbering.
    saves = check.output / 'saves'
    before = (saves / 'comi.s00').stat().st_mtime if (saves / 'comi.s00').exists() else 0
    check.jump(4)
    time.sleep(2)
    check.jump(9)
    check.wait(lambda: (saves / 'comi.s00').exists() and (saves / 'comi.s00').stat().st_mtime > before,
               'chapter autosave', 20)
    time.sleep(1)
    thumbs = sorted(saves.glob('comi.s00.hd.*.png'))
    assert len(thumbs) == 1, sorted(p.name for p in saves.iterdir())
    print('PASS: chapter change writes the autosave and its HD thumbnail', flush=True)
    open_book(check)
    hover_click(check, SAVE)
    time.sleep(2)
    hover(check, (320, 20))
    saving = shot(check, 'autosave-save-page')
    assert painting_difference(check, saving, tile(1)[2]) > 8, 'Save page lost its first tile number'
    leave_book(check, 9)
    check.jump(15)
    open_book(check)
    hover_click(check, LOAD)
    time.sleep(2)
    hover(check, (320, 20))
    loading = shot(check, 'autosave-load-page')
    assert painting_difference(check, loading, tile(1)[2]) < 8, 'autosave tile shows a number'
    assert painting_difference(check, loading, tile(2)[2]) > 8, 'second tile lost its number'
    actual = region(loading, tile(1)[1])
    image = Image.open(thumbs[0]).convert('RGB').resize(actual.size, Image.Resampling.BILINEAR)
    diff = min(difference(actual, image.point(lambda v, f=f: v * f // 255)) for f in (175, 255))
    assert diff < 12, ('autosave tile does not show its HD thumbnail', diff)
    hover_click(check, tile(1)[0])
    check.room(9)
    print(f'PASS: Load page lists the autosave first and loads it ({diff:.2f})', flush=True)


def controls(check):
    # Hover caption follows the moved Quit entry.
    idle = shot(check, 'caption-idle')
    hover(check, QUIT)
    time.sleep(1)
    caption = shot(check, 'caption-quit')
    assert difference(region(idle, CAPTION), region(caption, CAPTION)) > 1, 'no hover caption for Quit'
    # Text Size slider: click sets the nearest 5% step and moves the knob.
    for percent in (100, 40, 65):
        hover_click(check, (size_x(percent), SIZE_Y))
        time.sleep(1.5)
        assert config_value(check, 'hd_font_size') == str(percent), (percent, config_value(check, 'hd_font_size'))
        shot(check, f'text-size-{percent}')
    drag(check, (size_x(65), SIZE_Y), (size_x(85), SIZE_Y + 40))
    assert config_value(check, 'hd_font_size') == '85', config_value(check, 'hd_font_size')
    drag(check, (size_x(85), SIZE_Y), (size_x(65), SIZE_Y))
    assert config_value(check, 'hd_font_size') == '65'
    print('PASS: Text Size slider click and drag', flush=True)
    # [x] Text toggles at its new position and toggles back. Captures are
    # taken with the pointer on empty paper, away from hover highlights.
    away = (560, 400)
    hover(check, away)
    before = shot(check, 'toggle-before')
    point = ((TEXT_BOX[0] + TEXT_BOX[2]) // 2, (TEXT_BOX[1] + TEXT_BOX[3]) // 2)
    hover_click(check, point)
    hover(check, away)
    toggled = shot(check, 'toggle-text-off')
    assert difference(region(before, TEXT_BOX), region(toggled, TEXT_BOX)) > 5, 'Text checkbox did not toggle'
    hover_click(check, point)
    hover(check, away)
    restored = shot(check, 'toggle-text-on')
    assert difference(region(before, TEXT_BOX), region(restored, TEXT_BOX)) < 3, 'Text checkbox did not toggle back'
    # Effects Volume knob drags along its new row, even when the pointer strays.
    row = (48, EFFECTS_KNOB_Y - 14, 248, EFFECTS_KNOB_Y + 14)
    hover(check, away)
    before = shot(check, 'effects-before')
    knob = 48 + max(range(200), key=lambda x: difference(region(before, (48 + x, row[1], 49 + x, row[3])),
                                                           region(before, (48, row[1], 49, row[3]))))
    drag(check, (knob, EFFECTS_KNOB_Y), (70, EFFECTS_KNOB_Y + 30))
    hover(check, away)
    moved = shot(check, 'effects-dragged')
    assert difference(region(before, row), region(moved, row)) > 2, 'Effects knob did not move'
    drag(check, (70, EFFECTS_KNOB_Y), (knob, EFFECTS_KNOB_Y))
    print('PASS: checkbox toggle and slider drag at their new positions', flush=True)


def pause_banner(check):
    check.jump(9)
    time.sleep(2)
    before = shot(check, 'pause-before')
    count = len(log_lines(check, 'HD banner: retained frame'))
    check.send('key 32')
    time.sleep(1.5)
    first = shot(check, 'pause-open')
    second = shot(check, 'pause-open-again')
    assert len(log_lines(check, 'HD banner: retained frame')) > count, 'pause banner not retained'
    assert difference(first, second) < 1, 'paused frame changed'
    # Animation may advance before the pause; the scene must remain, not black.
    brightness = [sum(ImageStat.Stat(image).mean) / 3 for image in (before, first)]
    assert abs(brightness[0] - brightness[1]) < 12, brightness
    check.send('key 32')
    time.sleep(2)
    shot(check, 'pause-closed')
    print('PASS: pause banner keeps the gameplay frame', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/menu-check')
    parser.add_argument('--cpu', action='store_true', help='Disable GPU scene effects')
    args = parser.parse_args()
    output = args.output.resolve()
    assert (ROOT / '.playtest/hd/widescreen/bg_0092.png').is_file(), 'Install the room 92 widescreen sidecar first'
    output.mkdir(parents=True, exist_ok=True)
    grades = output / 'color-grades.json'
    grades.write_text(json.dumps({'schemaVersion': 1, 'rooms': {}}))
    check = Check(output, 169, color_grades_path=grades,
                  config_overrides={'comi': {'hd_gpu_effects': str(not args.cpu).lower(), 'hd_font_size': '65'},
                                    'scummvm': {'hd_film_enabled': 'false'}})
    try:
        check.jump(9)
        open_book(check)
        assert check.state()['viewportWidth'] == 640 and check.state()['aspectRatio'] == 169
        sides(check, 'book-169')
        print('PASS: book sides match widescreen/bg_0092', flush=True)
        book = shot(check, 'book')
        layout(check, book)
        prompt_checks(check, book)
        pages(check)
        controls(check)
        leave_book(check, 9)
        autosave(check)
        sides(check, 'cannon-after-book-169')
        print('PASS: gameplay sides restored after the book', flush=True)
        pause_banner(check)
        # The answered Quit prompt must not intercept a later quit request.
        open_book(check)
        count = len(log_lines(check, 'HD banner: retained frame'))
        started = time.monotonic()
        check.process.terminate()
        check.process.wait(8)
        assert time.monotonic() - started < 8
        assert len(log_lines(check, 'HD banner: retained frame')) == count, 'stale quit prompt reopened'
        print('PASS: engine exits from the book without a stale prompt', flush=True)
    finally:
        check.close()
    (output / 'result.json').write_text(json.dumps({'passed': True}))


if __name__ == '__main__':
    main()
