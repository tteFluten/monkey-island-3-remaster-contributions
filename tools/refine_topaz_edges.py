#!/usr/bin/env python3
"""Make a separate smooth-edge Topaz variant, without spending credits or changing masters."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from topaz_batch import atomic_image


def refine(result, original, scale=6, crisp=False):
    original = original.convert('RGBA')
    result = result.convert('RGBA')
    if result.size != (original.width * scale, original.height * scale):
        raise ValueError('Result must preserve the original canvas at the requested scale')
    source = np.asarray(original)
    solid = Image.fromarray(np.where(source[:, :, 3] >= 192, 255, 0).astype('uint8'))
    solid = solid.resize(result.size, Image.Resampling.NEAREST)
    blurred = np.asarray(solid.filter(ImageFilter.GaussianBlur(scale * (.55 if crisp else .4))), dtype=np.float32)
    # Smooth corners below one source pixel; keep the transition narrow at HD size.
    coverage = np.clip((blurred - (96 if crisp else 64)) / (63 if crisp else 127), 0, 1)
    coverage = coverage * coverage * (3 - 2 * coverage)
    shadow = Image.fromarray(np.where(source[:, :, 3] < 192, source[:, :, 3], 0).astype('uint8'))
    shadow = np.asarray(shadow.resize(result.size, Image.Resampling.BICUBIC)
                        .filter(ImageFilter.GaussianBlur(scale * .2)), dtype=np.float32) / 255
    alpha = coverage + shadow * (1 - coverage)
    # Extend nearby opaque colors through the antialias border. This avoids
    # interpolating against the gray matte or colored pixels outside the sprite.
    core = np.asarray(solid.filter(ImageFilter.MinFilter(5))) == 255
    colors = np.asarray(result).copy()[:, :, :3].astype(np.float32)
    known = core.copy()
    for _ in range(scale * 2):
        if (known | (coverage == 0)).all():
            break
        padded_colors = np.pad(colors * known[:, :, None], ((1, 1), (1, 1), (0, 0)))
        padded_known = np.pad(known.astype('float32'), 1)
        color_sum = (padded_colors[:-2, 1:-1] + padded_colors[2:, 1:-1] +
                     padded_colors[1:-1, :-2] + padded_colors[1:-1, 2:])
        count = (padded_known[:-2, 1:-1] + padded_known[2:, 1:-1] +
                 padded_known[1:-1, :-2] + padded_known[1:-1, 2:])
        fill = ~known & (count > 0) & (coverage > 0)
        colors[fill] = color_sum[fill] / count[fill, None]
        known |= fill
    reference = np.asarray(original.resize(result.size, Image.Resampling.BICUBIC))
    colors[~known] = reference[~known, :3]
    if crisp:
        # Reconstruct a roughly one-source-pixel ink border using the darkest existing
        # opaque paint. This is a separate review variant, never a master edit.
        paint = source[source[:, :, 3] >= 192, :3]
        ink = paint[np.argmin(paint.astype('float32').sum(axis=1))] if len(paint) else np.zeros(3)
        inner = np.asarray(Image.fromarray((coverage * 255).astype('uint8'))
                           .filter(ImageFilter.MinFilter(11)), dtype=np.float32) / 255
        border = np.clip((1 - inner) * 1.2, 0, 1)[:, :, None]
        colors = colors * (1 - border) + ink * border
    # Shadows are neutral black and retain partial alpha.
    colors *= np.divide(coverage, alpha, out=np.zeros_like(alpha), where=alpha > 0)[:, :, None]
    rgba = np.concatenate((np.clip(colors, 0, 255).astype('uint8'),
                           np.rint(alpha * 255).astype('uint8')[:, :, None]), axis=2)
    rgba[rgba[:, :, 3] <= 1] = 0
    return Image.fromarray(rgba)


def run(root, only=(), crisp=False):
    manifest = json.loads((root / 'manifest.json').read_text())
    count = 0
    for record in manifest['records']:
        source = record['source']
        if not source.startswith('costumes/') or (only and source not in only):
            continue
        result = root / '6x' / source
        if not result.exists():
            continue
        with Image.open(result) as master, Image.open(root / 'cleaned' / source) as original:
            atomic_image(refine(master, original, crisp=crisp), root / ('6x-crisp' if crisp else '6x-smooth') / source)
        count += 1
    print(f'Prepared {count} smooth-edge variants; 6x masters unchanged.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--only', action='append', default=[])
    parser.add_argument('--crisp', action='store_true', help='Reconstruct a narrow ink outline using existing source colors')
    args = parser.parse_args()
    run(args.root, args.only, args.crisp)
