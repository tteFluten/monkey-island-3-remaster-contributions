"""Z-plane foreground depth of field: blur, feathered coverage and blending."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class DepthOfFieldTests(unittest.TestCase):
    def test_blur_coverage_and_mix(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'depth.cpp'
            binary = Path(directory) / 'depth'
            source.write_text(r'''
#include "hd_depth_of_field.h"
#include "hd_object_depth.h"
#include <cassert>
#include <cstdlib>
#include <vector>
using namespace HdDepthOfField;
static int channel(unsigned int p, int c) { return (p >> (c * 8)) & 255; }
int main() {
    assert(level(-1) == 0 && level(0) == 0 && level(1) == 1 && level(2) == 2 && level(9) == 2);
    assert(radius(0, 4) == 0 && radius(1, 4) == 8 && radius(2, 4) == 16 && radius(2, 6) == 24);
    assert(factor(1) == 1 && factor(2) == 1 && factor(4) == 2 && factor(6) == 3);

    // Tuning: presets unless overridden, clamped hotkey steps, HD scaling.
    Tuning t = tuning(0, 2, 100);
    assert(blurTenths(0, t) == 0 && blurTenths(1, t) == 20 && blurTenths(2, t) == 40);
    assert(radiusTenths(blurTenths(1, t), 4) == radius(1, 4) && radiusTenths(blurTenths(2, t), 6) == radius(2, 6));
    assert(radiusTenths(25, 4) == 10 && radiusTenths(5, 4) == 2);
    t = step(2, t, 1, 0, 0);
    assert(t.blurTenths == 45 && blurTenths(1, t) == 45);
    t = step(1, tuning(0, 2, 100), -1, 0, 0);
    assert(t.blurTenths == 15);
    t = step(0, tuning(0, 2, 100), 1, 0, 0);   // off: steps from the Low preset
    assert(t.blurTenths == 25);
    for (int i = 0; i < 40; ++i) t = step(2, t, -1, -1, -1);
    assert(t.blurTenths == 5 && t.edge == 0 && t.intensity == 0);
    for (int i = 0; i < 40; ++i) t = step(2, t, 1, 1, 1);
    assert(t.blurTenths == 120 && t.edge == 12 && t.intensity == 100);
    t = tuning(-3, 99, -5);
    assert(t.blurTenths == 0 && t.edge == 12 && t.intensity == 0);
    t = tuning(2, 0, 150);
    assert(t.blurTenths == 5 && t.edge == 0 && t.intensity == 100 && t.depth == 1);
    assert(tuning(0, 2, 100, 0).depth == 1 && tuning(0, 2, 100, 9).depth == 7);
    t = step(2, tuning(0, 2, 100, 3), 0, 0, 0, 1);
    assert(t.depth == 4 && t.blurTenths == 0);
    for (int i = 0; i < 10; ++i) t = step(2, t, 0, 0, 0, -1);
    assert(t.depth == 1);

    // A flat painting stays exactly flat and opaque, for 3- and 4-byte pixels.
    const int w = 37, h = 23;
    std::vector<unsigned char> rgb(w * h * 3), rgba(w * h * 4);
    for (int i = 0; i < w * h; ++i) {
        rgb[i * 3] = 10; rgb[i * 3 + 1] = 120; rgb[i * 3 + 2] = 250;
        rgba[i * 4] = 10; rgba[i * 4 + 1] = 120; rgba[i * 4 + 2] = 250; rgba[i * 4 + 3] = 0;
    }
    std::vector<unsigned int> out;
    int ow, oh;
    for (int bpp : {3, 4}) {
        blur(bpp == 3 ? rgb.data() : rgba.data(), w * bpp, bpp, w, h, 2, 16, out, ow, oh);
        assert(ow == 19 && oh == 12 && (int)out.size() == ow * oh);
        for (unsigned int p : out) assert(p == 0xfffa780au);
        for (int y = 0; y < h * 2; ++y)
            for (int x = 0; x < w * 2; ++x)
                assert(sample(out.data(), ow, oh, 2, x, y) == 0xfffa780au);
    }

    // Radius 0 at factor 1 is the identity (alpha forced opaque).
    std::vector<unsigned char> noise(w * h * 4);
    for (size_t i = 0; i < noise.size(); ++i) noise[i] = (unsigned char)(i * 37 + i / 5);
    blur(noise.data(), w * 4, 4, w, h, 1, 0, out, ow, oh);
    assert(ow == w && oh == h);
    for (int i = 0; i < w * h; ++i) {
        assert((out[i] >> 24) == 255);
        for (int c = 0; c < 3; ++c) assert(channel(out[i], c) == noise[i * 4 + c]);
        assert(sample(out.data(), ow, oh, 1, i % w, i / w) == out[i]);
    }

    // A bright point spreads symmetrically, keeps most energy and loses its peak.
    const int s = 41;
    std::vector<unsigned char> dot(s * s * 3, 0);
    for (int y = 19; y <= 21; ++y)
        for (int x = 19; x <= 21; ++x) dot[(y * s + x) * 3 + 1] = 255;
    blur(dot.data(), s * 3, 3, s, s, 1, 3, out, ow, oh);
    long energy = 0;
    for (unsigned int p : out) energy += channel(p, 1);
    assert(std::labs(energy - 9 * 255) < 9 * 255 / 10);
    const int peak = channel(out[20 * s + 20], 1);
    assert(peak > 0 && peak < 255);
    for (int d = 1; d < 10; ++d) {
        assert(channel(out[20 * s + 20 - d], 1) == channel(out[20 * s + 20 + d], 1));
        assert(channel(out[(20 - d) * s + 20], 1) == channel(out[(20 + d) * s + 20], 1));
        assert(channel(out[20 * s + 20 + d], 1) <= channel(out[20 * s + 19 + d], 1));
    }
    assert(channel(out[0], 1) == 0);

    // Coverage counts planes 1..n-1 (plane 0 ignored), with camera offset:
    // plane 1 alone is farther scenery, the block inside both planes is nearest.
    const int vw = 64, vh = 32, strips = vw / 8 + 1;
    std::vector<unsigned char> planes(3 * vh * strips, 0);
    auto setBit = [&](int z, int x, int y, int offset) {
        planes[(z * vh + y) * strips + (x + offset) / 8] |= 0x80 >> ((x + offset) & 7);
    };
    const int offset = 3;
    for (int y = 0; y < vh; ++y)
        for (int x = 0; x < vw; ++x) {
            if (x < 20) setBit(0, x, y, offset);   // plane 0 is not an occluder
            if (x >= 40) setBit(1, x, y, offset);
            if (x >= 44 && x < 48 && y >= 10 && y < 14) setBit(2, x, y, offset);
        }
    auto row = [&](int y, int z) -> const unsigned char * { return &planes[(z * vh + y) * strips]; };
    std::vector<unsigned char> cover;
    assert(coverage(row, 3, vw, vh, offset, 0, cover));
    for (int y = 0; y < vh; ++y)
        for (int x = 0; x < vw; ++x) {
            const int count = HdObjectDepth::masked(row(y, 1), x, offset) +
                              HdObjectDepth::masked(row(y, 2), x, offset);
            assert(cover[y * vw + x] == (count == 2 ? 255 : count == 1 ? 128 : 0));
            assert(count == (x >= 44 && x < 48 && y >= 10 && y < 14 ? 2 : x >= 40 ? 1 : 0));
        }
    // Only plane 0 (or a single-plane room) has no foreground at all.
    assert(!coverage(row, 1, vw, vh, offset, 2, cover));
    for (unsigned char c : cover) assert(c == 0);
    // Depth 2 keeps only the nearest block, at full strength; larger depths clamp.
    for (int depth : {2, 3, 9}) {
        assert(coverage(row, 3, vw, vh, offset, 0, cover, depth));
        for (int yy = 0; yy < vh; ++yy)
            for (int x = 0; x < vw; ++x)
                assert(cover[yy * vw + x] == ((x >= 44 && x < 48 && yy >= 10 && yy < 14) ? 255 : 0));
    }
    auto none = [&](int, int) -> const unsigned char * { return nullptr; };
    assert(!coverage(none, 3, vw, vh, offset, 2, cover));

    // Feathered: zero well outside, full well inside, monotonic across the edge.
    assert(coverage(row, 2, vw, vh, offset, 2, cover));
    const int y = vh / 2;
    assert(cover[y * vw + 30] == 0 && cover[y * vw + 37] == 0);
    assert(cover[y * vw + 42] == 255 && cover[y * vw + 63] == 255);
    for (int x = 37; x < 42; ++x) assert(cover[y * vw + x] < cover[y * vw + x + 1]);
    assert(cover[0 * vw + 50] == 255 && cover[(vh - 1) * vw + 50] == 255);

    // HD coverage interpolates between native pixels and stays in range.
    for (int hx = 0; hx < vw * 4; ++hx) {
        const int a = coverageAt(cover.data(), vw, vh, 4, hx, y * 4);
        assert(a >= 0 && a <= 255);
        if (hx > 0) assert(a >= coverageAt(cover.data(), vw, vh, 4, hx - 1, y * 4));
    }
    assert(coverageAt(cover.data(), vw, vh, 4, 0, 0) == 0);
    assert(coverageAt(cover.data(), vw, vh, 4, vw * 4 - 1, vh * 4 - 1) == 255);

    // Mix endpoints, midpoint and alpha preservation.
    const unsigned int sharp = 0x80102030u, soft = 0xfff0e0d0u;
    assert(mix(sharp, soft, 0) == sharp);
    assert(mix(sharp, soft, 255) == 0x80f0e0d0u);
    const unsigned int half = mix(sharp, soft, 128);
    assert((half >> 24) == 0x80);
    for (int c = 0; c < 3; ++c)
        assert(std::abs(channel(half, c) - (channel(sharp, c) + channel(soft, c)) / 2) <= 1);
}
''')
            include = Path(__file__).resolve().parent / 'engine'
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(include), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
