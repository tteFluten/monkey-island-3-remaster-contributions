"""Options-book layout: placement, pointer mapping and the Text Size slider."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class BookLayoutTests(unittest.TestCase):
    def test_layout_round_trips_and_stays_on_the_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'layout.cpp'
            source.write_text(r'''
#include "hd_book_layout.h"
#include <cassert>
using namespace HdBookLayout;
int main() {
    // Controls stay inside the 640x480 surface, clear of the bottom caption
    // line, the Text Size slider and each other.
    for (int i = 0; i < kMoveCount; ++i) {
        const Box t = kMoves[i].target();
        assert(t.left >= 0 && t.top >= 40 && t.right <= 640 && t.bottom <= 420);
        assert(!(t.left < kSizeHit.right && kSizeHit.left < t.right && t.top < kSizeHit.bottom && kSizeHit.top < t.bottom));
        for (int j = 0; j < kMoveCount; ++j) {
            if (i == j) continue;
            const Box u = kMoves[j].target(), s = kMoves[i].source, r = kMoves[j].source;
            assert(!(t.left < u.right && u.left < t.right && t.top < u.bottom && u.top < t.bottom));
            assert(!(s.left < r.right && r.left < s.right && s.top < r.bottom && r.top < s.bottom));
        }
    }
    // Script items move with their control; hidden and unrelated ones do not.
    int x = 48, y = 79; assert(place(x, y) && x == 48 && y == 66);          // Effects Volume label
    x = 211; y = 320; assert(place(x, y) && x == 211 && y == 265);         // Text Speed knob
    x = 48; y = 270; assert(place(x, y) && x == 160 && y == 358);          // Text checkbox
    x = 472; y = 272; assert(place(x, y) && x == 496 && y == 328);         // Quit
    x = 48; y = 374; assert(!place(x, y));                                  // 3D acceleration box
    x = 83; y = 376; assert(!place(x, y));                                  // ... and its label
    x = 320; y = 430; assert(place(x, y) && x == 320 && y == 430);          // caption line
    // Pointer: every placed hotspot point maps back to its original spot.
    const int points[][2] = {{150, 116}, {60, 258}, {60, 282}, {210, 330}, {60, 362}, {472, 110}, {472, 170},
                             {472, 210}, {472, 250}, {472, 290}};
    for (const auto &p : points) {
        int px = p[0], py = p[1];
        assert(place(px, py));
        int capture = kFree;
        toScript(px, py, capture, false);
        assert(px == p[0] && py == p[1] && capture == kFree);
    }
    // Empty paper, the Text Size slider and the margins reach no hotspot.
    const int empty[][2] = {{150, 235}, {60, 415}, {150, 330}, {500, 420}, {10, 10}, {630, 200}};
    for (const auto &p : empty) {
        int px = p[0], py = p[1], capture = kFree;
        toScript(px, py, capture, false);
        assert(px == kNeutralX && py == kNeutralY);
    }
    // A slider drag keeps its control while held, then releases it.
    int capture = kFree, px = 190, py = 103;     // Effects knob on its new row
    toScript(px, py, capture, true);
    assert(capture == 0 && px == 190 && py == 116);
    px = 260; py = 300;                          // dragged off the row
    toScript(px, py, capture, true);
    assert(capture == 0 && px == 260 && py == 313);
    px = 260; py = 300;
    toScript(px, py, capture, false);
    assert(capture == kFree && px == kNeutralX);
    // A press on empty paper stays neutral even when dragged onto a control.
    capture = kFree; px = 150; py = 450;
    toScript(px, py, capture, true);
    assert(capture == -1);
    px = 150; py = 100;
    toScript(px, py, capture, true);
    assert(px == kNeutralX && py == kNeutralY);
    // Save/Load spread: slot columns move onto their pages; page corners
    // (x < 48, x >= 592) and the centred captions stay where they were.
    x = 78; y = 56; placeSlot(x, y); assert(x == 63 && y == 56);            // number 1
    x = 98; y = 184; placeSlot(x, y); assert(x == 83 && y == 184);          // slot 2 frame/stamp
    x = 402; y = 312; placeSlot(x, y); assert(x == 445 && y == 312);        // slot 6 frame/stamp
    x = 320; y = 445; placeSlot(x, y); assert(x == 320 && y == 445);        // caption
    for (int i = 0; i < kSlotMoveCount; ++i) {
        const Box t = kSlotMoves[i].target();
        assert(t.left >= 48 && t.right <= 592);                             // corners keep their zones
        assert(kSlotMoves[i].source.left + 144 + kSlotMoves[i].dx <= 640);
    }
    x = 155; y = 240; slotToScript(x, y); assert(x == 170 && y == 240);     // slot 2 hotspot
    x = 500; y = 100; slotToScript(x, y); assert(x == 457 && y == 100);     // slot 4 hotspot
    x = 10; y = 250; slotToScript(x, y); assert(x == 10 && y == 250);       // left page corner
    x = 40; y = 250; slotToScript(x, y); assert(x == 40 && y == 250);       // ... its whole zone
    assert(slotNumberAt(78, 56) && slotNumberAt(93, 312) && slotNumberAt(382, 184) && slotNumberAt(362, 200));
    assert(!slotNumberAt(168, 160) && !slotNumberAt(472, 288) && !slotNumberAt(320, 445) && !slotNumberAt(40, 56));
    x = 620; y = 250; slotToScript(x, y); assert(x == 620 && y == 250);     // right page corner
    x = 320; y = 460; slotToScript(x, y); assert(x == 320 && y == 460);     // below the slots
    // Language row: below Quit, clear of every script control and the caption.
    for (int i = 0; i < kLanguageCount; ++i) {
        const Box row = {kLanguageX[i] - 2, kLanguageY - 2, kLanguageX[i] + kLanguageWidth, kLanguageY + kCheckbox + 2};
        assert(row.right <= 640 && row.bottom <= 420 && targetAt(row.left, row.top) < 0 && targetAt(row.right - 1, row.bottom - 1) < 0);
        assert(kMoves[11].target().bottom <= row.top);                          // below Quit
        assert(languageAt(kLanguageX[i] + 10, kLanguageY + 12) == i);
    }
    assert(kLanguageX[0] + kLanguageWidth <= kLanguageX[1]);
    assert(languageAt(400, 360) < 0 && languageAt(300, 390) < 0);
    // Text Size slider: ends, steps and knob travel.
    assert(sizeKnobX(25) == kSliderLeft && sizeKnobX(100) == kSliderLeft + kSliderWidth - kKnobWidth);
    assert(sizeKnobX(10) == sizeKnobX(25) && sizeKnobX(120) == sizeKnobX(100));
    assert(sizeAt(0) == 25 && sizeAt(639) == 100);
    for (int p = 25; p <= 100; p += 5) assert(sizeAt(sizeKnobX(p) + kKnobWidth / 2) == p);
    for (int x = 0, last = 0; x < 640; ++x) { const int s = sizeAt(x); assert(s >= last && s % 5 == 0); last = s; }
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(source),
                            '-o', str(root / 'layout')], check=True, capture_output=True)
            subprocess.run([str(root / 'layout')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
