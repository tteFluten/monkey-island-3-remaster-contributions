"""Exercise head matte cleanup without changing coverage or other costume parts."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CostumeEdgeTests(unittest.TestCase):
    def test_head_outline_alpha_mirroring_and_body_isolation(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'edge.cpp'
            binary = Path(directory) / 'edge'
            source.write_text(r'''
#include "hd_costume_edge.h"
#include <cassert>
int main() {
    // Asymmetric outline colors make incorrect mirrored lookups observable.
    // The last column is row padding, not part of the artwork.
    unsigned int pixels[] = {
        0x00808080, 0x80808080, 0xff102030, 0xff403020, 0x80808080, 0x00808080, 0xdeadbeef,
        0x00808080, 0x40808080, 0xff102030, 0xff403020, 0x40808080, 0x00808080, 0xdeadbeef
    };
    for (int costume : {2, 25}) for (int cel : {8, 52}) {
        const bool clean = HdCostumeEdge::guybrushHead(costume, cel);
        for (int y = 0; y < 2; ++y) for (int x = 0; x < 6; ++x) {
            const auto original = pixels[y * 7 + x];
            const auto result = HdCostumeEdge::sample(pixels, 7, 6, 2, x, y, clean);
            assert((result >> 24) == (original >> 24));
            if (!clean || (original >> 24) == 0 || (original >> 24) == 255)
                assert(result == original);
        }
    }
    assert(HdCostumeEdge::sample(pixels, 7, 6, 2, 1, 0, true) == 0x80102030);
    assert(HdCostumeEdge::sample(pixels, 7, 6, 2, 4, 0, true) == 0x80403020);
    // An antialiased dark outline next to opaque skin must not become skin.
    const unsigned int ink[] = {0x00111111, 0x80111111, 0xffffd0b0};
    assert(HdCostumeEdge::sample(ink, 3, 3, 1, 1, 0, true) == ink[1]);
    const unsigned int hair[] = {0x00a0b0f0, 0x80a0b0f0, 0xff203040};
    assert(HdCostumeEdge::sample(hair, 3, 3, 1, 1, 0, true) == hair[1]);
    // Reflection happens before the lookup: the soft edge follows its outline.
    unsigned int mirrored[12];
    for (int y = 0; y < 2; ++y) for (int x = 0; x < 6; ++x)
        mirrored[y * 6 + x] = pixels[y * 7 + 5 - x];
    for (int y = 0; y < 2; ++y) for (int x = 0; x < 6; ++x)
        assert(HdCostumeEdge::sample(mirrored, 6, 6, 2, x, y, true) ==
               HdCostumeEdge::sample(pixels, 7, 6, 2, 5 - x, y, true));
    assert(pixels[6] == 0xdeadbeef && pixels[13] == 0xdeadbeef);
}
'''.replace('#include <cassert>', '#include <cassert>\n#include <initializer_list>'))
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-g',
                            '-I', str(ROOT / 'tools/engine'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
