#!/usr/bin/env python3
"""Prepare the local COMI dialogue font at native 4x resolution (Pillow only)."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SCALE = 4


def unicode_cmap(data):
    """Read Unicode BMP cmap format 4, rejecting missing/.notdef glyphs."""
    tables = {}
    for i in range(struct.unpack_from('>H', data, 4)[0]):
        tag, _, offset, length = struct.unpack_from('>4sIII', data, 12 + i * 16)
        tables[tag] = (offset, length)
    offset, _ = tables[b'cmap']
    found = set()
    for i in range(struct.unpack_from('>H', data, offset + 2)[0]):
        platform, encoding, relative = struct.unpack_from('>HHI', data, offset + 4 + 8 * i)
        sub = offset + relative
        if platform not in (0, 3) or (platform == 3 and encoding not in (1, 10)):
            continue
        if struct.unpack_from('>H', data, sub)[0] != 4:
            continue
        count = struct.unpack_from('>H', data, sub + 6)[0] // 2
        ends = sub + 14
        starts = ends + 2 * count + 2
        deltas = starts + 2 * count
        ranges = deltas + 2 * count
        for j in range(count):
            end = struct.unpack_from('>H', data, ends + 2 * j)[0]
            start = struct.unpack_from('>H', data, starts + 2 * j)[0]
            delta = struct.unpack_from('>h', data, deltas + 2 * j)[0]
            step = struct.unpack_from('>H', data, ranges + 2 * j)[0]
            for code in range(start, min(end + 1, 0xFFFF)):
                glyph = struct.unpack_from('>H', data, ranges + 2*j + step + 2*(code-start))[0] if step else code
                if step and glyph == 0:
                    continue
                if (glyph + delta) & 0xFFFF:
                    found.add(code)
    if not found:
        raise ValueError('Font has no supported Unicode BMP cmap')
    return found


def nut_height(path):
    data = path.read_bytes()
    if data[:4] != b'ANIM' or data[8:12] != b'AHDR':
        raise ValueError(f'Invalid NUT font: {path}')
    offset = 8
    height = 0
    for _ in range(struct.unpack_from('<H', data, 18)[0]):
        offset += struct.unpack_from('>I', data, offset + 4)[0] + 16
        height = max(height, struct.unpack_from('<H', data, offset + 16)[0])
    if not 4 <= height <= 64:
        raise ValueError(f'Invalid NUT height: {height}')
    return height


def character(code, cmap):
    if code < 32 or code == 127:
        return None
    try:
        char = bytes([code]).decode('cp1252')
    except UnicodeDecodeError:
        return None
    return char if ord(char) in cmap else None


def make_atlas(source, height, scale=SCALE):
    if scale not in (4, 6):
        raise ValueError("Supported dialogue scales: 4, 6")
    cmap = unicode_cmap(source.read_bytes())
    chars = [character(i, cmap) for i in range(256)]
    stroke = scale  # one original pixel, rasterized at final resolution
    sample = ''.join(c for c in chars if c and not c.isspace())
    size = height * scale
    while size > 1:
        font = ImageFont.truetype(str(source), size)
        box = font.getbbox(sample, anchor='ls', stroke_width=stroke)
        if box[3] - box[1] <= height * scale:
            break
        size -= 1
    baseline = -box[1]
    boxes = [font.getbbox(c, anchor='ls', stroke_width=stroke) if c and not c.isspace() else (0, 0, 0, 0) for c in chars]
    cell_w = max(b[2] - b[0] for b in boxes) + 2
    cell_h = height * scale
    atlas = Image.new('RGBA', (cell_w * 16, cell_h * 16))
    draw = ImageDraw.Draw(atlas)
    metrics = []
    for code, char in enumerate(chars):
        if char is None:
            metrics.append((0, 0, 0))
            continue
        box = boxes[code]
        # The engine lays out text in original integer coordinates. Round once
        # here and share this exact advance between measuring and drawing.
        advance = max(1, math.floor(font.getlength(char) / scale + 0.5))
        metrics.append((1, advance, box[0]))
        if not char.isspace():
            draw.text((code % 16 * cell_w - box[0], code // 16 * cell_h + baseline), char,
                      font=font, anchor='ls', fill='white', stroke_width=stroke, stroke_fill='black')
    header = struct.pack('<4sHHHH', b'DLG1', scale, height, cell_w, cell_h)
    binary = header + b''.join(struct.pack('<HHh', *m) for m in metrics)
    return atlas, binary, {'font_size_hd': size, 'line_height': height, 'baseline_hd': baseline,
                            'supported_characters': sum(m[0] for m in metrics)}


def prepare(source, destination, resource):
    # Validate and render everything before replacing any working asset.
    outputs = [(scale, i, make_atlas(source, nut_height(resource / f'FONT{i}.NUT'), scale))
               for scale in (4, 6) for i in range(5)]
    destination.mkdir(parents=True, exist_ok=True)
    saved = destination / 'efmi.TTF'
    if source.resolve() != saved.resolve():
        shutil.copyfile(source, saved)
    report = {'family': ImageFont.truetype(str(saved), 40).getname(),
              'sha256': hashlib.sha256(saved.read_bytes()).hexdigest(), 'scales': [4, 6],
              'encoding': 'cp1252', 'slots': []}
    for scale, i, (atlas, binary, details) in outputs:
        folder = destination / f'{scale}x'
        folder.mkdir(exist_ok=True)
        name = folder / f'FONT{i}'
        details.update(scale=scale, slot=i)
        atlas.save(str(name) + '.tmp.png')
        Path(str(name) + '.tmp.png').replace(str(name) + '.png')
        Path(str(name) + '.tmp.dat').write_bytes(binary)
        Path(str(name) + '.tmp.dat').replace(str(name) + '.dat')
        report['slots'].append(details)
    (destination / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, default=ROOT / '.playtest/hd/dialogue-font/efmi.TTF')
    parser.add_argument('--output', type=Path, default=ROOT / '.playtest/hd/dialogue-font')
    parser.add_argument('--resource', type=Path, default=ROOT / '.playtest/game/RESOURCE')
    args = parser.parse_args()
    print(json.dumps(prepare(args.font, args.output, args.resource), indent=2))
