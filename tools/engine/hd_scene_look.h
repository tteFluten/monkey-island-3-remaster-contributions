#ifndef SCUMM_HD_SCENE_LOOK_H
#define SCUMM_HD_SCENE_LOOK_H
#include "hd_color_grade.h"
#include "hd_depth_of_field.h"

// A room overrides individual controls. Explicit neutral/Off values are real
// overrides, not an absence of configuration.
namespace HdSceneLook {
enum Control { kFocus = HdColorGrade::kControls, kBlur, kEdge, kIntensity, kDepth, kControls };
inline const HdColorGrade::Range &range(int control) {
    if (control < HdColorGrade::kControls) return HdColorGrade::range(control);
    static const HdColorGrade::Range focus[] = {
        {"Depth of field", "depthOfField", 0, 2, 0, 1},
        {"Blur radius", "blurTenths", 0, 120, 0, 5},
        {"Edge softness", "edgeSoftness", 0, 12, 2, 1},
        {"Blur strength", "blurIntensity", 0, 100, 100, 10},
        {"Scene depth", "sceneDepth", 1, 7, 1, 1}};
    return focus[control - HdColorGrade::kControls];
}
inline int clamp(int control, int value) {
    const auto &r = range(control);
    value = HdDepthOfField::clampInt(value, r.low, r.high);
    return control == kBlur && value > 0 && value < 5 ? 5 : value;
}
struct Layer {
    int value[kControls];
    unsigned int mask = 0;
    Layer() { for (int c = 0; c < kControls; ++c) value[c] = range(c).neutral; }
    bool has(int c) const { return (mask & (1u << c)) != 0; }
    void set(int c, int v) { value[c] = clamp(c, v); mask |= 1u << c; }
    void inherit(int c) { mask &= ~(1u << c); }
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
    void reset(int room, int c) {
        if (roomValid(room)) rooms[room].inherit(c);
        else global.set(c, range(c).neutral);
    }
};
}
#endif
