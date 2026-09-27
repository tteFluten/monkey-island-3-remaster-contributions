"""Water routing, dry-scene exclusions, shoreline guards and room-coordinate masks."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/engine'))
from water_regions import catalog, header


class WaterTests(unittest.TestCase):
    def test_room_audit_is_complete_and_disjoint(self):
        data = catalog()
        groups = [set(data[key]) for key in ('existing', 'regions', 'excluded')]
        scenes = {str(d['scene']['roomNumber']): d['scene']['name']
                  for p in (ROOT / 'data/scenes').glob('*.json') for d in [json.loads(p.read_text())]}
        self.assertEqual(set.union(*groups), set(scenes))
        self.assertEqual(sum(map(len, groups)), len(scenes))
        for group in ('existing', 'regions', 'excluded'):
            for room, info in data[group].items():
                self.assertEqual(info['name'], scenes[room])
                if group == 'regions':
                    self.assertIn(info['palette'], ('blue', 'navy', 'any'))
                    self.assertTrue(info['polygons'])
                    for polygon in info['polygons'] + info.get('holes', []):
                        self.assertGreaterEqual(len(polygon), 3)
                        self.assertTrue(all(0 <= x <= 1000 and 0 <= y <= 1000 for x, y in polygon))
        for room, info in data['overlays'].items():
            self.assertIn(room, groups[0] | groups[1])
            ids = info['remove'] + info.get('mixed', [])
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(info['note'])

    def test_native_routing_and_shoreline_boundaries(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / 'common').mkdir()
            (out / 'common/hd_water_regions.h').write_text(header())
            source = out / 'water.cpp'
            source.write_text(r'''
#include "hd_water.h"
#include <cassert>
#include <vector>
using namespace HdWater;
int main() {
    const int rooms[] = {9,10,11,13,14,15,22,26,27,29,31,33,34,35,36,37,
        40,41,42,43,44,45,46,47,48,49,50,51,53,54,58,59,74,75,76,77,78};
    for (int r : rooms) assert(room(r));
    for (int r : {1,4,28,38,39,52,56,57,60,65,68,80,82,83,85,87,92}) assert(!room(r));
    assert(ambient(10,45) && ambient(11,51) && ambient(14,73) && ambient(15,83));
    // Story poses and impacts must never be removed as ambient water.
    for (int c : {34,46,47}) assert(!ambient(10,c));
    for (int c : {49,54,57}) assert(!ambient(11,c));
    const int overlays[][2] = {{15,85},{29,164},{31,177},{33,187},{33,188},
        {37,211},{37,212},{44,253},{54,277},{54,278},{75,369},{75,370},{77,376}};
    for (const auto &p : overlays) assert(ambient(p[0],p[1]));
    // Waterfalls, physical boats/hull edges, sharks, splashes and story poses.
    const int preserved[][2] = {{29,165},{29,166},{33,186},{37,210},{37,213},
        {37,214},{37,215},{37,216},{37,217},{75,368},{75,374},{77,377},{77,378},{77,379},{77,380}};
    for (const auto &p : preserved) assert(!ambient(p[0],p[1]));
    assert(mixedOverlay(37,212) && !mixedOverlay(37,211));
    unsigned char palette[768] = {};
    palette[3]=20; palette[4]=60; palette[5]=70; // Teal ripples.
    palette[6]=90; palette[7]=60; palette[8]=30; // Brown boat.
    const unsigned char under[] = {0,0,0,1}, after[] = {1,2,1,1};
    unsigned char display[] = {1,2,3,1}; // Third pixel occluded by another actor.
    removeOverlay(display,under,after,4,palette,true);
    assert(display[0]==0 && display[1]==2 && display[2]==3 && display[3]==1);
    removeOverlay(display,under,after,4,palette,false);
    assert(display[0]==0 && display[1]==0 && display[2]==3 && display[3]==1);
    assert(mapped(13,900,850,20,60,150));
    assert(mapped(49,550,370,20,30,150));
    assert(mapped(76,500,580,20,60,150));
    assert(mapped(77,950,970,20,60,150)); // Tall-room bottom, not screen bottom.
    assert(!mapped(49,550,370,160,100,30)); // Brown paint inside an ROI stays dry.
    const int dry[][3] = {{13,500,500},{22,500,800},{29,250,800},{33,500,850},
        {34,300,350},{35,700,800},{36,500,800},{37,700,450},{44,170,750},
        {45,250,400},{49,180,380},{53,390,650},{74,500,500},{75,800,800},
        {76,500,750},{77,650,750},{78,200,650}};
    // Even blue-colored actors/wood/land/sky cannot pass an excluded region.
    for (const auto &p : dry) assert(!mapped(p[0],p[1],p[2],20,30,150));
    for (int size : {1,2,3,10,700}) {
        std::vector<unsigned char> wet(size*size,2), depth(size*size,255);
        std::vector<unsigned short> edge(size*size);
        unsigned count = surfaceDepth(wet.data(),size,size,edge.data(),depth.data(),1);
        for (int i=0;i<size;++i) {
            assert(depth[i]==0 && depth[(size-1)*size+i]==0);
            assert(depth[i*size]==0 && depth[i*size+size-1]==0);
        }
        if (size>4) { assert(count>0); assert(depth[(size/2)*size+size/2]>0); }
        if (size==700) assert(depth[350*size+350]==254);
        wet[(size/2)*size+size/2]=0;
        surfaceDepth(wet.data(),size,size,edge.data(),depth.data(),1);
        assert(depth[(size/2)*size+size/2]==0);
    }
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I', str(out),
                            '-I', str(ROOT / 'tools/engine'), str(source), '-o', str(out / 'water')],
                           check=True, capture_output=True)
            subprocess.run([str(out / 'water')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
