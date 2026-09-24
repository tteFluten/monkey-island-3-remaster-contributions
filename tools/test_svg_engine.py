"""Exercise the native SVG decoder with the engine's pinned NanoSVG implementation.

Run tools/build_engine.sh first to obtain the pinned headers. No browser or Sharp
is involved in these tests; the bytes are the engine decoder's straight RGBA.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.playtest/engine/source'


class NativeSVGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SOURCE / 'graphics/nanosvg/nanosvg.h').exists() or not shutil.which('c++'):
            raise unittest.SkipTest('Build the pinned engine before testing its SVG decoder')
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cpp = Path(cls.temp.name) / 'decode.cpp'
        cls.binary = cpp.with_suffix('')
        cpp.write_text('''
#define NANOSVG_IMPLEMENTATION
#define NANOSVGRAST_IMPLEMENTATION
#include "quiver_svg.h"
#include "quiver_native.h"
#include <iostream>
#include <iterator>
int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "underlay") {
        // Two overlapping originals; only the middle two positions were drawn
        // by the front actor. Pixel 3 is later dialogue and must survive.
        unsigned char scene[] = {10, 20, 30, 40};
        unsigned char back[] = {1, 2, 3, 4};
        unsigned char front[] = {10, 21, 31, 40};
        unsigned char display[] = {10, 21, 31, 99};
        QuiverNative::removeActor(display, scene, front, 4);
        QuiverNative::removeActor(display, back, scene, 4);
        if (display[0] != 1 || display[1] != 2 || display[2] != 3 || display[3] != 99) return 3;
        // A missing back replacement is never removed (the caller omits it).
        unsigned char fallback[] = {10, 21, 31, 99};
        QuiverNative::removeActor(fallback, scene, front, 4);
        return fallback[0] == 10 && fallback[1] == 20 && fallback[2] == 30 && fallback[3] == 99 ? 0 : 4;
    }
    if (argc != 3) return 2;
    std::string xml((std::istreambuf_iterator<char>(std::cin)), std::istreambuf_iterator<char>());
    std::vector<unsigned char> rgba;
    if (!QuiverSVG::render(xml, std::atoi(argv[1]), std::atoi(argv[2]), rgba)) return 1;
    std::cout.write(reinterpret_cast<const char *>(rgba.data()), rgba.size());
    return 0;
}
''')
        subprocess.run(['c++', '-std=c++11', '-O1', '-I', str(SOURCE), '-I', str(ROOT / 'tools/engine'),
                        str(cpp), '-o', str(cls.binary)], check=True, capture_output=True)

    def decode(self, xml, width=80, height=120, accepted=True):
        result = subprocess.run([str(self.binary), str(width), str(height)], input=xml.encode(),
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0 if accepted else 1, result.stderr.decode())
        self.assertEqual(len(result.stdout), width * height * 4 if accepted else 0)
        return result.stdout

    def test_canvas_transform_straight_alpha_and_both_resolutions(self):
        xml = '<svg width="120" height="180" viewBox="0 0 20 30"><g transform="translate(5 6)"><path fill="#c83214" opacity="0.5" d="M0 0h5v12H0z"/></g></svg>'
        for scale in (4, 6):
            with self.subTest(scale=scale):
                w = 20 * scale
                rgba = self.decode(xml, w, 30 * scale)
                def pixel(x, y):
                    p = (y * w + x) * 4
                    return tuple(rgba[p:p + 4])
                self.assertEqual(pixel(0, 0)[3], 0)
                self.assertEqual(pixel(4 * scale, 8 * scale)[3], 0)
                r, g, b, a = pixel(7 * scale, 8 * scale)
                # NanoSVG premultiplies/unpremultiplies with integer rounding.
                for actual, expected in zip((r, g, b), (200, 50, 20)):
                    self.assertLessEqual(abs(actual - expected), 2)
                self.assertIn(a, (127, 128))
                self.assertEqual(pixel(11 * scale, 8 * scale)[3], 0)

    def test_local_gradient(self):
        xml = '<svg viewBox="0 0 20 30"><defs><linearGradient id="g"><stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs><rect width="20" height="30" fill="url(#g)"/></svg>'
        rgba = self.decode(xml)
        self.assertGreater(rgba[(60 * 80 + 5) * 4], rgba[(60 * 80 + 75) * 4])
        self.assertEqual(rgba[3], 255)

    def test_rejects_bad_canvas_and_empty_art(self):
        for xml in ('<svg viewBox="0 0 80 80"><path d="M0 0h80v80z"/></svg>',
                    '<svg width="0" height="30"/>', '<svg width="20" height="30"/>',
                    '<svg width="nan" height="30"><path d="M0 0h1v1z"/></svg>'):
            with self.subTest(xml=xml):
                self.decode(xml, accepted=False)

    def test_rejects_unsupported_active_and_malformed_documents(self):
        for part in ('<image href="https://example.com/a.png"/>', '<script/>', '<text>Hi</text>',
                     '<clipPath/>', '<mask/>', '<use href="#a"/>', '<path onclick="x"/>',
                     '<path fill="url(https://example.com/a)"/>', '<path style="filter:blur(3px)"/>',
                     '<g><path/></svg>', '<path d="M0 0"', '<path fill=red/>'):
            with self.subTest(part=part):
                self.decode('<svg viewBox="0 0 20 30">' + part + '</svg>', accepted=False)
        self.decode('<!DOCTYPE svg><svg/>', accepted=False)
        self.decode('<svg/>garbage', accepted=False)
        self.decode('<svg/>\0', accepted=False)

    def test_rejects_unbounded_output(self):
        xml = '<svg viewBox="0 0 20 30"><path d="M0 0h20v30z"/></svg>'
        for width, height in ((0, 120), (-1, 120), (9000, 13500), (4096, 6144)):
            self.decode(xml, width, height, accepted=False)

    def test_original_pixels_removed_before_svg_with_depth_and_ui_preserved(self):
        subprocess.run([str(self.binary), 'underlay'], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
