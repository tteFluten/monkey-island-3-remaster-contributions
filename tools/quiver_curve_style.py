"""Round sharp joins in Quiver hair paths while retaining their curve geometry."""
import numpy as np


def split(curve, t):
    p = np.asarray(curve, dtype=float)
    a = (1 - t) * p[:-1] + t * p[1:]
    b = (1 - t) * a[:-1] + t * a[1:]
    c = (1 - t) * b[0] + t * b[1]
    return np.array([p[0], a[0], b[0], c]), np.array([c, b[1], a[2], p[3]])


def section(curve, start, end):
    left, _ = split(curve, end)
    return split(left, start / end)[1] if start else left


def rounded_path(points, closed, radius):
    points = np.asarray(points, dtype=float)
    curves = [points[i:i + 4] for i in range(0, len(points) - 1, 3)]
    if not curves: return '', 0
    if closed and np.linalg.norm(curves[-1][-1] - curves[0][0]) > 1e-5:
        a, b = curves[-1][-1], curves[0][0]
        curves.append(np.array([a, a + (b - a) / 3, a + (b - a) * 2 / 3, b]))
    starts, ends = np.zeros(len(curves)), np.ones(len(curves))
    rounded = set()
    for i in range(len(curves) if closed else len(curves) - 1):
        j = (i + 1) % len(curves)
        incoming = curves[i][3] - curves[i][2]
        outgoing = curves[j][1] - curves[j][0]
        if np.linalg.norm(incoming) < 1e-8: incoming = curves[i][3] - curves[i][0]
        if np.linalg.norm(outgoing) < 1e-8: outgoing = curves[j][3] - curves[j][0]
        product = np.linalg.norm(incoming) * np.linalg.norm(outgoing)
        if product < 1e-8 or np.dot(incoming, outgoing) / product > .90: continue
        a = sum(np.linalg.norm(v) for v in np.diff(curves[i], axis=0))
        b = sum(np.linalg.norm(v) for v in np.diff(curves[j], axis=0))
        if min(a, b) < radius * .25: continue
        ends[i] = 1 - min(.25, radius / a)
        starts[j] = min(.25, radius / b)
        rounded.add(i)
    trimmed = [section(c, s, e) for c, s, e in zip(curves, starts, ends)]
    def xy(p): return f'{p[0]:.6f} {p[1]:.6f}'
    d = 'M' + xy(trimmed[0][0])
    for i, curve in enumerate(trimmed):
        d += ' C' + ' '.join(xy(p) for p in curve[1:])
        if i in rounded:
            nxt = trimmed[(i + 1) % len(trimmed)]
            a, b = curve[3], nxt[0]
            u, v = a - curve[2], nxt[1] - b
            distance = np.linalg.norm(b - a) / 3
            u /= max(1e-8, np.linalg.norm(u)); v /= max(1e-8, np.linalg.norm(v))
            d += ' C' + ' '.join(xy(p) for p in (a + u * distance, b - v * distance, b))
    return d + (' Z' if closed else ''), len(rounded)
