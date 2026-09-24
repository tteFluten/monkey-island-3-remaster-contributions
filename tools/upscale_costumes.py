#!/usr/bin/env python3
"""
Upscale COMI costume frames using pixel-art-aware algorithms.

Steps per frame:
1. Convert palette index 0 (black background) to transparent
2. Detect dark border colors used as antialiasing/shadow → convert to black with alpha
3. Apply Scale2x/Scale3x (EPX) pixel art upscale
4. Save as RGBA PNG

Usage:
  python3 tools/upscale_costumes.py                    # process all
  python3 tools/upscale_costumes.py LFLF_0015_AKOS_0076  # process one costume
  python3 tools/upscale_costumes.py --scale 3          # 3x instead of default 2x
  python3 tools/upscale_costumes.py --preview LFLF_0015_AKOS_0076  # save a comparison strip
"""

import os
import sys
import argparse
import numpy as np
from PIL import Image
from pathlib import Path

EXTRACTED_DIR = Path(__file__).parent.parent / 'extracted' / 'costumes'
OUTPUT_DIR = Path(__file__).parent.parent / 'upscaled' / 'costumes'


def palette_to_rgba(img: Image.Image) -> np.ndarray:
    """Convert paletted image to RGBA, treating index 0 as transparent.
    Also detect near-black border pixels and give them partial alpha."""

    if img.mode != 'P':
        return np.array(img.convert('RGBA'))

    pal = img.getpalette()  # flat [R,G,B,R,G,B,...]
    indices = np.array(img)
    h, w = indices.shape

    # Build RGBA from palette
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    for y in range(h):
        for x in range(w):
            idx = indices[y, x]
            if idx == 0:
                # Transparent
                rgba[y, x] = [0, 0, 0, 0]
            else:
                r, g, b = pal[idx*3:idx*3+3]
                # Check if it's a very dark pixel bordering transparency
                # These are antialiasing/shadow pixels
                brightness = r * 0.299 + g * 0.587 + b * 0.114
                if brightness < 15:
                    # Near-black: use as shadow with partial alpha
                    rgba[y, x] = [0, 0, 0, 180]
                else:
                    rgba[y, x] = [r, g, b, 255]

    return rgba


def palette_to_rgba_fast(img: Image.Image) -> np.ndarray:
    """Fast vectorized version of palette_to_rgba."""

    if img.mode != 'P':
        return np.array(img.convert('RGBA'))

    pal = np.array(img.getpalette(), dtype=np.uint8).reshape(-1, 3)
    indices = np.array(img)
    h, w = indices.shape

    # Map indices to RGB
    rgb = pal[indices]  # (h, w, 3)

    # Alpha: 0 for index 0, 255 for others
    alpha = np.where(indices == 0, 0, 255).astype(np.uint8)

    # Detect near-black non-transparent pixels (antialiasing/shadow)
    brightness = (rgb[:,:,0].astype(float) * 0.299 +
                  rgb[:,:,1].astype(float) * 0.587 +
                  rgb[:,:,2].astype(float) * 0.114)
    shadow_mask = (indices != 0) & (brightness < 15)

    # Shadow pixels: black with partial alpha
    rgb[shadow_mask] = [0, 0, 0]
    alpha[shadow_mask] = 180

    rgba = np.concatenate([rgb, alpha[:,:,np.newaxis]], axis=2)
    return rgba


def scale2x(rgba: np.ndarray) -> np.ndarray:
    """EPX / Scale2x algorithm for pixel art.

    For each pixel P with neighbors:
        A
      C P B
        D

    Output 2x2 block:
      E0 E1
      E2 E3

    Where:
      E0 = (C==A && C!=D && A!=B) ? A : P
      E1 = (A==B && A!=C && B!=D) ? B : P
      E2 = (D==C && D!=B && C!=A) ? C : P
      E3 = (B==D && B!=A && D!=C) ? D : P
    """
    h, w = rgba.shape[:2]
    out = np.zeros((h * 2, w * 2, 4), dtype=np.uint8)

    # Pad with transparent pixels
    padded = np.zeros((h + 2, w + 2, 4), dtype=np.uint8)
    padded[1:-1, 1:-1] = rgba

    for y in range(h):
        py = y + 1
        for x in range(w):
            px = x + 1
            P = padded[py, px]
            A = padded[py-1, px]
            B = padded[py, px+1]
            C = padded[py, px-1]
            D = padded[py+1, px]

            def eq(a, b):
                return np.array_equal(a, b)

            out[y*2, x*2] = A if (eq(C,A) and not eq(C,D) and not eq(A,B)) else P
            out[y*2, x*2+1] = B if (eq(A,B) and not eq(A,C) and not eq(B,D)) else P
            out[y*2+1, x*2] = C if (eq(D,C) and not eq(D,B) and not eq(C,A)) else P
            out[y*2+1, x*2+1] = D if (eq(B,D) and not eq(B,A) and not eq(D,C)) else P

    return out


def scale2x_fast(rgba: np.ndarray) -> np.ndarray:
    """Vectorized Scale2x — much faster than per-pixel loop."""
    h, w = rgba.shape[:2]

    # Pad
    padded = np.zeros((h + 2, w + 2, 4), dtype=np.uint8)
    padded[1:-1, 1:-1] = rgba

    P = padded[1:-1, 1:-1]  # center
    A = padded[0:-2, 1:-1]  # top
    B = padded[1:-1, 2:]    # right
    C = padded[1:-1, 0:-2]  # left
    D = padded[2:,   1:-1]  # bottom

    # Compare all channels at once
    def eq(a, b):
        return np.all(a == b, axis=2)

    ca = eq(C, A)
    cd = eq(C, D)
    ab = eq(A, B)
    bd = eq(B, D)

    # E0 = A if (C==A && C!=D && A!=B) else P
    e0_cond = ca & ~cd & ~ab
    # E1 = B if (A==B && A!=C && B!=D) else P
    e1_cond = ab & ~eq(A, C) & ~bd
    # E2 = C if (D==C && D!=B && C!=A) else P
    e2_cond = eq(D, C) & ~eq(D, B) & ~ca
    # E3 = D if (B==D && B!=A && D!=C) else P
    e3_cond = bd & ~eq(B, A) & ~cd

    out = np.zeros((h * 2, w * 2, 4), dtype=np.uint8)

    # Expand conditions to include channel dim
    e0_cond = e0_cond[:,:,np.newaxis]
    e1_cond = e1_cond[:,:,np.newaxis]
    e2_cond = e2_cond[:,:,np.newaxis]
    e3_cond = e3_cond[:,:,np.newaxis]

    out[0::2, 0::2] = np.where(e0_cond, A, P)
    out[0::2, 1::2] = np.where(e1_cond, B, P)
    out[1::2, 0::2] = np.where(e2_cond, C, P)
    out[1::2, 1::2] = np.where(e3_cond, D, P)

    return out


def scale3x_fast(rgba: np.ndarray) -> np.ndarray:
    """Vectorized Scale3x — extends Scale2x to 3x3 output blocks."""
    h, w = rgba.shape[:2]

    padded = np.zeros((h + 2, w + 2, 4), dtype=np.uint8)
    padded[1:-1, 1:-1] = rgba

    P = padded[1:-1, 1:-1]
    A = padded[0:-2, 1:-1]
    B = padded[1:-1, 2:]
    C = padded[1:-1, 0:-2]
    D = padded[2:,   1:-1]

    # Diagonals
    E_tl = padded[0:-2, 0:-2]  # top-left
    F_tr = padded[0:-2, 2:]    # top-right
    G_bl = padded[2:,   0:-2]  # bottom-left
    H_br = padded[2:,   2:]    # bottom-right

    def eq(a, b):
        return np.all(a == b, axis=2)

    ca = eq(C, A)
    cd = eq(C, D)
    ab = eq(A, B)
    bd = eq(B, D)
    da = eq(D, A)
    bc = eq(B, C)

    def cond3(c):
        return c[:,:,np.newaxis]

    out = np.zeros((h * 3, w * 3, 4), dtype=np.uint8)

    # 9 output pixels per input pixel
    # Top row
    out[0::3, 0::3] = np.where(cond3(ca & ~cd & ~ab), A, P)
    out[0::3, 1::3] = np.where(cond3((ca & ~cd & ~ab & ~eq(A, F_tr)) | (ab & ~eq(A, C) & ~bd & ~eq(A, E_tl))), A, P)
    out[0::3, 2::3] = np.where(cond3(ab & ~eq(A, C) & ~bd), B, P)

    # Middle row
    out[1::3, 0::3] = np.where(cond3((ca & ~cd & ~ab & ~eq(C, G_bl)) | (eq(D,C) & ~eq(D,B) & ~ca & ~eq(C, E_tl))), C, P)
    out[1::3, 1::3] = P  # center is always P
    out[1::3, 2::3] = np.where(cond3((ab & ~eq(A,C) & ~bd & ~eq(B, H_br)) | (bd & ~eq(B,A) & ~cd & ~eq(B, F_tr))), B, P)

    # Bottom row
    out[2::3, 0::3] = np.where(cond3(eq(D,C) & ~eq(D,B) & ~ca), C, P)
    out[2::3, 1::3] = np.where(cond3((eq(D,C) & ~eq(D,B) & ~ca & ~eq(D, H_br)) | (bd & ~eq(B,A) & ~cd & ~eq(D, G_bl))), D, P)
    out[2::3, 2::3] = np.where(cond3(bd & ~eq(B,A) & ~cd), D, P)

    return out


def process_frame(input_path: Path, output_path: Path, scale: int = 3) -> bool:
    """Process a single costume frame: transparency + upscale."""
    try:
        img = Image.open(input_path)
        rgba = palette_to_rgba_fast(img)

        if scale == 2:
            upscaled = scale2x_fast(rgba)
        elif scale == 3:
            # Apply scale2x then another pass, or use scale3x
            upscaled = scale3x_fast(rgba)
        elif scale == 4:
            upscaled = scale2x_fast(scale2x_fast(rgba))
        elif scale == 6:
            upscaled = scale2x_fast(scale3x_fast(rgba))
        else:
            raise ValueError(f'Unsupported scale: {scale}. Use 2, 3, 4, or 6.')

        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(upscaled).save(output_path, 'PNG')
        return True
    except Exception as e:
        print(f'  ERROR {input_path.name}: {e}', file=sys.stderr)
        return False


def make_preview(akos_id: str, scale: int = 3):
    """Create a comparison strip: original frames on top, upscaled below."""
    frames_orig = sorted(EXTRACTED_DIR.glob(f'{akos_id}_frame_*.png'),
                         key=lambda f: int(f.stem.rsplit('_', 1)[1]))
    if not frames_orig:
        print(f'No frames found for {akos_id}')
        return

    # Limit to first 8 frames for preview
    frames_orig = frames_orig[:8]

    originals = []
    upscaled = []
    for f in frames_orig:
        img = Image.open(f)
        rgba = palette_to_rgba_fast(img)
        originals.append(rgba)
        if scale == 2:
            up = scale2x_fast(rgba)
        elif scale == 3:
            up = scale3x_fast(rgba)
        elif scale == 4:
            up = scale2x_fast(scale2x_fast(rgba))
        else:
            up = scale3x_fast(rgba)
        upscaled.append(up)

    # Find max dimensions
    max_h_orig = max(a.shape[0] for a in originals)
    max_w_orig = max(a.shape[1] for a in originals)
    max_h_up = max(a.shape[0] for a in upscaled)
    max_w_up = max(a.shape[1] for a in upscaled)

    n = len(originals)
    gap = 4

    # Create strip: originals on left side, upscaled on right
    total_w = max(n * (max_w_orig + gap), n * (max_w_up + gap))
    total_h = max_h_orig + gap + max_h_up + gap

    strip = np.zeros((total_h, total_w, 4), dtype=np.uint8)
    # Checkerboard background for transparency
    for y in range(total_h):
        for x in range(total_w):
            if (x // 8 + y // 8) % 2 == 0:
                strip[y, x] = [40, 40, 40, 255]
            else:
                strip[y, x] = [60, 60, 60, 255]

    # Place originals (top row)
    x_off = 0
    for orig in originals:
        oh, ow = orig.shape[:2]
        y_off = max_h_orig - oh  # bottom-align
        for y in range(oh):
            for x in range(ow):
                if orig[y, x, 3] > 0:
                    strip[y_off + y, x_off + x] = orig[y, x]
        x_off += max_w_orig + gap

    # Place upscaled (bottom row)
    x_off = 0
    y_base = max_h_orig + gap
    for up in upscaled:
        uh, uw = up.shape[:2]
        y_off = y_base + (max_h_up - uh)
        for y in range(uh):
            for x in range(uw):
                if up[y, x, 3] > 0:
                    strip[y_off + y, x_off + x] = up[y, x]
        x_off += max_w_up + gap

    preview_dir = Path(__file__).parent.parent / 'previews'
    preview_dir.mkdir(exist_ok=True)
    preview_path = preview_dir / f'preview_{akos_id}_scale{scale}x.png'
    Image.fromarray(strip).save(preview_path, 'PNG')
    print(f'Preview saved: {preview_path}')


def main():
    parser = argparse.ArgumentParser(description='Upscale COMI costume frames')
    parser.add_argument('akos_id', nargs='?', help='Process specific AKOS (e.g. LFLF_0015_AKOS_0076)')
    parser.add_argument('--scale', type=int, default=3, choices=[2, 3, 4, 6], help='Scale factor (default: 3)')
    parser.add_argument('--preview', type=str, help='Generate comparison preview for AKOS ID')
    args = parser.parse_args()

    if args.preview:
        make_preview(args.preview, args.scale)
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.akos_id:
        pattern = f'{args.akos_id}_frame_*.png'
    else:
        pattern = '*.png'

    frames = sorted(EXTRACTED_DIR.glob(pattern))
    if not frames:
        print(f'No frames found matching {pattern}')
        return

    print(f'Processing {len(frames)} frames at {args.scale}x...')
    done = 0
    for i, f in enumerate(frames):
        out = OUTPUT_DIR / f.name
        if out.exists():
            done += 1
            continue
        if process_frame(f, out, args.scale):
            done += 1
        if (i + 1) % 100 == 0:
            print(f'  {i+1}/{len(frames)}...')

    print(f'Done: {done}/{len(frames)} frames upscaled to {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
