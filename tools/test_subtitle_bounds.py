"""Check subtitle safe areas against the actual cropped presentation geometry."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SubtitleBoundsTests(unittest.TestCase):
    def test_bounds_stay_visible_across_displays_and_room_layouts(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / 'common').mkdir()
            (temp / 'common/hd_aspect.h').write_bytes((ROOT / 'tools/engine/hd_aspect.h').read_bytes())
            source = temp / 'bounds.cpp'
            source.write_text(r'''
#include "hd_subtitle_bounds.h"
#include <cassert>
int main() {
    const int displays[][2] = {{2560,1440},{2560,1600},{3456,2234},{3440,1440},{960,800}};
    for (const auto &display : displays) for (int width : {640,864}) for (bool cover : {false,true}) {
        const auto safe = HdSubtitleBounds::safeArea(display[0],display[1],width,cover);
        const auto draw = HdAspect::game(display[0],display[1],169,width,cover);
        assert(safe.x > 0 && safe.y > 0 && safe.w > 0 && safe.h > 0);
        assert(safe.x + safe.w < width && safe.y + safe.h < 480);
        // Project the text bounds into physical pixels independently of the
        // safe-area calculation. Every edge must be inside the actual display.
        assert(draw.x + double(safe.x) * draw.w / width > 0);
        assert(draw.y + double(safe.y) * draw.h / 480 > 0);
        assert(draw.x + double(safe.x + safe.w) * draw.w / width < display[0]);
        assert(draw.y + double(safe.y + safe.h) * draw.h / 480 < display[1]);
    }
    const auto wide = HdSubtitleBounds::safeArea(3440,1440,640,true);
    assert(wide.y > 60 && wide.y + wide.h < 420); // Cropped top/bottom.
    const auto tall = HdSubtitleBounds::safeArea(2560,1600,864,true);
    assert(tall.x > 50 && tall.x + tall.w < 814); // Cropped panorama sides.
    const auto pending = HdSubtitleBounds::safeArea(0,0,640,false);
    assert(pending.x == 16 && pending.y == 12 && pending.w == 608 && pending.h == 456);
}
'''.replace('#include <cassert>', '#include <cassert>\n#include <initializer_list>'))
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(temp), '-I', str(ROOT / 'tools/engine'),
                            str(source), '-o', str(temp / 'bounds')], check=True)
            subprocess.run([str(temp / 'bounds')], check=True)


if __name__ == '__main__':
    unittest.main()
