"""Autosave: chapter cards, Load-page tiles and save ages."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class AutosaveTests(unittest.TestCase):
    def test_age_and_tiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'autosave.cpp'
            source.write_text(r'''
#include "hd_autosave.h"
#include <cassert>
using namespace HdAutosave;
int main() {
    const unsigned date = 27u << 24 | 9u << 16 | 2026u;
    assert(minutes(date, 10u << 8 | 5) - minutes(date, 9u << 8 | 50) == 15);
    assert(minutes(1u << 24 | 10u << 16 | 2026u, 0) - minutes(30u << 24 | 9u << 16 | 2026u, 23u << 8 | 59) == 1);
    assert(minutes(1u << 24 | 3u << 16 | 2028u, 0) - minutes(29u << 24 | 2u << 16 | 2028u, 0) == 1440);
    assert(minutes(1u << 24 | 1u << 16 | 1970u, 0) == 0);
    assert(chapterCard(4) && chapterCard(8) && chapterCard(88) && !chapterCard(9) && !chapterCard(92) && !chapterCard(3));
    assert(loadSlot(1) == 0 && loadSlot(7) == 6);
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(source),
                            '-o', str(root / 'autosave')], check=True, capture_output=True)
            subprocess.run([str(root / 'autosave')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
