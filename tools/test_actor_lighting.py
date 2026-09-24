"""HD actors must follow native palette lighting without changing their alpha."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ActorLightingTests(unittest.TestCase):
    def test_native_palette_shading_and_transparency(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'lighting.cpp'
            binary = Path(directory) / 'lighting'
            source.write_text(r'''
#include "hd_actor_lighting.h"
#include <cassert>
#include <cstring>
#include <initializer_list>
int main() {
    unsigned char base[768] = {}, current[768] = {};
    unsigned int usage[256] = {};
    auto neutral = HdActorLighting::fromPalette(base, current, usage);
    assert(neutral.apply(0x80123456u) == 0x80123456u);

    // Guybrush's shirt and skin in room 9 use these native palette colors.
    const unsigned char colors[][3] = {{247, 247, 231}, {255, 199, 175}, {23, 15, 7}};
    const int gains[] = {200, 180, 130};
    for (int i = 0; i < 3; ++i) {
        usage[235 + i] = 100 + i * 10;
        for (int c = 0; c < 3; ++c) {
            base[(235 + i) * 3 + c] = colors[i][c];
            current[(235 + i) * 3 + c] = colors[i][c] * gains[c] / 255;
        }
    }
    // Unused white padding slots map to unrelated dark scene colors.
    // They must not change the recovered actor lighting.
    for (int i = 16; i < 220; ++i)
        for (int c = 0; c < 3; ++c) {
            base[i * 3 + c] = 255;
            current[i * 3 + c] = 10;
        }
    auto shaded = HdActorLighting::fromPalette(base, current, usage);
    for (int c = 0; c < 3; ++c) assert(shaded.channel[c] == gains[c]);
    // Little-endian RGBA: white becomes warm brown, alpha is unchanged.
    assert(shaded.apply(0x80ffffffu) == 0x8082b4c8u);
    assert(shaded.apply(0x00ffffffu) == 0x0082b4c8u);
    assert(shaded.apply(0xff000000u) == 0xff000000u);

    // Palette changes affect the same stationary pose immediately, including
    // returning to neutral after a room transition or a restored save.
    std::memcpy(current, base, sizeof(base));
    neutral = HdActorLighting::fromPalette(base, current, usage);
    assert(neutral.apply(0x807bbdf3u) == 0x807bbdf3u);
    std::memset(current, 0, sizeof(current));
    auto dark = HdActorLighting::fromPalette(base, current, usage);
    assert(dark.apply(0x80ffffffu) == 0x80000000u);

    // Fully clipped actors have no samples; they must not retain stale tint.
    std::memset(usage, 0, sizeof(usage));
    neutral = HdActorLighting::fromPalette(base, current, usage);
    assert(neutral.apply(0x80ffffffu) == 0x80ffffffu);

    // Brightening clamps each RGB channel rather than spilling into alpha.
    HdActorLighting::Tint bright;
    bright.channel[0] = bright.channel[1] = bright.channel[2] = 512;
    assert(bright.apply(0x80808080u) == 0x80ffffffu);

    auto strong = shaded.enhanced();
    assert(strong.channel[0] == 206 && strong.channel[1] == 191 && strong.channel[2] == 161);
    assert((strong.apply(0x807bbdf3u) >> 24) == 0x80);
    // Recorded cannon-room walk: the grate raises green while red is fixed.
    // Keep that color transition pronounced, along with the warm right side
    // and darker left corner. These fixtures come from the live room palette.
    HdActorLighting::Tint grate = shaded, right = shaded, left = shaded;
    grate.channel[1] = 198;
    right.channel[0] = 251;
    left.channel[0] = 165; left.channel[1] = 149; left.channel[2] = 95;
    auto lit = grate.enhanced(), warm = right.enhanced(), darkCorner = left.enhanced();
    assert(lit.channel[1] - strong.channel[1] >= 13);
    assert(warm.channel[0] - strong.channel[0] >= 44);
    for (int c = 0; c < 3; ++c) assert(strong.channel[c] - darkCorner.channel[c] >= 15);
    assert(bright.enhanced().channel[0] == 264);
    // Shared cannon-room orange keeps the same RGB proportions for both
    // actors while retaining their live brightness and walking transitions.
    HdActorLighting::Tint wally;
    wally.channel[2] = 180;
    auto guyWarm = shaded.enhanced(true), wallyWarm = wally.enhanced(true);
    const int orange[] = {255, 233, 198};
    for (auto tint : {guyWarm, wallyWarm}) {
        assert(tint.channel[0] > tint.channel[1] && tint.channel[1] > tint.channel[2]);
        for (int c = 1; c < 3; ++c) {
            int error = tint.channel[c] * 255 - tint.channel[0] * orange[c];
            assert(error >= -127 && error <= 127);
        }
        assert((tint.apply(0x80ffffffu) >> 24) == 0x80);
    }
    assert(grate.enhanced(true).channel[0] - guyWarm.channel[0] >= 8);
    assert(guyWarm.channel[0] - left.enhanced(true).channel[0] >= 20);
    assert(dark.enhanced(true).apply(0x80ffffffu) == 0x80000000u);
    // Enhancement must preserve black, neutral white, and smooth fade ramps.
    int previous = -1;
    for (int gain = 0; gain <= 255; ++gain) {
        HdActorLighting::Tint fade;
        fade.channel[0] = fade.channel[1] = fade.channel[2] = gain;
        auto eased = fade.enhanced();
        assert(eased.channel[0] >= previous && eased.channel[0] - previous <= 2);
        assert(eased.channel[0] == eased.channel[1] && eased.channel[1] == eased.channel[2]);
        if (gain == 0 || gain == 255) assert(eased.channel[0] == gain);
        previous = eased.channel[0];
    }

    // Wally animates without moving. A different pose (or an overlapping actor)
    // must not change the weights and switch which native palette colors win.
    unsigned char mapping[256] = {};
    mapping[0] = 235; mapping[1] = 236;
    usage[235] = 100;
    HdActorLighting::StableSamples samples;
    auto first = samples.update(9, 25, mapping, usage);
    assert(first[235] == 100 && first[236] == 0);
    usage[235] = 0; usage[236] = 500;
    auto animated = samples.update(9, 25, mapping, usage);
    assert(animated[235] == 100 && animated[236] == 0);
    // Real lighting changes still affect a stationary pose immediately.
    std::memcpy(current, base, sizeof(base));
    auto restored = HdActorLighting::fromPalette(base, current, animated).enhanced();
    assert(restored.apply(0x80ffffffu) == 0x80ffffffu);
    // Room/costume/remapping changes and restored saves discard old samples.
    assert(samples.update(10, 25, mapping, usage)[236] == 500);
    usage[236] = 50;
    assert(samples.update(10, 26, mapping, usage)[236] == 50);
    mapping[1] = 237; usage[236] = 60;
    assert(samples.update(10, 26, mapping, usage)[236] == 60);
    samples.reset(); usage[236] = 70;
    assert(samples.update(10, 26, mapping, usage)[236] == 70);
    samples.reset(); std::memset(usage, 0, sizeof(usage));
    samples.update(9, 25, mapping, usage);
    assert(!samples.ready);
    usage[236] = 100;
    assert(samples.update(9, 25, mapping, usage)[236] == 100 && samples.ready);
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-g',
                            '-I', str(ROOT / 'tools/engine'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
