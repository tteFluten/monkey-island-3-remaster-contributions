"""Deterministic vector ink, measured in original cel pixels.

NanoSVG resolves all nested transforms before brush geometry is constructed.
No texture, filter, random noise, raster tracing or eye repositioning is used.
"""
import json
import math
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np

SVG = 'http://www.w3.org/2000/svg'
INK = '#30231b'


def path_data(path):
    p = path['points']
    d = f'M{p[0][0]:.5f} {p[0][1]:.5f}'
    for i in range(1, len(p), 3):
        d += ' C' + ' '.join(f'{x:.5f} {y:.5f}' for x, y in p[i:i+3])
    return d + (' Z' if path['closed'] else '')


def brush_contour(path, width, canvas=None):
    """A round brush with gentle directional pressure and tapered open ends."""
    points = np.asarray(path['points'], dtype=float)
    samples = []
    for i in range(0, len(points) - 1, 3):
        curve = points[i:i+4]
        length = np.linalg.norm(np.diff(curve, axis=0), axis=1).sum()
        t = np.linspace(0, 1, max(3, min(512, math.ceil(length / .25) + 1)))[:, None]
        segment = (1-t)**3*curve[0] + 3*(1-t)**2*t*curve[1] + 3*(1-t)*t*t*curve[2] + t**3*curve[3]
        samples.extend(segment[:-1])
    samples.append(points[-1])
    p = np.array(samples)
    p = p[np.r_[True, np.linalg.norm(np.diff(p, axis=0), axis=1) > 1e-6]]
    if len(p) < 2: return ''
    closed = path['closed']
    if closed and np.linalg.norm(p[-1]-p[0]) < 1e-5: p = p[:-1]
    if len(p) < 2: return ''
    direction = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
    if not closed:
        direction[0] = p[1]-p[0]; direction[-1] = p[-1]-p[-2]
    direction /= np.maximum(1e-8, np.linalg.norm(direction, axis=1))[:, None]
    normal = np.column_stack((-direction[:, 1], direction[:, 0]))
    # Same nib and pressure rule for every cel: no frame-dependent jitter.
    pressure = .90 + .20 * ((direction[:, 0] + direction[:, 1]) / math.sqrt(2))**2
    if not closed:
        distances = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
        end_distance = np.minimum(distances, distances[-1]-distances)
        pressure *= .30 + .70 * np.minimum(1, end_distance / max(.1, min(width*2, distances[-1]/3)))
    offset = normal * (width * pressure / 2)[:, None]
    left, right = p+offset, p-offset
    if canvas:
        # Keep expanded ink inside the existing cel. No canvas growth or subject
        # recentering; the subpixel inset avoids introducing clipped opaque edges.
        for edge in (left, right):
            edge[:,0] = np.clip(edge[:,0], .4, canvas[0]-.4)
            edge[:,1] = np.clip(edge[:,1], .4, canvas[1]-.4)
    def outline(vertices):
        return 'M' + ' L'.join(f'{x:.5f} {y:.5f}' for x,y in vertices) + ' Z'
    if closed:
        return outline(left) + ' ' + outline(right[::-1])
    return outline(np.concatenate((left, right[::-1])))


def paint(color):
    return '#' + ''.join(f'{(color >> (8*i)) & 255:02x}' for i in range(3)), ((color >> 24) & 255)/255


def stylize(svg, size, config, decoder):
    width = float(config.get('width', 1.0))
    if not .3 <= width <= 1.2: raise ValueError('Brush width outside reviewed source-pixel range')
    root = ET.fromstring(svg)
    root.set('width', str(size[0])); root.set('height', str(size[1]))
    with tempfile.TemporaryDirectory(prefix='quiver-brush-') as tmp:
        source = Path(tmp)/'source.svg'
        source.write_text(ET.tostring(root, encoding='unicode'))
        shapes = json.loads(subprocess.check_output([str(decoder), '--shapes', str(source)]))
    result = ET.Element(f'{{{SVG}}}svg', dict(width=str(size[0]*6), height=str(size[1]*6),
                                             viewBox=f'0 0 {size[0]} {size[1]}'))
    strokes = 0
    for shape in shapes:
        if not shape['visible']: continue
        if shape['fill_type'] not in (0,1) or shape['stroke_type'] not in (0,1):
            raise ValueError('Brush pass requires solid paints; gradients need separate review')
        group = ET.SubElement(result, f'{{{SVG}}}g', opacity=str(shape['opacity']))
        if shape['fill_type'] == 1:
            color, alpha = paint(shape['fill_color'])
            rgb = [int(color[i:i+2],16) for i in (1,3,5)]
            # Filled ink features (including the already tapered eyebrows) retain
            # their exact geometry. Preserve partial-alpha ground shadows.
            if max(rgb) <= 65 and shape['opacity']*alpha > .9: color = INK
            ET.SubElement(group, f'{{{SVG}}}path', d=' '.join(path_data(p) for p in shape['paths']),
                          fill=color, **{'fill-opacity':str(alpha), 'fill-rule':'evenodd' if shape['fill_rule'] else 'nonzero'})
        if shape['stroke_type'] == 1 and shape['stroke_width'] > 0:
            color, alpha = paint(shape['stroke_color'])
            for path in shape['paths']:
                d = brush_contour(path, width, size)
                if d:
                    ET.SubElement(group, f'{{{SVG}}}path', d=d, fill=INK, **{'fill-opacity':str(alpha), 'fill-rule':'evenodd'})
                    strokes += 1
    return ET.tostring(result, encoding='unicode'), dict(type='vector-brush', width_original=width,
            ink=INK, stroke_paths=strokes, pressure_range=[.9,1.1], open_tip_pressure=.3,
            filled_ink_geometry='preserved', version=1)
