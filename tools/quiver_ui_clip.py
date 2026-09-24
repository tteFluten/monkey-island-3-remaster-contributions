"""Flatten only rectangular clips on straight SVG paths, without tracing artwork."""
import math
import re
import xml.etree.ElementTree as ET


def polygons(data):
    token = r'[MmLlHhVvZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
    if re.sub(token, '', data).strip(' ,\t\n\r'):
        raise ValueError('Clip flattening only supports straight path commands')
    values = re.findall(token, data)
    result, points = [], []
    x = y = 0.0
    command = None
    i = 0
    while i < len(values):
        if values[i].isalpha():
            command = values[i]
            i += 1
        if command is None:
            raise ValueError('Missing path command')
        if command.lower() == 'z':
            if not points:
                raise ValueError('Empty closed path')
            x, y = points[0]
            result.append(points)
            points = []
            command = None
            continue
        count = 2 if command.lower() in ('m', 'l') else 1
        numbers = [float(v) for v in values[i:i + count]]
        if len(numbers) != count or not all(math.isfinite(v) for v in numbers):
            raise ValueError('Invalid path coordinates')
        i += count
        relative = command.islower()
        if command.lower() in ('m', 'l'):
            if command.lower() == 'm' and points:
                result.append(points)
                points = []
            x, y = (x + numbers[0], y + numbers[1]) if relative else numbers
        elif command.lower() == 'h':
            x = x + numbers[0] if relative else numbers[0]
        else:
            y = y + numbers[0] if relative else numbers[0]
        points.append((x, y))
        if command.lower() == 'm':
            command = 'l' if relative else 'L'
    if points:
        result.append(points)
    return result


def clip(points, bounds):
    left, top, right, bottom = bounds
    for axis, edge, sign in ((0, left, 1), (0, right, -1), (1, top, 1), (1, bottom, -1)):
        result = []
        for a, b in zip(points[-1:] + points[:-1], points):
            ia, ib = (a[axis] - edge) * sign >= 0, (b[axis] - edge) * sign >= 0
            if ia != ib:
                t = (edge - a[axis]) / (b[axis] - a[axis])
                result.append(tuple(a[j] + t * (b[j] - a[j]) for j in (0, 1)))
            if ib:
                result.append(b)
        points = result
    return points


def flatten(raw):
    if len(raw) > 8_000_000 or re.search(r'<!DOCTYPE|<!ENTITY', raw, re.I):
        raise ValueError('Unsupported SVG document')
    root = ET.fromstring(raw)
    corrections = []
    # Arrow sometimes wraps the whole canvas in a fully opaque alpha mask.
    # Only this exact no-op mask can be removed; luminance/partial masks fail.
    canvas = [float(v) for v in re.split(r'[ ,]+', root.get('viewBox', '').strip())]
    for parent in root.iter():
        for mask in list(parent):
            if mask.tag.split('}')[-1] != 'mask':
                continue
            if (len(mask) != 1 or mask.get('style') != 'mask-type:alpha'
                    or mask.get('maskUnits') != 'userSpaceOnUse'
                    or set(mask.attrib) - {'id', 'x', 'y', 'width', 'height', 'style', 'maskUnits'}):
                raise ValueError('Only opaque full-canvas alpha masks can be removed')
            rect = mask[0]
            region = [float(mask.get(k, 0)) for k in ('x', 'y', 'width', 'height')]
            rectangle = [float(rect.get(k, 0)) for k in ('x', 'y', 'width', 'height')]
            if (rect.tag.split('}')[-1] != 'rect' or len(rect) or region != canvas or rectangle != canvas
                    or set(rect.attrib) - {'x', 'y', 'width', 'height', 'fill'}
                    or not re.fullmatch(r'#[0-9a-fA-F]{6}', rect.get('fill', ''))):
                raise ValueError('Alpha mask must be an opaque rectangle covering the canvas')
            for node in root.iter():
                if node.get('mask') == f'url(#{mask.get("id")})':
                    del node.attrib['mask']
            parent.remove(mask)
            corrections.append(dict(type='remove-opaque-canvas-alpha-mask', mask_id=mask.get('id')))
    bounds = {}
    for node in root.iter():
        if node.tag.split('}')[-1] != 'clipPath':
            continue
        if set(node.attrib) != {'id'} or len(node) != 1:
            raise ValueError('Only plain rectangular clips can be flattened')
        rect = node[0]
        if rect.tag.split('}')[-1] != 'rect' or len(rect) or set(rect.attrib) - {'x', 'y', 'width', 'height', 'transform', 'fill'}:
            raise ValueError('Only plain rectangular clips can be flattened')
        x, y = float(rect.get('x', 0)), float(rect.get('y', 0))
        if 'transform' in rect.attrib:
            match = re.fullmatch(r'translate\(\s*([-+.\d]+)[ ,]+([-+.\d]+)\s*\)', rect.get('transform'))
            if not match:
                raise ValueError('Unsupported clipping transform')
            x += float(match[1]); y += float(match[2])
        width, height = float(rect.get('width')), float(rect.get('height'))
        if not all(math.isfinite(v) for v in (x, y, width, height)) or min(width, height) <= 0:
            raise ValueError('Invalid clip dimensions')
        bounds[node.get('id')] = (x, y, x + width, y + height)
    if not bounds:
        return ET.tostring(root, encoding='unicode'), corrections
    used = []
    for group in root.iter():
        if 'clip-path' not in group.attrib:
            continue
        match = re.fullmatch(r'url\(#([^()]+)\)', group.get('clip-path'))
        if not match or match[1] not in bounds or group.tag.split('}')[-1] != 'g':
            raise ValueError('Unsupported clip reference')
        for path in group:
            if path.tag.split('}')[-1] != 'path' or 'transform' in path.attrib or 'stroke' in path.attrib:
                raise ValueError('Clipping requires untransformed filled paths')
            parts = [clip(points, bounds[match[1]]) for points in polygons(path.get('d', ''))]
            path.set('d', ' '.join('M' + ' L'.join(f'{x:.9g} {y:.9g}' for x, y in points) + ' Z'
                                  for points in parts if points))
        del group.attrib['clip-path']
        used.append(dict(type='flatten-rectangular-clip', clip_id=match[1], bounds=bounds[match[1]],
                         method='Polygon/rectangle intersection; provider path coordinates retained'))
    for parent in root.iter():
        for child in list(parent):
            if child.tag.split('}')[-1] == 'clipPath':
                parent.remove(child)
    return ET.tostring(root, encoding='unicode'), corrections + used
