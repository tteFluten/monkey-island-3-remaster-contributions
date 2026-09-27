#!/usr/bin/env python3
"""Prepare and check COMI language packs (see PLAYTEST.md, "Languages").

  template OUTPUT   Write OUTPUT/overrides.tab (every game line, English text to
                    translate, UTF-8) and OUTPUT/voices.csv (spoken lines: tag,
                    bundle, English text) from the local English game data.
  check PACK        Validate a pack directory: overrides.tab tags and encoding,
                    LANGUAGE.TAB, voice bundles and voices/<TAG>.wav format, and
                    report coverage against the English game.

Reads only local game data (.playtest/game/RESOURCE); writes nothing else.
"""
import argparse
import csv
from pathlib import Path
import struct
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / '.playtest/game/RESOURCE'

# Engine prompts (quit, pause, restart, save/load messages): tagged like game
# lines but built into the engine, so the English LANGUAGE.TAB may lack them.
ENGINE_STRINGS = {
    'BT_100': 'Please insert disk %d. Press ENTER', 'BT__003': 'Unable to Find %s, (%s %d) Press Button.',
    'BT__004': 'Error reading disk %c, (%c%d) Press Button.', 'BT__002': 'Game Paused.  Press SPACE to Continue.',
    'BT__005': 'Are you sure you want to restart?  (Y/N)', 'BT__006': 'Are you sure you want to quit?  (Y/N)',
    'BT__008': 'Save', 'BT__009': 'Load', 'BT__010': 'Play', 'BT__011': 'Cancel', 'BT__012': 'Quit', 'BT__013': 'OK',
    'BT__014': 'You must enter a name', 'BT__015': 'The game was NOT saved (disk full?)',
    'BT__016': 'The game was NOT loaded', 'BT__017': "Saving '%s'", 'BT__018': "Loading '%s'",
    'BT__019': 'Name your SAVE game', 'BT__020': 'Select a game to LOAD',
    'BT__028': 'Do you want to replace this saved game? (Y/N)Y', 'SYST200': 'Are you sure you want to quit?',
    'SYST201': 'Yes', 'SYST202': 'No', 'SYST203': 'iMuse buffer count changed to %d', 'BT_104': 'Voice and Text',
    'BT_105': 'Text Display Only', 'BT_103': 'Voice Only', 'SYST300': 'y',
}


def read_table(data, encoding):
    """TAG -> text for "TAG<space or tab>text" lines, as the engine reads them."""
    table = {}
    for line in data.decode(encoding).splitlines():
        if line.startswith('﻿'):
            line = line[1:]
        tag = ''
        for c in line[:8]:
            if c in ' \t':
                break
            tag += c
        if tag and len(line) > len(tag) and line[len(tag)] in ' \t':
            table[tag.upper()] = line[len(tag) + 1:]
    return table


def bundle_names(path):
    """Entry names (e.g. SMSR001.IMX) in a VOXDISK*.BUN bundle."""
    with open(path, 'rb') as bundle:
        tag, offset, count = struct.unpack('>4sII', bundle.read(12))
        bundle.seek(offset)
        names = []
        for _ in range(count):
            if tag == b'LB23':
                name = bundle.read(24).split(b'\0')[0].decode('latin-1')
            else:
                name = bundle.read(8).split(b'\0')[0].decode('latin-1') + '.' + bundle.read(4).split(b'\0')[0].decode('latin-1')
            bundle.read(8)
            names.append(name.upper())
    return names


def spoken(game):
    lines = {}
    for disk in (1, 2):
        path = game / f'VOXDISK{disk}.BUN'
        if path.exists():
            for name in bundle_names(path):
                if name.endswith('.IMX'):
                    lines.setdefault(name[:-4], disk)
    return lines


def english_lines(game):
    english = dict(ENGINE_STRINGS)
    english.update(read_table((game / 'LANGUAGE.TAB').read_bytes(), 'cp1252'))
    return english


def template(output, game):
    english = english_lines(game)
    voices = spoken(game)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'overrides.tab').write_text(''.join(f'{tag}\t{text}\r\n' for tag, text in english.items()), encoding='utf-8')
    with open(output / 'voices.csv', 'w', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        writer.writerow(['tag', 'voice bundle', 'english text'])
        for tag, disk in sorted(voices.items()):
            writer.writerow([tag, f'VOXDISK{disk}.BUN', english.get(tag, '')])
    print(f'{len(english)} lines in overrides.tab, {len(voices)} spoken lines in voices.csv -> {output}')


def check_wav(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            if audio.getsampwidth() != 2 or audio.getnchannels() not in (1, 2) or audio.getcomptype() != 'NONE':
                return f'needs 16-bit PCM mono/stereo (has {audio.getsampwidth() * 8}-bit, {audio.getnchannels()} channels)'
            if audio.getnframes() == 0:
                return 'is empty'
    except (wave.Error, EOFError) as error:
        return f'is not a PCM WAV ({error})'
    return None


def check(pack, game):
    english = english_lines(game)
    voices = spoken(game)
    problems, text, recorded = [], {}, set()
    if (pack / 'LANGUAGE.TAB').exists():
        text.update(read_table((pack / 'LANGUAGE.TAB').read_bytes(), 'cp1252'))
    if (pack / 'overrides.tab').exists():
        raw = (pack / 'overrides.tab').read_bytes()
        try:
            overrides = read_table(raw, 'utf-8')
        except UnicodeDecodeError as error:
            problems.append(f'overrides.tab is not UTF-8: {error}')
            overrides = {}
        for tag, line in overrides.items():
            try:
                line.encode('cp1252')
            except UnicodeEncodeError:
                problems.append(f'overrides.tab {tag}: characters the game fonts cannot show: {line!r}')
        text.update(overrides)
    unknown = sorted(set(text) - set(english))
    if unknown:
        problems.append(f'{len(unknown)} tags not in the English game (first: {", ".join(unknown[:5])})')
    for disk in (1, 2):
        path = pack / f'VOXDISK{disk}.BUN'
        if path.exists():
            try:
                recorded.update(name[:-4] for name in bundle_names(path) if name.endswith('.IMX'))
            except (OSError, struct.error) as error:
                problems.append(f'{path.name} is not a voice bundle: {error}')
    for path in sorted((pack / 'voices').glob('*.wav')) if (pack / 'voices').is_dir() else []:
        tag = path.stem.upper()
        if tag not in voices:
            problems.append(f'voices/{path.name}: not a spoken line in the English game')
        issue = check_wav(path)
        if issue:
            problems.append(f'voices/{path.name} {issue}')
        else:
            recorded.add(tag)
    translated = len(set(text) & set(english))
    print(f'text: {translated}/{len(english)} lines; voices: {len(recorded & set(voices))}/{len(voices)} spoken lines')
    for problem in problems:
        print('PROBLEM:', problem)
    return not problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--game', type=Path, default=GAME, help='English RESOURCE directory')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('template').add_argument('output', type=Path)
    commands.add_parser('check').add_argument('pack', type=Path)
    args = parser.parse_args()
    if args.command == 'template':
        template(args.output, args.game)
    elif not check(args.pack, args.game):
        sys.exit(1)


if __name__ == '__main__':
    main()
