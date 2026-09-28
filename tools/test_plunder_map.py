"""Exercise authored map regions and physical-to-script input with sanitizers."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class PlunderMapTests(unittest.TestCase):
    def test_destinations_framing_empty_scenery_and_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'map.cpp'
            source.write_text(r'''
#include "hd_plunder_map.h"
#include "hd_aspect.h"
#include <cassert>
#include <cmath>
#include <initializer_list>
#include <cstdio>
using namespace HdPlunderMap;
int main() {
    const Point landmarks[] = {{230,350},{355,587},{795,548},{867,466},
        {577,435},{637,334},{700,412},{654,703}};
    const int oldBoxes[][4] = {{88,144,224,192},{184,248,288,304},{536,232,592,272},
        {592,176,640,248},{376,168,432,256},{416,128,488,216},{432,144,560,200},{392,272,520,368}};
    assert(kCount == 8);
    for (unsigned i = 0; i < kCount; ++i) {
        assert(target(landmarks[i].x, landmarks[i].y) == int(i));
        int x, y; script(landmarks[i].x, landmarks[i].y, x, y);
        assert(x >= oldBoxes[i][0] && x < oldBoxes[i][2] && y >= oldBoxes[i][1] && y < oldBoxes[i][3]);
        // Every polygon interior resolves consistently, including points
        // close to its edges. Regions must never overlap another destination.
        for (int py = 0; py < 1000; ++py) for (int px = 0; px < 1000; ++px)
            if (polygon(kDestinations[i].outline,kDestinations[i].count,px+.25,py+.25)) {
                if (target(px+.25,py+.25) != int(i)) fprintf(stderr, "Overlap %u at %d,%d with %d\n",i,px,py,target(px+.25,py+.25));
                assert(target(px+.25,py+.25) == int(i));
            }
    }
    for (Point p : {Point{50,50},Point{500,210},Point{500,750},Point{940,850},Point{350,450}}) {
        int x,y; script(p.x,p.y,x,y); assert(x==320 && y==476);
    }
    const Point sizes[] = {{2560,1440},{2560,1600},{3440,1440},{1280,720},{3456,2234}};
    for (Point size : sizes) {
        // Cover the display with uniform scaling, cropping the excess artwork.
        const auto outer = HdAspect::frame(size.x,size.y,169,true);
        assert(outer.x <= 0 && outer.y <= 0);
        assert(outer.x + outer.w >= size.x && outer.y + outer.h >= size.y);
        const auto rect = HdAspect::game(size.x,size.y,169,640,true);
        const double wide = rect.h * 16.0/9.0;
        const double left = rect.x + (rect.w-wide)/2;
        for (unsigned i=0;i<kCount;++i) {
            int x,y;
            assert(pointer(std::round(left+landmarks[i].x*wide/1000),
                std::round(rect.y+landmarks[i].y*rect.h/1000),rect.x,rect.y,rect.w,rect.h,x,y));
            assert(x==kDestinations[i].x && y==kDestinations[i].y);
        }
        int x,y;
        assert(!pointer(std::floor(left)-1,rect.y+rect.h/2,rect.x,rect.y,rect.w,rect.h,x,y));
        assert(!pointer(rect.x,rect.y-1,rect.x,rect.y,rect.w,rect.h,x,y));
        assert(pointer(std::ceil(left)+1,rect.y+rect.h/2,rect.x,rect.y,rect.w,rect.h,x,y));
        assert(x==320 && y==476); // Old left margin is accepted, but is empty sea.
    }
    for (double x=0;x<640;x+=.25) {
        assert(std::abs(interpolate(kX,interpolate(kX,x),true)-x)<1e-8);
        assert(interpolate(kX,x+.25)>interpolate(kX,x));
    }
    assert(std::abs(sourceX((405-256)/2.4)-108)<1e-8);
    assert(std::abs(sourceY(420/2.4)-165)<1e-8);
    assert(water(40,750,10,70,170));
    assert(water(704,521,10,160,210));
    assert(!water(500,100,20,160,200)); // Sky.
    assert(!water(650,695,20,160,200)); // Fort, irrespective of hue.
    assert(!water(840,642,20,160,200)); // Painted sailboat.
    assert(!water(704,521,170,90,20)); // Dry warm paint inside a broad region.
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(source), '-o', str(root / 'map')],
                           check=True)
            subprocess.run([str(root / 'map')], check=True)


if __name__ == '__main__':
    unittest.main()
