"""Cached drawing data must retain nearest-neighbor geometry and soft edges."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CostumeRasterTests(unittest.TestCase):
    def test_cached_scaling_lighting_mirroring_and_reload(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'raster.cpp'
            binary = Path(directory) / 'raster'
            source.write_text(r'''
#include "hd_costume_raster.h"
#include <cassert>
int main() {
    unsigned int texture[11 * 7];
    for (int i = 0; i < 77; ++i) texture[i] = ((i * 43u % 256) << 24) | (i * 7919u & 0xffffff);
    texture[13] = 0x80808080; texture[14] = 0xff003366;
    HdCostumeRaster::Cache cache;
    cache.scope(9, 1);
    for (int w : {3, 11, 44}) for (int h : {2, 7, 28})
    for (bool mirror : {false, true}) for (int matte : {0, 1, 2})
    for (int light : {0, 128, 255, 272}) {
        HdActorLighting::Tint tint; tint.channel[0] = light; tint.channel[1] = light / 2;
        const auto *pixels = cache.get(texture, 11, 11, 7, w, h, 2, 4, mirror, matte, tint);
        for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
            int sx = x * 11 / w; if (mirror) sx = 10 - sx;
            int sy = y * 7 / h;
            unsigned int expected = texture[sy * 11 + sx] >> 24
                ? tint.apply(matte == 2 ? HdObjectDepth::edgeColor(texture, 11, 11, 7, sx, sy) : HdCostumeEdge::sample(texture, 11, 11, 7, sx, sy, matte)) : 0;
            assert(pixels[y * w + x] == expected);
        }
        assert(cache.get(texture, 11, 11, 7, w, h, 2, 4, mirror, matte, tint) == pixels);
    }
    HdActorLighting::Tint tint;
    texture[0] = 0xff123456; cache.scope(9, 2);
    assert(cache.get(texture, 11, 11, 7, 11, 7, 2, 4, false, false, tint)[0] == texture[0]);
    texture[0] = 0xffabcdef; cache.scope(15, 2);
    assert(cache.get(texture, 11, 11, 7, 11, 7, 2, 4, false, false, tint)[0] == texture[0]);
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(ROOT / 'tools/engine'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)

if __name__ == '__main__': unittest.main()
