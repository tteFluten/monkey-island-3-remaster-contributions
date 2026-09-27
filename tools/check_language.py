#!/usr/bin/env python3
"""Native language-pack checks with a generated test pack (not a translation).

Builds <output>/lang/es with a UTF-8 overrides.tab for the options book and the
quit prompt, and voices/CNWY034.wav (a tone) for a line spoken in the cannon
room. Checks the book's language row, the instant switch of text and voice,
persistence, start-up restore, switching back, and a missing pack.
Uses copied saves and an isolated config (see check_aspect).
"""
import argparse
import configparser
import math
from pathlib import Path
import struct
import time
import wave

from PIL import Image, ImageChops, ImageStat
from check_aspect import Check, ROOT
from check_menu import hover, hover_click, leave_book, log_lines, open_book, prompt_shot, region, shot, QUIT

OVERRIDES = {
    'SA__025': 'TABLA DE CONTENIDOS', 'SA__026': 'Guardar partida', 'SA__027': 'Cargar partida',
    'SA__028': 'Volver al juego', 'SA__029': 'Salir', 'SA__030': 'Volumen de efectos',
    'SA__031': 'Volumen de voces', 'SA__032': 'Volumen de música', 'SA__033': 'Velocidad del texto',
    'SA__034': 'Voces', 'SA__035': 'Texto', 'SA__036': 'Mostrar línea de objetos',
    'SA__004': 'Salir de The Curse of Monkey Island', 'SYST200': '¿Seguro que quieres salir?',
    'SYST201': 'Sí', 'SYST202': 'No', 'CNWY034': '¡Malditos perros sarnosos!',
}
ENGLISH, SPANISH = (414, 392), (518, 392)     # Language row (hd_book_layout.h)
EFFECTS_LABEL = (48, 62, 220, 88)
VOICE_LINE = 'CNWY034'


def build_pack(root):
    pack = root / 'lang/es'
    (pack / 'voices').mkdir(parents=True, exist_ok=True)
    (pack / 'overrides.tab').write_text(''.join(f'{tag}\t{text}\r\n' for tag, text in OVERRIDES.items()), encoding='utf-8')
    with wave.open(str(pack / f'voices/{VOICE_LINE}.wav'), 'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(22050)
        out.writeframes(b''.join(struct.pack('<h', int(6000 * math.sin(i * 2 * math.pi * 440 / 22050)))
                                 for i in range(22050 * 3 // 2)))
    (root / 'empty').mkdir(exist_ok=True)
    return root / 'lang'


def language(check):
    config = configparser.ConfigParser(interpolation=None)
    config.read(check.output / 'scummvm.ini')
    return config.get('comi', 'hd_language', fallback='en')


def start(output, packs, code):
    return Check(output, 169, config_overrides={
        'comi': {'hd_language_dir': str(packs), 'hd_language': code},
        'scummvm': {'hd_film_enabled': 'false'}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/language-check')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    packs = build_pack(output)

    check = start(output / 'switch', packs, 'en')
    try:
        check.jump(9)
        open_book(check)
        hover(check, (320, 20))
        english = shot(check, 'book-en')
        hover_click(check, SPANISH)
        check.wait(lambda: language(check) == 'es', 'Spanish saved')
        hover(check, (320, 20))
        spanish = shot(check, 'book-es')
        assert log_lines(check, 'HD language: es ('), 'switch not logged'
        diff = max(ImageStat.Stat(ImageChops.difference(region(english, EFFECTS_LABEL), region(spanish, EFFECTS_LABEL))).mean)
        assert diff > 3, ('book labels did not change', diff)
        print(f'PASS: the book switches to Spanish instantly ({diff:.1f})', flush=True)
        hover_click(check, QUIT)
        time.sleep(1.5)
        prompt_shot(check, 'quit-es')
        check.send('key 110')
        time.sleep(2)
        leave_book(check, 9)
        check.jump(15)
        check.jump(9)
        check.wait(lambda: log_lines(check, f'HD voice: {VOICE_LINE}.IMX from the language pack'), 'Spanish voice line', 60)
        print('PASS: a spoken line plays from the pack voices', flush=True)
        open_book(check)
        hover_click(check, ENGLISH)
        check.wait(lambda: language(check) == 'en', 'English saved')
        hover(check, (320, 20))
        back = shot(check, 'book-en-again')
        diff = max(ImageStat.Stat(ImageChops.difference(region(english, EFFECTS_LABEL), region(back, EFFECTS_LABEL))).mean)
        assert diff < 3, ('English labels did not return', diff)
        print('PASS: switching back restores English', flush=True)
    finally:
        check.close()

    check = start(output / 'restore', packs, 'es')
    try:
        assert log_lines(check, 'HD language: es ('), 'saved Spanish not restored at start-up'
        check.jump(9)
        open_book(check)
        hover(check, (320, 20))
        restored = shot(check, 'book-es-restored')
        diff = max(ImageStat.Stat(ImageChops.difference(region(spanish, EFFECTS_LABEL), region(restored, EFFECTS_LABEL))).mean)
        assert diff < 3, ('restored book is not in Spanish', diff)
        print('PASS: the saved language is restored at start-up', flush=True)
    finally:
        check.close()

    check = start(output / 'missing', output / 'empty', 'es')
    try:
        assert log_lines(check, 'pack not found; using English'), 'missing pack not reported'
        check.jump(9)
        open_book(check)
        hover_click(check, SPANISH)
        time.sleep(2)
        assert not log_lines(check, 'HD language: es ('), 'switched without a pack'
        hover(check, (320, 20))
        shot(check, 'book-no-pack')
        print('PASS: without a pack the book stays in English and Spanish is unavailable', flush=True)
    finally:
        check.close()


if __name__ == '__main__':
    main()
