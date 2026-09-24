#ifndef SCUMM_HD_COLOR_GRADE_H
#define SCUMM_HD_COLOR_GRADE_H
#include <cmath>

// Per-room color correction of the composed scene (painting, objects and
// characters; dialogue, verbs and cursor are drawn afterwards). Draw-time
// only: the stored artwork and the original palettes are never altered.
namespace HdColorGrade {
enum Control { kBrightness, kContrast, kSaturation, kGamma, kWarmth, kTint,
    kVignetteOn, kVignetteAmount, kVignetteRadius, kVignetteSoftness, kControls };

struct Range {
    const char *name, *key;
    int low, high, neutral, step;
};
// Gamma is stored x100 (1.00 = 100). Others are signed percentages.
inline const Range &range(int control) {
    static const Range ranges[kControls] = {
        {"Brightness", "brightness", -50, 50, 0, 2}, {"Contrast", "contrast", -50, 50, 0, 2},
        {"Saturation", "saturation", -100, 100, 0, 5}, {"Gamma", "gamma", 50, 200, 100, 5},
        {"Warmth", "warmth", -50, 50, 0, 2}, {"Tint", "tint", -50, 50, 0, 2},
        {"Vignette", "vignetteEnabled", 0, 1, 0, 1},
        {"Strength", "vignetteAmount", 0, 100, 40, 5},
        {"Radius", "vignetteRadius", 10, 100, 60, 5},
        {"Softness", "vignetteSoftness", 1, 100, 50, 5}};
    return ranges[control < 0 ? 0 : control >= kControls ? kControls - 1 : control];
}

struct Grade {
    int value[kControls] = {0, 0, 0, 100, 0, 0, 0, 40, 60, 50};
};

inline int clampControl(int control, int v) {
    const Range &r = range(control);
    return v < r.low ? r.low : v > r.high ? r.high : v;
}
inline bool identity(const Grade &g) {
    for (int c = 0; c < kControls; ++c)
        if (g.value[c] != range(c).neutral) return false;
    return true;
}
inline bool colorIdentity(const Grade &g) {
    for (int c = 0; c < kVignetteOn; ++c)
        if (g.value[c] != range(c).neutral) return false;
    return true;
}
inline bool vignetteActive(const Grade &g) {
    return g.value[kVignetteOn] && g.value[kVignetteAmount] > 0;
}
// Elliptical, viewport-relative darkening. Radius is the untouched center;
// softness is the smooth transition to the maximum strength. No artwork edits.
inline unsigned char vignetteGain(const Grade &g, double x, double y, double width, double height) {
    if (!vignetteActive(g) || width <= 0 || height <= 0) return 255;
    const double nx = (2 * (x + 0.5) - width) / width;
    const double ny = (2 * (y + 0.5) - height) / height;
    const double inner = g.value[kVignetteRadius] / 100.0;
    const double outer = inner + g.value[kVignetteSoftness] / 100.0;
    double t = (nx * nx + ny * ny - inner * inner) / (outer * outer - inner * inner);
    t = t < 0 ? 0 : t > 1 ? 1 : t;
    t = t * t * (3 - 2 * t);
    return (unsigned char)std::lround(255 * (1 - g.value[kVignetteAmount] / 100.0 * t));
}
inline unsigned int vignettePixel(unsigned int rgba, unsigned char gain) {
    const unsigned int r = ((rgba & 255) * gain + 127) / 255;
    const unsigned int g = (((rgba >> 8) & 255) * gain + 127) / 255;
    const unsigned int b = (((rgba >> 16) & 255) * gain + 127) / 255;
    return (rgba & 0xff000000u) | r | (g << 8) | (b << 16);
}
inline Grade adjust(Grade g, int control, int steps) {
    if (control >= 0 && control < kControls)
        g.value[control] = clampControl(control, g.value[control] + steps * range(control).step);
    return g;
}

// Per-channel curves (white balance, gamma, contrast, brightness) plus the
// saturation factor in 1/256 units, precomputed once per grade change.
struct Lut {
    unsigned char channel[3][256];
    int saturation = 256;
};

inline void build(const Grade &g, Lut &lut) {
    const double warmth = g.value[kWarmth] / 250.0, tint = g.value[kTint] / 250.0;
    // Positive warmth: redder/less blue. Positive tint: magenta (less green).
    const double gain[3] = {1 + warmth + tint / 2, 1 - tint, 1 - warmth + tint / 2};
    const double gamma = g.value[kGamma] / 100.0;
    const double contrast = 1 + g.value[kContrast] / 100.0;
    const double brightness = g.value[kBrightness] / 200.0;
    for (int c = 0; c < 3; ++c)
        for (int v = 0; v < 256; ++v) {
            double x = v / 255.0 * gain[c];
            x = x < 0 ? 0 : x > 1 ? 1 : x;
            x = std::pow(x, 1 / gamma);
            x = (x - 0.5) * contrast + 0.5 + brightness;
            const int out = (int)std::lround(x * 255);
            lut.channel[c][v] = (unsigned char)(out < 0 ? 0 : out > 255 ? 255 : out);
        }
    lut.saturation = 256 + g.value[kSaturation] * 256 / 100;
}

// RGBA as in the HD composite: R in the low byte. Alpha is preserved.
inline unsigned int apply(unsigned int rgba, const Lut &lut) {
    int r = lut.channel[0][rgba & 255], g = lut.channel[1][(rgba >> 8) & 255], b = lut.channel[2][(rgba >> 16) & 255];
    if (lut.saturation != 256) {
        const int l = (77 * r + 150 * g + 29 * b) >> 8;
        r = l + (((r - l) * lut.saturation) >> 8);
        g = l + (((g - l) * lut.saturation) >> 8);
        b = l + (((b - l) * lut.saturation) >> 8);
        r = r < 0 ? 0 : r > 255 ? 255 : r;
        g = g < 0 ? 0 : g > 255 ? 255 : g;
        b = b < 0 ? 0 : b > 255 ? 255 : b;
    }
    return (rgba & 0xff000000u) | (unsigned int)r | ((unsigned int)g << 8) | ((unsigned int)b << 16);
}
}
#endif
