"""Presentation camera dynamics, subpixel sampling and engine patch wiring."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class CameraTests(unittest.TestCase):
    def test_spring_and_world_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'camera.cpp').write_text(r'''
#include "hd_camera.h"
#include "hd_motion.h"
#include <cassert>
#include <set>
using namespace HdCamera;
int main() {
    Axis a; a.reset(0);
    double last = 0;
    for (int i = 0; i < 180; ++i) {
        a.step(100, 1.0/60, 0, 200);
        assert(a.position >= last && a.position <= 100);
        last = a.position;
    }
    assert(a.position == 100 && !a.moving());
    // Constant-target closed form is independent of display cadence.
    Axis b, c; b.reset(0); c.reset(0);
    for (int i = 0; i < 60; ++i) b.step(100, 1.0/60, 0, 200);
    for (int i = 0; i < 30; ++i) c.step(100, 1.0/30, 0, 200);
    assert(std::fabs(b.position - c.position) < 1e-10);
    Axis variable; variable.reset(0);
    for (int i = 0; i < 20; ++i) {
        variable.step(100, .01, 0, 200);
        variable.step(100, .04, 0, 200);
    }
    assert(std::fabs(variable.position - b.position) < 1e-10);
    // Slow motion still generates distinct fractional camera positions.
    Follow f; f.reset(432, 240, 410, 1, 1000);
    HdMotion::Track walk; walk.sample(432, 410, 2, true);
    std::set<double> poses;
    for (int tick = 1; tick <= 12; ++tick) {
        walk.sample(432 + tick, 410, 2, false);
        for (unsigned frame = 1; frame <= 5; ++frame) {
            f.step(walk.preciseX(frame * 1024 / 5), walk.preciseY(frame * 1024 / 5),
                1000 + ((tick - 1) * 5 + frame) * (1000.0/60), 432, 1664, 240, 240);
            poses.insert(f.x.position);
            assert(f.x.position >= 432 && f.x.position <= walk.x);
            assert(f.y.position == 240);
            assert(std::fabs(f.x.position - anchor(f.x.position)) <= .5);
        }
    }
    assert(poses.size() == 60 && walk.x == 444 && walk.y == 410);
    assert(f.moving()); // Walker has stopped; camera still needs presentation.
    for (int i = 1; i <= 180; ++i) f.step(444, 410, 2000+i*(1000.0/60), 432,1664,240,240);
    assert(!f.moving() && f.x.position == 444);
    // Route bends and reversals follow actual actor positions in both axes.
    f.reset(600, 400, 550, 1, 0);
    for (int i = 1; i <= 60; ++i) f.step(600+i, 550, i*(1000.0/60), 432,1664,240,1000);
    const double cornerX = f.x.position;
    for (int i = 61; i <= 120; ++i) f.step(660, 550+i-60, i*(1000.0/60), 432,1664,240,1000);
    assert(f.x.position >= cornerX && f.x.position <= 660 && f.y.position > 400);
    for (int i = 121; i <= 300; ++i) f.step(450, 450, i*(1000.0/60), 432,1664,240,1000);
    assert(f.x.position >= 450 && std::fabs(f.x.position-450) < .01);
    assert(f.y.position >= 300 && std::fabs(f.y.position-300) < .01);
    // Script bounds and edges don't retain hidden spring momentum.
    f.step(2000, 2000, 5020, 432,500,240,240);
    assert(f.x.position <= 500 && f.y.position == 240 && f.y.velocity == 0);
    for (int i=1; i<=180; ++i) f.step(2000,2000,5020+i*(1000.0/60),432,500,240,240);
    assert(f.x.position == 500 && f.x.velocity == 0);
    // Lifecycle reset clears velocity, offset, actor identity and elapsed time.
    f.reset(700, 300, 600, 0, 9999);
    assert(!f.moving() && !f.actor && f.x.position==700 && f.x.velocity==0 && f.verticalOffset==-300);
    f.reset(500, 300, 600, 1, 10000);
    f.step(600, 600, 9000, 432,1664,240,1000);
    assert(f.x.position==500); // No negative-time integration.
    f.step(600, 600, 900000, 432,1664,240,1000);
    assert(f.x.position < 520); // No catch-up sweep after a display stall.
    // Shared world resampling, including alpha, with edge-replicated gutters.
    unsigned src[8] = {0xff000000,0xff404040,0xff808080,0xffc0c0c0,
                       0xff202020,0xff606060,0xffa0a0a0,0xffe0e0e0}, dst[8];
    translate(src,4,dst,4,4,2,0,0);
    for(int i=0;i<8;++i) assert(src[i]==dst[i]);
    translate(src,4,dst,4,4,2,.5,.5);
    assert(dst[0]==0xff303030 && dst[3]==0xffd0d0d0 && dst[7]==0xffe0e0e0);
    translate(src,4,dst,4,4,2,-.5,-.5);
    assert(dst[0]==src[0] && dst[7]==0xffb0b0b0);
    assert(anchor(432.49)==432 && anchor(432.51)==433);
    for (double x=432; x<1664; x+=.1) {
        assert(std::fabs(x-rasterAnchor(x,true)) <= 4.00001);
        assert(std::fabs(x-rasterAnchor(x,false)) <= .50001);
    }
    Click click;
    click.record(15, 200, 300, 600.25, 10.75);
    // A later camera pose does not change the queued world-space click.
    assert(click.consume(15, true) && click.x + anchor(click.left) == 800);
    assert(click.y + anchor(click.top) == 311 && !click.consume(15, true));
    click.record(15, 200, 300, 600, 10);
    assert(!click.consume(77, true)); // Room changes discard a pending click.
    click.record(15, 200, 300, 600, 10);
    assert(!click.consume(15, false)); // Cancelled click does not survive a tick.
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(root / 'camera.cpp'),
                            '-o', str(root / 'camera')], check=True, capture_output=True)
            subprocess.run([str(root / 'camera')], check=True, capture_output=True, timeout=10)


if __name__ == '__main__': unittest.main()
