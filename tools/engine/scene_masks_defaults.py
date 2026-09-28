"""Expose the same source geometry used by the water renderers to the editor."""
import json
import re
from pathlib import Path
HERE = Path(__file__).parent

def header():
    rooms = json.loads((HERE / 'water_regions.json').read_text())['regions']
    lines = ['#ifndef HD_SCENE_MASKS_DEFAULTS_H', '#define HD_SCENE_MASKS_DEFAULTS_H',
             '#include "common/hd_scene_masks.h"', 'namespace HdMasks {',
             'inline Water defaults(int room, const std::string &source) { Water w;']
    for room, file, size, positive, holes, palette in [
        (13, 'hd_plunder_map.h', (1000,1000), ['sea','bay','cove'], ['ship','wrecks'], 'blue'),
        (29, 'hd_voodoo_exterior.h', (2048,1152), ['pools'], ['bridge','path','foreground'], 'voodoo')]:
        text = (HERE / file).read_text()
        source = re.search(r'kSource\[\] = "([^"]+)"', text)[1]
        lines += [f'if (room == {room} && source == "{source}") {{', f'w.authored = true; w.palette = "{palette}";']
        for name in positive + holes:
            body = re.search(r'Point '+name+r'\[\] = \{(.*?)\};', text, re.S)[1]
            points = [(float(x)*1000/size[0], float(y)*1000/size[1]) for x,y in re.findall(r'\{(\d+),(\d+)\}', body)]
            lines += ['w.'+('zones' if name in positive else 'holes')+'.push_back({'+','.join('{%.12g,%.12g}'%p for p in points)+'});']
        lines += ['return w; }']
    lines += ['switch(room) {']
    for room, data in rooms.items():
        lines += [f'case {room}: w.authored = true; w.palette = "{data["palette"]}";']
        for field, dest in [('polygons','zones'),('holes','holes')]:
            for ring in data.get(field,[]):
                lines += ['w.'+dest+'.push_back({'+','.join('{%s,%s}'%(x,y) for x,y in ring)+'});']
        lines += ['break;']
    lines += ['default: break; } return w; }', '}', '#endif']
    return '\n'.join(lines)+'\n'
