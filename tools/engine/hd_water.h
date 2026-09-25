#ifndef COMMON_HD_WATER_H
#define COMMON_HD_WATER_H

namespace HdWater {
// Ambient water only. In particular, waterline costumes 49/57 include Murray
// and 54 contains scripted splashes; replacing those would erase story poses.
inline bool ambient(int room, int costume) {
    return (room == 11 && (costume == 51 || costume == 59)) ||
           (room == 14 && (costume == 73 || costume == 74)) ||
           (room == 15 && (costume == 80 || costume == 83));
}
inline bool room(int room) { return room == 11 || room == 14 || room == 15; }

// Only the waterline painting uses this material classifier: its hull is
// olive/brown and its bottom-connected water is dark blue/teal. Work from the
// selected ungraded painting, never from the scene containing actors or UI.
inline bool waterlineColor(unsigned r, unsigned g, unsigned b) {
    return g > 6 && b > 6 && g * 4 > r * 5 && b * 4 > r * 5 && b * 10 > g * 7;
}

// Native actor captures already contain transparency, clipping and z-plane
// occlusion. Never turn a sprite's rectangular bounds into a water surface.
inline void coverage(unsigned char *mask, const unsigned char *current,
                     const unsigned char *under, const unsigned char *after, unsigned count) {
    for (unsigned i = 0; i < count; ++i)
        if (under[i] != after[i] && current[i] == after[i]) mask[i] = 255;
}
}
#endif
