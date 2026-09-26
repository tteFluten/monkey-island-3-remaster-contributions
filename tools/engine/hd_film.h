#ifndef COMMON_HD_FILM_H
#define COMMON_HD_FILM_H

#include "common/config-manager.h"
#include "common/system.h"
#include "common/ustr.h"
#include "common/util.h"

namespace HdFilm {
enum Control { kEnabled, kStrength, kGrain, kDust, kScratches, kFlicker, kWobble, kChromatic, kControls };
struct Range { const char *name, *key; int low, high, neutral, step; };
inline const Range &range(int control) {
    static const Range ranges[] = {
        {"Film effect", "hd_film_enabled", 0, 1, 0, 1},
        {"Overall strength", "hd_film_strength", 0, 100, 20, 5},
        {"Grain", "hd_film_grain", 0, 200, 100, 10},
        {"Dust", "hd_film_dust", 0, 200, 100, 10},
        {"Scratches", "hd_film_scratches", 0, 200, 100, 10},
        {"Flicker", "hd_film_flicker", 0, 200, 100, 10},
        {"Frame wobble", "hd_film_wobble", 0, 200, 100, 10},
        {"Chromatic aberration", "hd_film_chromatic", 0, 200, 100, 10}};
    return ranges[control];
}
struct State {
    uint revision = 0;
    bool capture = false, bypass = false;
    int testTick = -1; // Only set through opt-in engine-local test input.
};
inline State &state() { static State value; return value; }
inline int get(int control) {
    const auto &r = range(control);
    if (!ConfMan.hasKey(r.key, Common::ConfigManager::kApplicationDomain)) return r.neutral;
    if (control == kEnabled) return ConfMan.getBool(r.key, Common::ConfigManager::kApplicationDomain) ? 1 : 0;
    return CLIP(ConfMan.getInt(r.key, Common::ConfigManager::kApplicationDomain), r.low, r.high);
}
inline bool enabled() {
    return ConfMan.hasKey("playtest_session") && get(kEnabled) && !state().bypass;
}
inline int strength() { return get(kStrength); }
inline void set(int control, int value, bool save = true) {
    const auto &r = range(control);
    value = CLIP(value, r.low, r.high);
    if (control == kEnabled) ConfMan.setBool(r.key, value != 0, Common::ConfigManager::kApplicationDomain);
    else ConfMan.setInt(r.key, value, Common::ConfigManager::kApplicationDomain);
    state().bypass = false;
    ++state().revision;
    if (save) ConfMan.flushToDisk();
}
inline void reset() {
    for (int c = 0; c < kControls; ++c) set(c, range(c).neutral, false);
    ConfMan.flushToDisk();
}
inline void toggle() {
    const bool on = !get(kEnabled);
    set(kEnabled, on ? 1 : 0);
    g_system->displayMessageOnOSD(Common::U32String(on ? "Film: On" : "Film: Off"));
}
}
#endif
