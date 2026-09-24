"""Solid oval contact shadows follow native feet and preserve scene colors."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class ActorShadowTests(unittest.TestCase):
    def test_feet_position_scaling_elevation_clipping_and_solid_oval(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'shadow.cpp'
            binary = Path(directory) / 'shadow'
            source.write_text(r'''
#include "hd_actor_shadow.h"
#include <cassert>
#include <vector>
int main() {
    const int w = 160, h = 160;
    std::vector<unsigned char> under(w*h, 20), after(under);
    auto body = [&](int x, int top, int width, int height) {
        after = under;
        for (int y = top; y < top + height; ++y)
            for (int xx = x; xx < x + width; ++xx) after[y*w+xx] = 200;
    };
    body(60, 30, 20, 100);
    auto shadow = HdActorShadow::footprint(under.data(), after.data(), w, h, 70, 130, 0);
    assert(shadow.valid && shadow.x >= 69 && shadow.x <= 70 && shadow.y == 127);
    assert(shadow.radiusX > 16.79f && shadow.radiusX < 16.81f);
    assert(shadow.radiusY > 4.03f && shadow.radiusY < 4.04f);
    assert(shadow.opacity == 38);
    // Wally's scripted x origin is zero; his shadow belongs under his sprite.
    auto wally = HdActorShadow::footprint(under.data(), after.data(), w, h, 0, 130, 0);
    assert(wally.valid && wally.x == 69.5f);
    assert(HdActorShadow::groundElevation(0, 381, 381) == 0);
    assert(HdActorShadow::groundElevation(70, 130, 20) == 20);
    assert(HdActorShadow::groundElevation(0, 130, 20) == 20);
    body(80, 50, 20, 100);
    auto walked = HdActorShadow::footprint(under.data(), after.data(), w, h, 90, 150, 0);
    assert(walked.x == shadow.x + 20 && walked.y == shadow.y + 20);
    body(30, 30, 10, 50);
    auto distant = HdActorShadow::footprint(under.data(), after.data(), w, h, 35, 80, 0);
    assert(distant.valid && distant.radiusX < shadow.radiusX);
    // Elevation leaves the shadow on the floor, wider and fainter.
    body(60, 10, 20, 100);
    auto raised = HdActorShadow::footprint(under.data(), after.data(), w, h, 70, 130, 20);
    assert(raised.valid && raised.y == shadow.y && raised.opacity < shadow.opacity);
    assert(raised.radiusX > shadow.radiusX);
    // Hidden feet, a clipped portrait, and a horizontal prop are not casters.
    assert(!HdActorShadow::footprint(under.data(), after.data(), w, h, 70, 155, 0).valid);
    body(60, 60, 20, 100);
    assert(!HdActorShadow::footprint(under.data(), after.data(), w, h, 70, 160, 0).valid);
    body(20, 60, 100, 40);
    assert(!HdActorShadow::footprint(under.data(), after.data(), w, h, 70, 100, 0).valid);
    after = under;
    assert(!HdActorShadow::footprint(under.data(), after.data(), w, h, 0, 0, 0).valid);
    // Uniform 15% black inside the ellipse, preserving floor color and alpha.
    const unsigned int floor = 0x80123456u;
    const auto center = HdActorShadow::shade(floor, 0, 0, shadow.opacity);
    assert(HdActorShadow::shade(0x80ffffffu, 0, 0, shadow.opacity) == 0x80d9d9d9u);
    assert(center == 0x800f2c49u);
    assert(HdActorShadow::shade(floor, 0, 0, 0) == floor);
    assert(HdActorShadow::shade(0xff000000u, 0, 0, shadow.opacity) == 0xff000000u);
    for (int i = -99; i <= 99; ++i) {
        assert(HdActorShadow::shade(floor, i / 100.0f, 0, shadow.opacity) == center);
        assert(HdActorShadow::shade(floor, 0, i / 100.0f, shadow.opacity) == center);
    }
    // A crisp ellipse, not a rectangle or a blur spilling into its corners.
    assert(HdActorShadow::shade(floor, .7f, .7f, shadow.opacity) == center);
    for (int x : {-1, 1}) for (int y : {-1, 1}) {
        assert(HdActorShadow::shade(floor, x * .8f, y * .8f, shadow.opacity) == floor);
        assert(HdActorShadow::shade(floor, (float)x, 0, shadow.opacity) == floor);
        assert(HdActorShadow::shade(floor, 0, (float)y, shadow.opacity) == floor);
    }

}
''')
            include = Path(__file__).resolve().parent / 'engine'
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(include), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
