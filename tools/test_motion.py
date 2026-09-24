"""Deterministic drawing timelines, without changing simulation timing."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class MotionTests(unittest.TestCase):
    def test_camera_layers_endpoints_discontinuities_and_clock_wrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'motion.cpp').write_text(r'''
#include "hd_motion.h"
#include <cassert>
#include <set>
int main() {
    HdMotion::Clock clock;
    HdMotion::Track camera, foreground;
    bool reset = clock.sample(14, 1000, true);
    camera.sample(320, 240, 14, reset);
    foreground.sample(700, 300, 73, reset);
    assert(!camera.moving && !foreground.moving);
    reset = clock.sample(14, 1083, true);
    camera.sample(350, 240, 14, reset);
    foreground.sample(715, 300, 73, reset);
    std::set<int> positions;
    for (unsigned t = 1083; t < 1166; t += 17) {
        auto fraction = clock.fraction(t);
        positions.insert(camera.atX(fraction));
        assert(camera.atX(fraction) >= 320 && camera.atX(fraction) <= 350);
        assert(foreground.atX(fraction) >= 700 && foreground.atX(fraction) <= 715);
    }
    assert(positions.size() == 5); // Five distinct draws from a single native tick.
    assert(camera.x == 350 && foreground.x == 715); // Presentation never moves simulation targets.
    assert(camera.atX(clock.fraction(1166)) == 350);
    assert(camera.atX(clock.fraction(9000)) == 350); // No extrapolation on a stall.
    camera.sample(320, 240, 14, false);
    assert(camera.atX(512) == 335 && camera.atX(1024) == 320);
    camera.sample(900, 240, 14, false); // Room jumps snap instead of sweeping.
    assert(!camera.moving && camera.atX(0) == 900);
    foreground.sample(800, 300, 74, false); // A new costume must not inherit old motion.
    assert(!foreground.moving && foreground.atX(0) == 800);
    assert(clock.sample(15, 1200, true));
    assert(clock.sample(15, 1300, false)); // Menu / cutscene bypass.
    assert(!clock.valid && clock.sample(15, 1400, true));
    assert(clock.sample(15, 2000, true)); // Pause / load / hitch.
    clock.sample(15, 0xfffffff0u, true);
    assert(!clock.sample(15, 0x43u, true));
    assert(clock.interval == 83 && clock.fraction(0x43u) == 0);
    assert(clock.fraction(0x96u) == 1024);
    // Twelve simulation targets coexist with sixty visual positions per second.
    HdMotion::Track walk;
    walk.sample(0, 0, 2, true);
    int ticks = 0, draws = 0;
    for (int step = 1; step <= 12; ++step) {
        walk.sample(step * 10, 0, 2, false); ++ticks;
        for (unsigned fraction = 0; fraction < 1024; fraction += 205) {
            assert(walk.atX(fraction) <= walk.x); ++draws;
        }
    }
    assert(ticks == 12 && draws == 60 && walk.x == 120);
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(root / 'motion.cpp'),
                            '-o', str(root / 'motion')], check=True, capture_output=True)
            subprocess.run([str(root / 'motion')], check=True, capture_output=True, timeout=10)


if __name__ == '__main__': unittest.main()
