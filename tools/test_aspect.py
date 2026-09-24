"""Presentation geometry and real boundary behavior, with native sanitizers."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class AspectTests(unittest.TestCase):
    def test_viewports_output_input_and_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'aspect.cpp'
            source.write_text(r'''
#include "hd_aspect.h"
#include <cassert>
#include <initializer_list>
using namespace HdAspect;
int main() {
    assert(preference(0) == 43 && preference(169) == 169);
    assert(viewport(43, 2096, 480) == 640);
    assert(viewport(169, 2096, 480) == 864);
    assert(viewport(169, 864, 480) == 864);
    assert(viewport(169, 863, 480) == 640);
    assert(viewport(169, 640, 2044) == 640);
    assert(viewport(169, 1200, 1200) == 640);
    Rect r = game(2560, 1920, 43, 640);
    assert(r.x == 0 && r.y == 0 && r.w == 2560 && r.h == 1920);
    r = game(2560, 1440, 169, 640);
    assert(r.x == 320 && r.y == 0 && r.w == 1920 && r.h == 1440);
    r = game(2560, 1440, 169, 864);
    assert(r.x == -16 && r.y == 0 && r.w == 2592 && r.h == 1440);
    // At 3x display scale, the visible edges map to native pixels 5..858.
    assert((0 - r.x) * 864 / r.w == 5);
    assert((2559 - r.x) * 864 / r.w == 858);
    for (int width : {640, 1280, 1920, 2560, 3840}) {
        for (int height : {480, 720, 1080, 1440, 2160}) {
            Rect f = frame(width, height, 169);
            r = game(width, height, 169, 640);
            assert(f.x >= 0 && f.y >= 0 && f.w <= width && f.h <= height);
            assert(r.h == f.h && r.w * 480 / 640 <= r.h);
        }
    }
    assert(camera(320, 2096, 864, 320, 1776) == 432);
    assert(camera(1776, 2096, 864, 320, 1776) == 1664);
    assert(camera(320, 896, 864, 320, 320) == 432); // fixed script camera
    assert(camera(800, 896, 864, 800, 800) == 464);
    assert(camera(600, 2096, 864, 700, 500) == 600);
    Buttons b;
    int x = 12, y = 34;
    assert(!b.accept(false, 1, 0, x, y) && b.pressed == 0);
    assert(!b.accept(true, 0, 1, x, y)); // margin press, center release
    assert(b.accept(true, 1, 0, x, y) && b.pressed == 1);
    x = 999; y = 999;
    assert(!b.accept(false, 0, 0, x, y));
    assert(b.accept(false, 0, 1, x, y)); // center press, margin release
    assert(x == 12 && y == 34 && b.pressed == 0);
    assert(!b.accept(false, 0, 1, x, y)); // no orphan release
    assert(b.accept(true, 2, 0, x, y));
    assert(b.accept(true, 4, 0, x, y));
    assert(b.accept(false, 0, 2, x, y) && b.pressed == 4);
    assert(b.accept(false, 0, 4, x, y) && b.pressed == 0);
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(source),
                            '-o', str(root / 'aspect')], check=True, capture_output=True)
            subprocess.run([str(root / 'aspect')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
