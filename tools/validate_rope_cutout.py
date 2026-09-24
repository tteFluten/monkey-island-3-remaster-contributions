"""Geometry validation for the cannon rope's thin, stair-stepped source art.

The reference is validation-only. This module never writes or repairs pixels.
A two-runtime-pixel tolerance is half a source pixel at the required 4x scale.
"""
import numpy as np
from PIL import Image, ImageFilter
from topaz_character_cutouts import character_validation


def validate_rope(result, raw, source):
    report = character_validation(result, raw, source)
    with Image.open(result) as image:
        rgba = np.array(image)
    with Image.open(raw) as image:
        rgb = np.array(image.convert('RGB'))
    with Image.open(source) as image:
        if rgba.shape[1::-1] != (image.width*4, image.height*4):
            raise ValueError('Rope validation requires exact 4x dimensions')
        reference = np.array(image.convert('RGBA').getchannel('A').resize(
            (rgba.shape[1],rgba.shape[0]), Image.Resampling.NEAREST)) >= 192
    mask = rgba[:,:,3] >= 192
    fringe = rgba[:,:,3] >= 32
    def expanded(a, radius):
        return np.asarray(Image.fromarray((a*255).astype('uint8')).filter(ImageFilter.MaxFilter(radius*2+1))) > 0
    def coverage(a,b): return float((a & b).sum()/max(1,a.sum()))
    def bounds(a):
        y,x = np.nonzero(a)
        return np.array([x.min(),y.min(),x.max(),y.max()]) if len(x) else None
    rb,mb = bounds(reference),bounds(mask)
    bounds_error = int(np.abs(rb-mb).max()) if rb is not None and mb is not None else None
    # Every occupied source row/column needs nearby output, including small ends
    # that could disappear without moving the overall area score very much.
    expanded_mask = expanded(mask,2)
    rows = bool(np.all(~reference.any(1) | expanded_mask.any(1)))
    columns = bool(np.all(~reference.any(0) | expanded_mask.any(0)))
    metrics = dict(reference_coverage=coverage(reference,expanded_mask),
        output_precision=coverage(mask,expanded(reference,2)),
        fringe_precision=coverage(fringe,expanded(reference,4)),
        area_ratio=float(mask.sum()/max(1,reference.sum())),
        bounds_error_pixels=bounds_error, rows_present=rows, columns_present=columns,
        rgb_unchanged=bool(np.array_equal(rgba[:,:,:3],rgb)))
    character_passed = report['passed']
    report['passed'] = bool(metrics['reference_coverage'] >= .99 and metrics['output_precision'] >= .99
        and metrics['fringe_precision'] >= .99 and .85 <= metrics['area_ratio'] <= 1.15
        and bounds_error is not None and bounds_error <= 2 and rows and columns
        and metrics['rgb_unchanged'] and report['silhouette_iou'] >= .80
        and report['missing_interior_fraction'] <= .01 and report['outside_fraction'] <= .01
        and (rgba[:,:,3] == 0).any() and (rgba[:,:,3] >= 250).any())
    report.update(character_validation_passed=character_passed,
        rope_geometry=dict(version=1,tolerance_pixels=2,**metrics))
    return report
