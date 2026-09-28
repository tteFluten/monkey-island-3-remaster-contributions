#ifndef SCUMM_HD_SCENE_LOOK_H
#define SCUMM_HD_SCENE_LOOK_H
#include "hd_color_grade.h"
#include "hd_depth_of_field.h"

// A room overrides individual controls. Explicit neutral/Off values are real
// overrides, not an absence of configuration.
namespace HdSceneLook {
enum Control { kFocus = HdColorGrade::kControls, kBlur, kEdge, kIntensity, kDepth,
    kWaterOpacity, kWaterWaves, kWaterSpeed, kWaterDistortion, kWaterHighlights,
    kWaterRed, kWaterGreen, kWaterBlue, kWaterLight, kWaterLightDirection, kWaterGloss, kWaterScale, kWaterReflection,
    kShadowX, kShadowY, kShadowWidth, kShadowOvalness, kShadowOpacity,
    kShadowRed, kShadowGreen, kShadowBlue, kControls };
static_assert(kControls <= 64, "Scene Look overrides must fit their bit mask");
inline const HdColorGrade::Range &range(int control) {
    if (control < HdColorGrade::kControls) return HdColorGrade::range(control);
    static const HdColorGrade::Range focus[] = {
        {"Depth of field", "depthOfField", 0, 2, 0, 1},
        {"Blur radius", "blurTenths", 0, 120, 0, 5},
        {"Edge softness", "edgeSoftness", 0, 12, 2, 1},
        {"Blur strength", "blurIntensity", 0, 100, 100, 10},
        {"Scene depth", "sceneDepth", 1, 7, 1, 1},
        {"Water strength", "waterOpacity", 0, 100, 100, 5},
        {"Wave height", "waterWaves", 0, 300, 100, 10},
        {"Wave speed", "waterSpeed", 0, 300, 100, 10},
        {"Distortion", "waterDistortion", 0, 300, 100, 10},
        {"Highlights", "waterHighlights", 0, 300, 100, 10},
        {"Color red", "waterRed", 0, 200, 100, 5},
        {"Color green", "waterGreen", 0, 200, 100, 5},
        {"Color blue", "waterBlue", 0, 200, 100, 5},
        {"Light strength", "waterLight", 0, 200, 100, 10},
        {"Light direction", "waterLightDirection", -180, 180, 0, 5},
        {"Highlight sharpness", "waterGloss", 25, 200, 100, 5},
        {"Wave size", "waterScale", 25, 400, 100, 5},
        {"Reflection opacity", "waterReflection", 0, 100, 8, 1},
        {"Position X", "shadowOffsetX", -80, 80, 0, 1},
        {"Position Y", "shadowOffsetY", -80, 80, 0, 1},
        {"Width", "shadowWidth", 25, 300, 100, 5},
        {"Ovalness", "shadowOvalness", 5, 100, 24, 1},
        {"Opacity", "shadowOpacity", 0, 100, 15, 1},
        {"Color red", "shadowRed", 0, 255, 0, 1},
        {"Color green", "shadowGreen", 0, 255, 0, 1},
        {"Color blue", "shadowBlue", 0, 255, 0, 1}};
    return focus[control - HdColorGrade::kControls];
}
inline int clamp(int control, int value) {
    const auto &r = range(control);
    value = HdDepthOfField::clampInt(value, r.low, r.high);
    return control == kBlur && value > 0 && value < 5 ? 5 : value;
}
struct Layer {
    int value[kControls];
    unsigned long long mask = 0;
    Layer() { for (int c = 0; c < kControls; ++c) value[c] = range(c).neutral; }
    bool has(int c) const { return (mask & (1ULL << c)) != 0; }
    void set(int c, int v) { value[c] = clamp(c, v); mask |= 1ULL << c; }
    void inherit(int c) { mask &= ~(1ULL << c); }
};
struct Settings {
    Layer global, rooms[256];
    static bool roomValid(int room) { return room > 0 && room < 256 && room != 92; }
    int get(int room, int c) const {
        return roomValid(room) && rooms[room].has(c) ? rooms[room].value[c] : global.value[c];
    }
    HdColorGrade::Grade grade(int room) const {
        HdColorGrade::Grade g;
        for (int c = 0; c < HdColorGrade::kControls; ++c) g.value[c] = get(room, c);
        return g;
    }
    void set(int room, int c, int value) {
        (roomValid(room) ? rooms[room] : global).set(c, value);
    }
    bool shadowPositionOverridden(int room) const {
        return roomValid(room) && (rooms[room].has(kShadowX) || rooms[room].has(kShadowY));
    }
    void overrideShadowPosition(int room) {
        if (!roomValid(room)) return;
        const int x = get(room, kShadowX), y = get(room, kShadowY);
        set(room, kShadowX, x); set(room, kShadowY, y);
    }
    void resetShadows(int room, bool positionOnly = false) {
        for (int c = kShadowX; c < (positionOnly ? kShadowY + 1 : kControls); ++c) reset(room, c);
    }
    void reset(int room, int c) {
        if (roomValid(room)) rooms[room].inherit(c);
        else global.set(c, range(c).neutral);
    }
};
}
#endif
