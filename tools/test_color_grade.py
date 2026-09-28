"""Per-room color grades: neutral identity, ranges, curves and saturation."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class ColorGradeTests(unittest.TestCase):
    def test_grade_curves_and_controls(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'grade.cpp'
            binary = Path(directory) / 'grade'
            source.write_text(r'''
#include "hd_color_grade.h"
#include "hd_scene_look.h"
#include <cassert>
#include <cstdlib>
#include <initializer_list>
using namespace HdColorGrade;
static int ch(unsigned int p, int c) { return (p >> (c * 8)) & 255; }
static unsigned int rgb(int r, int g, int b, int a = 255) {
    return (unsigned)r | ((unsigned)g << 8) | ((unsigned)b << 16) | ((unsigned)a << 24);
}
int main() {
    // The difficulty screen has independent look overrides and inherits global
    // values only where no room override exists. The options book is excluded.
    HdSceneLook::Settings settings;
    assert(HdSceneLook::Settings::roomValid(87));
    assert(!HdSceneLook::Settings::roomValid(92));
    settings.set(0, kContrast, 6);
    settings.set(87, kVignetteOn, 1);
    settings.set(87, kVignetteAmount, 65);
    assert(settings.get(87, kContrast) == 6);
    assert(settings.get(87, kVignetteOn) == 1);

    // Extended water controls push shadow overrides past bit 31. Every bit
    // must remain independent, including when inheriting/resetting a control.
    for (int c = 0; c < HdSceneLook::kControls; ++c) {
        HdSceneLook::Layer layer;
        layer.set(c, HdSceneLook::range(c).high + 1);
        for (int other = 0; other < HdSceneLook::kControls; ++other)
            assert(layer.has(other) == (other == c));
        assert(layer.value[c] == HdSceneLook::range(c).high);
        layer.inherit(c);
        assert(layer.mask == 0);
    }
    settings.set(0, HdSceneLook::kWaterRed, 125);
    settings.set(75, HdSceneLook::kWaterRed, 0); // Explicit black channel is real.
    settings.set(75, HdSceneLook::kShadowBlue, 180);
    assert(settings.get(75, HdSceneLook::kWaterRed) == 0);
    assert(settings.get(74, HdSceneLook::kWaterRed) == 125);
    settings.reset(75, HdSceneLook::kWaterRed);
    assert(settings.get(75, HdSceneLook::kWaterRed) == 125);
    assert(settings.get(75, HdSceneLook::kShadowBlue) == 180);
    assert(HdSceneLook::clamp(HdSceneLook::kWaterScale, 0) == 25);
    assert(HdSceneLook::clamp(HdSceneLook::kWaterGloss, 0) == 25);
    assert(HdSceneLook::clamp(HdSceneLook::kWaterLightDirection, -999) == -180);
    assert(settings.get(9, kVignetteOn) == 0);
    assert(settings.get(0, kVignetteAmount) == 40);
    settings.reset(87, kVignetteAmount);
    assert(settings.get(87, kVignetteAmount) == 40);
    assert(settings.get(87, kVignetteOn) == 1);

    // Scene position overrides pin both effective coordinates; reverting just
    // position keeps other shadow properties and every unrelated look setting.
    settings.set(0, HdSceneLook::kShadowX, -3);
    settings.set(0, HdSceneLook::kShadowY, -5);
    settings.set(29, HdSceneLook::kShadowWidth, 140);
    settings.set(29, kBrightness, 8);
    assert(!settings.shadowPositionOverridden(29));
    settings.overrideShadowPosition(29);
    settings.set(0, HdSceneLook::kShadowX, 12);
    assert(settings.get(29, HdSceneLook::kShadowX)==-3);
    assert(settings.get(14, HdSceneLook::kShadowX)==12);
    settings.set(29, HdSceneLook::kShadowY, 0);
    assert(settings.get(29, HdSceneLook::kShadowY)==0); // Explicit zero overrides.
    settings.resetShadows(29,true);
    assert(!settings.shadowPositionOverridden(29));
    assert(settings.get(29, HdSceneLook::kShadowX)==12);
    assert(settings.get(29, HdSceneLook::kShadowWidth)==140);
    assert(settings.get(29, kBrightness)==8);
    settings.set(29, HdSceneLook::kShadowX, 7);
    assert(settings.shadowPositionOverridden(29));
    assert(!settings.rooms[29].has(HdSceneLook::kShadowY));
    settings.overrideShadowPosition(29);
    assert(settings.get(29, HdSceneLook::kShadowX)==7 && settings.rooms[29].has(HdSceneLook::kShadowY));
    settings.resetShadows(29);
    assert(settings.get(29, HdSceneLook::kShadowWidth)==100);
    assert(settings.get(29, kBrightness)==8);
    settings.set(0, HdSceneLook::kShadowWidth, 135);
    settings.resetShadows(0,true);
    assert(settings.get(0, HdSceneLook::kShadowX)==0 && settings.get(0, HdSceneLook::kShadowY)==0);
    assert(settings.get(0, HdSceneLook::kShadowWidth)==135);
    settings.resetShadows(0);
    assert(settings.get(0, HdSceneLook::kShadowWidth)==100);
    assert(settings.get(0, HdSceneLook::kWaterRed)==125);

    // The neutral grade is an exact identity for every color, alpha preserved.
    Grade neutral;
    assert(identity(neutral));
    Lut lut;
    build(neutral, lut);
    for (int v = 0; v < 256; ++v)
        for (int c = 0; c < 3; ++c) assert(lut.channel[c][v] == v);
    for (unsigned int p : {0u, 0xffffffffu, 0x80123456u, rgb(200, 10, 90, 7)}) assert(apply(p, lut) == p);

    // Steps and clamping follow each control's range; any change is non-neutral.
    Grade g = adjust(neutral, kBrightness, 3);
    assert(g.value[kBrightness] == 6 && !identity(g));
    g = adjust(g, kGamma, -100);
    assert(g.value[kGamma] == 50);
    g = adjust(g, kSaturation, 100);
    assert(g.value[kSaturation] == 100);
    assert(adjust(neutral, 99, 1).value[kTint] == 0 && identity(adjust(neutral, -1, 1)));
    assert(clampControl(kContrast, -80) == -50 && clampControl(kGamma, 999) == 200);
    assert(range(kGamma).neutral == 100 && range(kTint).key[0] == 't');

    // Brightness lifts, contrast spreads around mid gray, gamma lifts midtones.
    Grade bright; bright.value[kBrightness] = 20; build(bright, lut);
    assert(ch(apply(rgb(100, 100, 100), lut), 0) == 126 && lut.channel[0][255] == 255);
    Grade contrast; contrast.value[kContrast] = 50; build(contrast, lut);
    assert(lut.channel[1][64] < 64 && lut.channel[1][192] > 192 && std::abs(lut.channel[1][128] - 128) <= 1);
    Grade gamma; gamma.value[kGamma] = 150; build(gamma, lut);
    assert(lut.channel[2][64] > 64 && lut.channel[2][0] == 0 && lut.channel[2][255] == 255);
    for (int v = 1; v < 256; ++v) assert(lut.channel[2][v] >= lut.channel[2][v - 1]);

    // Warmth trades blue for red; tint trades green for magenta.
    Grade warm; warm.value[kWarmth] = 50; build(warm, lut);
    unsigned int p = apply(rgb(128, 128, 128), lut);
    assert(ch(p, 0) > 128 && ch(p, 1) == 128 && ch(p, 2) < 128);
    Grade tint; tint.value[kTint] = 50; build(tint, lut);
    p = apply(rgb(128, 128, 128), lut);
    assert(ch(p, 1) < 128 && ch(p, 0) > 128 && ch(p, 2) > 128);

    // Saturation: -100 is gray, grays never shift, +100 pushes channels apart.
    Grade gray; gray.value[kSaturation] = -100; build(gray, lut);
    p = apply(rgb(200, 40, 90, 3), lut);
    assert(ch(p, 0) == ch(p, 1) && ch(p, 1) == ch(p, 2) && (p >> 24) == 3);
    Grade vivid; vivid.value[kSaturation] = 100; build(vivid, lut);
    assert(apply(rgb(90, 90, 90), lut) == rgb(90, 90, 90));
    p = apply(rgb(160, 100, 100), lut);
    assert(ch(p, 0) > 160 && ch(p, 1) < 100);
    p = apply(rgb(255, 0, 0), lut);
    assert(ch(p, 0) == 255 && ch(p, 1) == 0 && ch(p, 2) == 0);

    // Old six-control room records inherit an OFF vignette with useful defaults.
    Grade vig;
    assert(!vignetteActive(vig) && colorIdentity(vig));
    assert(vignetteGain(vig, 0, 0, 640, 480) == 255);
    vig = adjust(vig, kVignetteOn, 1);
    assert(vignetteActive(vig) && colorIdentity(vig) && !identity(vig));
    assert(vignetteGain(vig, 319.5, 239.5, 640, 480) == 255);
    assert(vignetteGain(vig, 0, 0, 640, 480) < 255);
    // Elliptical symmetry, smooth/monotonic falloff, scale-independent geometry.
    for (int y = 0; y < 480; y += 7) for (int x = 0; x < 640; x += 7) {
        const auto a = vignetteGain(vig, x, y, 640, 480);
        assert(a == vignetteGain(vig, 639 - x, 479 - y, 640, 480));
        assert(a == vignetteGain(vig, (x + .5) * 4 - .5, (y + .5) * 4 - .5, 2560, 1920));
    }
    int last = 255;
    for (int x = 320; x < 640; ++x) {
        int gain = vignetteGain(vig, x, 239.5, 640, 480);
        assert(gain <= last); last = gain;
    }
    Grade soft = vig; soft.value[kVignetteSoftness] = 100;
    assert(vignetteGain(soft, 600, 240, 640, 480) >= vignetteGain(vig, 600, 240, 640, 480));
    Grade radius = vig; radius.value[kVignetteRadius] = 100;
    assert(vignetteGain(radius, 600, 240, 640, 480) >= vignetteGain(vig, 600, 240, 640, 480));
    assert(vignettePixel(rgb(100, 150, 200, 7), 255) == rgb(100, 150, 200, 7));
    assert(vignettePixel(rgb(100, 150, 200, 7), 0) == rgb(0, 0, 0, 7));
    vig.value[kVignetteOn] = 0; vig.value[kVignetteAmount] = 80;
    assert(!vignetteActive(vig) && !identity(vig)); // Remember strength while off.
    vig.value[kVignetteOn] = 1; vig.value[kVignetteAmount] = 0;
    assert(!vignetteActive(vig));
    assert(clampControl(kVignetteOn, 5) == 1 && clampControl(kVignetteSoftness, 0) == 1);
    // A 4:3 center and 16:9 side texture use the same normalized full-frame mask.
    vig = Grade(); vig.value[kVignetteOn] = 1;
    for (int x = 0; x < 1920; x += 11) {
        const int full = vignetteGain(vig, x + 320, 100, 2560, 1440);
        const int center = vignetteGain(vig, (x + 320 + .5) * 4 / 3 - .5,
            (100 + .5) * 4 / 3 - .5, 1920 * 16.0 / 9, 1920);
        assert(full == center);
    }
}
''')
            include = Path(__file__).resolve().parent / 'engine'
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(include), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
