"""Check scaled metrics and nearest-neighbor bounds at every menu setting."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FontSizeTests(unittest.TestCase):
    def test_layout_and_sampling_bounds(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'font_size.cpp'
            binary = Path(directory) / 'font_size'
            source.write_text(r'''
#include "hd_font_size.h"
#include <cassert>
using namespace Scumm;
int main() {
    assert(hdFontSizePercent(0) == 65);
    assert(hdFontSizePercent(101) == 65);
    assert(hdFontSizeMetric(24, 50) == 12);
    assert(hdFontSizeMetric(13, 50) == 7);
    assert(hdFontSizeMetric(0, 25) == 0);
    for (int percent = 25; percent <= 100; percent += 5) {
        assert(hdFontSizePercent(percent) == percent);
        for (int width = 1; width <= 224; ++width) {
            int scaled = hdFontSizeMetric(width, percent);
            assert(scaled > 0 && scaled <= width);
            for (int x = 0; x < scaled; ++x)
                assert(x * 100 / percent < width);
        }
    }
}
''')
            subprocess.run(['c++', '-std=c++11', '-I', str(ROOT / 'tools/engine'),
                            str(source), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
