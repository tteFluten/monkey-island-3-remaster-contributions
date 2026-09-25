"""Native renderer regression: room objects must not paint over fallback actors."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ObjectDepthTests(unittest.TestCase):
    def test_native_actor_occlusion_ui_transparency_and_scrolling(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'depth.cpp'
            binary = Path(directory) / 'depth'
            source.write_text(r'''
#include "hd_object_depth.h"
#include <cassert>
#include <vector>
int main() {
    // Cached z-buffer rows must match the old resource lookup even when the
    // camera starts partway through an eight-pixel strip.
    unsigned char masks[128];
    for (int i = 0; i < 128; ++i) masks[i] = (i * 37 + 19) & 255;
    for (int camera = 0; camera < 32; ++camera)
        for (int x = 0; x < 640; ++x) {
            bool original = masks[(x + camera) / 8] & (0x80 >> ((x + camera) & 7));
            assert(HdObjectDepth::masked(masks + camera / 8, x, camera & 7) == original);
            assert(!HdObjectDepth::masked(nullptr, x, camera & 7));
        }
    // The actor draws at 0 and 2. At 1 it is hidden by original foreground;
    // at 2 its pixel is subsequently covered by UI. Only 0 survives.
    unsigned char under[] = {10, 20, 30, 40};
    unsigned char after[] = {50, 20, 60, 40};
    unsigned char display[] = {50, 20, 99, 40};
    unsigned char actors[] = {0, 0, 0, 0};
    HdObjectDepth::protectActor(actors, display, under, after, 4);
    assert(actors[0] == 1 && actors[1] == 0 && actors[2] == 0 && actors[3] == 0);
    // Overlapping actors accumulate coverage, and stationary poses can reuse it.
    unsigned char front[] = {50, 20, 99, 70};
    HdObjectDepth::protectActor(actors, front, display, front, 4);
    assert(actors[0] == 1 && actors[3] == 1);
    const unsigned int matte[] = {0x00808080, 0x80808080, 0xfe003366};
    assert(HdObjectDepth::edgeColor(matte, 3, 3, 1, 0, 0) == matte[0]);
    assert(HdObjectDepth::edgeColor(matte, 3, 3, 1, 1, 0) == 0x80003366);
    assert(HdObjectDepth::edgeColor(matte, 3, 3, 1, 2, 0) == matte[2]);
    const unsigned int isolated = 0x80808080;
    assert(HdObjectDepth::edgeColor(&isolated, 1, 1, 1, 0, 0) == isolated);
    // Soft PNG edges blend into an opaque scene continuously across 127/128;
    // transparent gray matte RGB must not introduce a dotted pale outline.
    for (unsigned int coverage = 0; coverage <= 255; ++coverage) {
        unsigned int background = 0xff203040;
        unsigned int edge = (coverage << 24) | 0x00808080;
        unsigned char noActor = 0, covered = 0;
        HdObjectDepth::blit(&background, 1, 1, 1, &edge, 1, 1, 1,
                            0, 0, 1, &noActor, &covered);
        assert((background >> 24) == 255);
        for (unsigned int channel = 0; channel < 3; ++channel) {
            unsigned int original = (0xff203040 >> (channel * 8)) & 255;
            unsigned int expected = (128 * coverage + original * (255 - coverage) + 127) / 255;
            assert(((background >> (channel * 8)) & 255) == expected);
        }
        assert(covered == 1); // Keep native low-resolution pixels suppressed.
    }
    // GPU scene alpha measures foreground opacity, not background opacity.
    // Successive translucent objects must leave the correct background share.
    for (unsigned int behind : {0u, 64u, 128u, 255u}) {
        for (unsigned int alpha = 0; alpha <= 255; ++alpha) {
            unsigned int scene = (behind << 24) | 0x00203040;
            unsigned int sprite = (alpha << 24) | 0x00808080;
            unsigned char noActor = 0, covered = 0;
            HdObjectDepth::blit(&scene, 1, 1, 1, &sprite, 1, 1, 1,
                               0, 0, 1, &noActor, &covered);
            assert((scene >> 24) == alpha + (behind * (255 - alpha) + 127) / 255);
        }
    }
    for (int scale : {4, 6}) {
        int w = 4 * scale, h = scale, pitch = w + 2;
        std::vector<unsigned int> dest(pitch * h, 0xff112233);
        std::vector<unsigned int> object(w * h, 0xffabcdef);
        std::vector<unsigned char> alpha(w * h, 0);
        // Transparent source must preserve underlying scene color.
        for (int y = 0; y < h; ++y) object[y * w + 2 * scale] = 0;
        HdObjectDepth::blit(dest.data(), pitch, w, h, object.data(), w, w, h,
                            0, 0, scale, actors, alpha.data());
        for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
            bool actor = x < scale || x >= 3 * scale;
            assert(dest[y * pitch + x] == ((actor || x == 2 * scale) ? 0xff112233 : 0xffabcdef));
            assert(alpha[y * w + x] == (actor ? 0 : 1));
        }
        // Scrolled objects may start off either viewport edge. Check padding
        // and canaries too, including negative Y; never form an out-of-bounds pointer.
        std::vector<unsigned int> guarded(pitch * h + 2, 0xff112233);
        for (int left : {-w, -scale, w - scale, w}) {
            HdObjectDepth::blit(guarded.data() + 1, pitch, w, h, object.data(), w,
                                w, h, left, -1, scale, actors, alpha.data());
            assert(guarded.front() == 0xff112233 && guarded.back() == 0xff112233);
            for (int y = 0; y < h; ++y)
                assert(guarded[1 + y * pitch + w] == 0xff112233);
        }
        // Fully replaced HD poses are omitted from this mask, leaving a clean
        // object underlay before the HD actor is composited in the later pass.
        unsigned char replaced[] = {0, 0, 0, 0};
        HdObjectDepth::blit(dest.data(), pitch, w, h, object.data(), w, w, h,
                            0, 0, scale, replaced, alpha.data());
        assert(dest[0] == 0xffabcdef);
    }
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-g',
                            '-I', str(ROOT / 'tools/engine'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
