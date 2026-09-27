"""Banner boxes over a retained HD frame, with native sanitizers."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class BannerTests(unittest.TestCase):
    def test_box_replaces_only_the_banner_area(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'banner.cpp'
            source.write_text(r'''
#include "hd_banner.h"
#include <cassert>
#include <vector>
using namespace HdBanner;
int main() {
    const int w = 16, h = 12, pitch = 20, scale = 4;
    std::vector<U8> base(pitch * h, 7), native(pitch * h, 7), palette(768, 0);
    palette[3 * 9] = 10; palette[3 * 9 + 1] = 20; palette[3 * 9 + 2] = 30;
    palette[3 * 7] = 1;
    // Unchanged screen: no box, frame untouched (the "No" restore redraw).
    Rect r = changed(native.data(), pitch, base.data(), pitch, w, h);
    assert(r.empty() && r.left == 0 && r.right == 0);
    // A box drawn with a fill that partly matches the original index.
    for (int y = 3; y < 6; ++y) for (int x = 2; x < 9; ++x) native[y * pitch + x] = 9;
    native[4 * pitch + 5] = 7; // same index as underneath, inside the box
    native[2 * pitch + 19] = 1; // beyond the visible width: ignored
    r = changed(native.data(), pitch, base.data(), pitch, w, h);
    assert(r.left == 2 && r.top == 3 && r.right == 9 && r.bottom == 6);
    std::vector<U32> frame(w * scale * h * scale, 0x11223344u);
    paint(frame.data(), w * scale, w * scale, h * scale, native.data(), pitch, r, scale, palette.data());
    const U32 box = 10u | 20u << 8 | 30u << 16 | 0xff000000u;
    for (int y = 0; y < h * scale; ++y)
        for (int x = 0; x < w * scale; ++x) {
            const bool inside = x >= 2 * scale && x < 9 * scale && y >= 3 * scale && y < 6 * scale;
            const U32 value = frame[y * w * scale + x];
            if (!inside) assert(value == 0x11223344u);
            else if (x / scale == 5 && y / scale == 4) assert(value == (1u | 0xff000000u));
            else assert(value == box);
        }
    // Clipped to the frame at the edges.
    Rect edge; edge.left = w - 1; edge.top = h - 1; edge.right = w; edge.bottom = h;
    paint(frame.data(), w * scale, w * scale - 2, h * scale - 2, native.data(), pitch, edge, scale, palette.data());
    assert(frame[(h * scale - 1) * w * scale + w * scale - 1] == 0x11223344u);
    assert(frame[(h * scale - 3) * w * scale + w * scale - 3] == (1u | 0xff000000u));

    // Quit-prompt shape: page (0), box fill (5) with bevel (6), two buttons (8).
    const int W = 64, H = 40;
    std::vector<U8> screen(W * H, 0);
    for (int y = 4; y < 36; ++y) for (int x = 4; x < 60; ++x)
        screen[y * W + x] = (y == 4 || y == 35 || x == 4 || x == 59) ? 6 : 5;
    for (int y = 22; y < 32; ++y) for (int x = 10; x < 26; ++x) screen[y * W + x] = 8;
    for (int y = 22; y < 32; ++y) for (int x = 38; x < 54; ++x) screen[y * W + x] = 8;
    Rect found;
    // Message: above the buttons, below the bevel, between the side bevels.
    assert(container(screen.data(), W, W, H, 20, 44, 12, found));
    assert(found.left == 5 && found.right == 59 && found.top == 5 && found.bottom == 22);
    // Button label: the button itself.
    assert(container(screen.data(), W, W, H, 14, 22, 27, found));
    assert(found.left == 10 && found.right == 26 && found.top == 22 && found.bottom == 32);
    // A stray pixel of another colour in the line does not choose the fill.
    screen[27 * W + 15] = 5;
    assert(container(screen.data(), W, W, H, 14, 22, 27, found) && found.left == 10 && found.right == 26);
    assert(!container(screen.data(), W, W, H, 14, 22, H, found));
    assert(!container(screen.data(), W, W, H, 30, 30, 10, found));
    // Centring: HD ink [inkStart, inkEnd) into a native box at 4x.
    assert(centreOffset(100, 140, 22, 32, 4) == -12);   // 12 HD px up to the centre
    assert(centreOffset(88, 128, 22, 32, 4) == 0);
    assert(meantCentred(100, 140, 20, 40, 4));      // gaps 20 / 20
    assert(meantCentred(90, 140, 20, 40, 4));       // gaps 10 / 20: nudged
    assert(!meantCentred(84, 104, 20, 60, 4));      // left-aligned: gaps 4 / 136
    assert(!meantCentred(60, 200, 20, 40, 4));      // wider than its box
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(source),
                            '-o', str(root / 'banner')], check=True, capture_output=True)
            subprocess.run([str(root / 'banner')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
