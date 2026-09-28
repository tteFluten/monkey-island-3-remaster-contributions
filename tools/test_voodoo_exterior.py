"""Round-trip registered walking/input geometry and shoreline exclusions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VoodooExteriorTests(unittest.TestCase):
    def test_registered_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / 'common').mkdir()
            for name in ('hd_plunder_map.h', 'hd_aspect.h'):
                (temp / 'common' / name).write_bytes((ROOT / 'tools/engine' / name).read_bytes())
            source = temp / 'test.cpp'
            source.write_text(r'''
#include "hd_voodoo_exterior.h"
#include "common/hd_aspect.h"
#include <cassert>
#include <cmath>
int main() {
    using namespace HdVoodooExterior;
    // No foldovers or discontinuities: the engine's connected walkboxes stay
    // connected, and pointer hits return to the same original script position.
    for(int x=0;x<640;++x) {
        assert(paintX(x+1)>paintX(x));
        assert(std::abs(nativeX(paintX(x))-x)<1e-6);
        assert(std::abs(sourceX((paintX(x)-256)/2.4)-x)<1e-6);
    }
    for(int y=0;y<480;++y) {
        assert(paintY(y+1)>paintY(y));
        assert(std::abs(nativeY(paintY(y))-y)<1e-6);
    }
    // Entrance/exit follows the painted bottom path and joins the unchanged
    // interior smoothly. Scenery and other parts of the room get no offset.
    assert(entranceOffset(0,465)==260);
    assert(entranceOffset(14,459)>240);
    assert(entranceOffset(103,420)==0);
    assert(entranceOffset(300,354)==0);
    assert(entranceOffset(29,261)==0);
    for(int x=0;x<100;++x)assert(entranceOffset(x,450)>=entranceOffset(x+1,450));
    for(int y=390;y<460;++y)assert(std::abs(entranceOffset(50,y+1)-entranceOffset(50,y))<=14);
    const int sizes[][2]={{1280,720},{1280,800},{1720,720},{3456,2234}};
    for(const auto &size:sizes) {
        const auto r=HdAspect::game(size[0],size[1],169,640,true);
        for(int x=10;x<630;x+=7) for(int y=10;y<460;y+=9) {
            const int px=std::lround(r.x+(paintX(x)-256)*r.w/1536);
            const int py=std::lround(r.y+paintY(y)*r.h/1152);
            int sx,sy;
            assert(pointer(px,py,r.x,r.y,r.w,r.h,sx,sy));
            assert(std::abs(sx-x)<=2 && std::abs(sy-y)<=2);
        }
    }
    assert(water(100,820,60,100,160));
    assert(water(1860,920,60,100,160));
    assert(water(1500,1090,60,100,160));
    // Geometry excludes land even if blue lighting passes the color guard.
    assert(!water(1400,810,60,100,160));
    assert(!water(650,900,60,100,160));
    assert(!water(400,1100,60,100,160));
    assert(!water(1400,300,60,100,160));
    assert(!water(1090,340,60,100,160));
    int x,y; assert(!pointer(0,0,0,0,0,0,x,y));
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(temp), '-I', str(ROOT / 'tools/engine'),
                            str(source), '-o', str(temp / 'test')], check=True)
            subprocess.run([str(temp / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
