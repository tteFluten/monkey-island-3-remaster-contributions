"""Compile reviewed room-space water regions into the native shader's coverage router."""
import json
from pathlib import Path

CATALOG = Path(__file__).with_name('water_regions.json')


def catalog():
    return json.loads(CATALOG.read_text())


def header():
    data = catalog()
    rooms = data['regions']
    lines = ['// Generated from water_regions.json by the engine patcher.',
             '#ifndef COMMON_HD_WATER_REGIONS_H', '#define COMMON_HD_WATER_REGIONS_H',
             'namespace HdWater {', 'struct Point { double x, y; };',
             '''template<unsigned N> inline bool polygon(const Point (&p)[N], double x, double y) {
    bool inside = false;
    for (unsigned i = 0, j = N - 1; i < N; j = i++)
        if ((p[i].y > y) != (p[j].y > y) &&
            x < (p[j].x - p[i].x) * (y - p[i].y) / (p[j].y - p[i].y) + p[i].x)
            inside = !inside;
    return inside;
}''', 'inline bool mappedRoom(int room) { switch (room) {',
             ' '.join(f'case {room}:' for room in rooms) + ' return true;',
             'default: return false; } }',
             '''inline bool mapped(int room, double x, double y, unsigned r, unsigned g, unsigned b) {
    // Hue alone never selects a surface: each color test is constrained by
    // reviewed room-space polygons, excluding sky and dry foreground details.
    const bool blue = b > 6 && b * 100 > r * 112 && b * 100 > g * 70;
    const bool navy = blue && b * 100 > g * 145;
    switch (room) {''']
    for room, info in rooms.items():
        lines.append(f'    case {room}: {{ // {info["name"]}')
        groups = []
        for key in ('polygons', 'holes'):
            names = []
            for index, points in enumerate(info.get(key, [])):
                name = f'{key}{index}'
                names.append(f'polygon({name}, x, y)')
                lines.append('        static const Point ' + name + '[] = {' +
                             ', '.join('{' + f'{x}, {y}' + '}' for x, y in points) + '};')
            if names:
                groups.append(('!' if key == 'holes' else '') + '(' + ' || '.join(names) + ')')
        color = {'any': 'true', 'blue': 'blue', 'navy': 'navy'}[info['palette']]
        lines.append('        return ' + ' && '.join([color, *groups]) + ';\n    }')
    lines += ['    default: return false;', '    }', '}']
    for function, fields in (('ambient', ('remove', 'mixed')), ('mixedOverlay', ('mixed',))):
        lines.append(f'inline bool {function}(int room, int costume) {{ switch (room) {{')
        for room, info in data['overlays'].items():
            costumes = [costume for field in fields for costume in info.get(field, [])]
            if costumes:
                lines.append(f'    case {room}: return ' + ' || '.join(f'costume == {c}' for c in costumes) + ';')
        lines += ['    default: return false;', '} }']
    lines += ['}', '#endif', '']
    return '\n'.join(lines)
