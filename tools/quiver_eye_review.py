#!/usr/bin/env python3
"""Measure eye-white landmarks and make aligned face comparisons for visual review.

This is a review aid, not an automatic acceptance test: tiny source pupils,
partially closed eyes and unfilled SVG eye outlines require visual inspection.
Coordinates are always in original cel pixels, before runtime mirroring/scaling.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import numpy as np
from PIL import Image, ImageDraw


def white_pixels(rgba):
    rgb = rgba[:, :, :3].astype(int)
    return (rgba[:, :, 3] > 192) & (rgb.min(2) > 195) & ((rgb.max(2) - rgb.min(2)) < 60)


def clusters(mask, distance=2):
    points = set(map(tuple, np.argwhere(mask)))
    result = []
    while points:
        start = points.pop()
        group, queue = [start], [start]
        while queue:
            y, x = queue.pop()
            for dy in range(-distance, distance + 1):
                for dx in range(-distance, distance + 1):
                    point = y + dy, x + dx
                    if point in points:
                        points.remove(point); queue.append(point); group.append(point)
        coords = np.array(group)
        y0, x0 = coords.min(0); y1, x1 = coords.max(0) + 1
        result.append(dict(box=[int(x0), int(y0), int(x1), int(y1)],
                           center=[float((x0 + x1) / 2), float((y0 + y1) / 2)], area=len(group)))
    return sorted(result, key=lambda c: c['center'][0])


def measure(source, rendered, height):
    src = white_pixels(np.array(source.convert('RGBA'))); src[height:] = False
    original = [c for c in clusters(src) if c['area'] <= 20 and
                c['box'][2] - c['box'][0] <= 7 and c['box'][3] - c['box'][1] <= 8]
    scale = rendered.width / source.width
    dst = white_pixels(np.array(rendered.convert('RGBA'))); dst[int(height * scale):] = False
    generated = [c for c in clusters(dst, 1) if 8 <= c['area'] <= 1200 and
                 c['box'][2] - c['box'][0] <= 50 and c['box'][3] - c['box'][1] <= 60]
    for c in generated:
        c['center'] = [v / scale for v in c['center']]
        c['box'] = [v / scale for v in c['box']]
    pairs = []
    for eye in original:
        if not generated: continue
        match = min(generated, key=lambda c: sum((a - b) ** 2 for a, b in zip(c['center'], eye['center'])))
        delta = [round(b - a, 3) for a, b in zip(eye['center'], match['center'])]
        pairs.append(dict(source=eye, generated=match, delta=delta))
    return dict(source_eyes=original, generated_candidates=generated, eyes=pairs,
                needs_visual_inspection=not original or len(pairs) != len(original) or
                any(max(map(abs, eye['delta'])) > 1 for eye in pairs))


def review(output, destination):
    destination.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((output / 'manifest.json').read_text())
    repairs_file = output / 'repairs.json'
    repairs = json.loads(repairs_file.read_text()) if repairs_file.exists() else {}
    with sqlite3.connect(output / 'jobs.sqlite') as db:
        states = dict(db.execute('select key,state from jobs'))
    results, faces = [], []
    for record in sorted(manifest['records'], key=lambda r: r['cel']):
        key = record['artwork_sha256']
        if states.get(key) not in ('accepted', 'geometry_passed'): continue
        if record['cel'] in manifest['scope']['standing_body_cels']: continue
        source = Image.open(output / 'cleaned' / record['source']).convert('RGBA')
        rendered = Image.open(output / '6x' / (key + '.png')).convert('RGBA')
        head = record['cel'] in manifest['scope']['standing_head_cels']
        height = int(source.height * (.65 if head else .19))
        report = dict(cel=record['cel'], key=key, **measure(source, rendered, height))
        repair = repairs.get(key, {})
        if repair.get('eye_style') in ('solid-dark-dot', 'white-with-dark-dot'):
            dots = []
            for eye in report['source_eyes']:
                x, y = eye['center']
                pixel = rendered.getpixel((round(x * 6), round(y * 6)))
                dots.append(dict(center=[x, y], dark_at_source_center=max(pixel[:3]) < 80 and pixel[3] > 240))
            report['dot_eyes'] = dots
            report['needs_visual_inspection'] = not dots or not all(d['dark_at_source_center'] for d in dots)
        results.append(report)
        # Same crop and scale on both sides; margins are never independently fitted.
        crop_height = min(source.height, height + 8)
        box = source.crop((0, 0, source.width, crop_height)).getbbox()
        if box:
            left, right = max(0, box[0] - 2), min(source.width, box[2] + 2)
            pair = Image.new('RGB', (400, 260), '#465660'); draw = ImageDraw.Draw(pair)
            draw.text((5, 5), f"Cel {record['cel']} | original / Quiver", fill='white')
            factor = min(190 / (right - left), 225 / crop_height)
            for j, im in enumerate((source, rendered)):
                scale = im.width / source.width
                crop = im.crop(tuple(round(v * scale) for v in (left, 0, right, crop_height)))
                crop = crop.resize((round((right - left) * factor), round(crop_height * factor)),
                                   Image.Resampling.NEAREST if j == 0 else Image.Resampling.LANCZOS)
                pair.paste(crop, (j * 200, 27), crop)
            faces.append(pair)
    (destination / 'landmarks.json').write_text(json.dumps(results, indent=2) + '\n')
    for page in range((len(faces) + 11) // 12):
        sheet = Image.new('RGB', (1200, 1040), '#465660')
        for i, face in enumerate(faces[page * 12:(page + 1) * 12]):
            sheet.paste(face, ((i % 3) * 400, (i // 3) * 260))
        sheet.save(destination / f'faces-{page + 1:02}.png')
    print(f'{len(results)} face comparisons saved to {destination}')
    for result in results:
        if result['source_eyes'] and result['needs_visual_inspection']:
            print('Inspect eye landmarks:', result['cel'], [e['delta'] for e in result['eyes']])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('output/quiver-cannon/walking-vectorized'))
    parser.add_argument('--review-dir', type=Path, default=Path('.context/quiver-eyes'))
    args = parser.parse_args()
    review(args.output, args.review_dir)
