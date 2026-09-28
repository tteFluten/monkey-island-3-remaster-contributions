#ifndef COMMON_HD_WATER_H
#define COMMON_HD_WATER_H
#include "common/hd_water_regions.h"
#include "hd_scene_masks.h"

namespace HdWater {
// Reviewed ambient/reflection costumes and mixed water/boat poses are generated
// from water_regions.json. Story poses, impacts and waterfalls are excluded.
inline bool room(int room) { return HdMasks::waterOverride(room) || room == 10 || room == 11 || room == 14 || room == 15 || mappedRoom(room); }
inline bool fullSurface(int room) { return room == 10 || room == 11; }

// The cannon and waterline paintings use this material classifier: their wood is
// olive/brown and their water is dark blue/teal. Work from the
// selected ungraded painting, never from the scene containing actors or UI.
inline bool waterlineColor(unsigned r, unsigned g, unsigned b) {
    return g > 6 && b > 6 && g * 4 > r * 5 && b * 4 > r * 5 && b * 10 > g * 7;
}

// Unwind only visible pixels belonging to this actor, front to back. The boat
// animation in room 37 combines wood with teal ripples; retain its physical boat
// while removing the water. Use the native palette, before room color grading.
inline void removeOverlay(unsigned char *display, const unsigned char *under,
                          const unsigned char *after, unsigned count,
                          const unsigned char *palette, bool mixed) {
    for (unsigned i = 0; i < count; ++i) {
        const unsigned p = after[i] * 3;
        if (display[i] == after[i] && under[i] != after[i] &&
            (!mixed || waterlineColor(palette[p], palette[p + 1], palette[p + 2])))
            display[i] = under[i];
    }
}

// Distance from dry paint, used to stop refraction crossing a shoreline or
// foreground boundary. Callers supply reusable native-resolution buffers.
inline unsigned surfaceDepth(const unsigned char *water, int width, int height,
                             unsigned short *edge, unsigned char *depth, int guard) {
    for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
        const int i = y * width + x;
        const unsigned near = x && y ? (edge[i - 1] < edge[i - width] ? edge[i - 1] : edge[i - width]) : 0;
        edge[i] = water[i] != 2 || !x || !y || x == width - 1 || y == height - 1 ? 0 :
            (near < 254 ? near + 1 : 255);
        depth[i] = 0;
    }
    unsigned covered = 0;
    for (int y = height - 2; y >= 1; --y) for (int x = width - 2; x >= 1; --x) {
        const int i = y * width + x;
        const unsigned near = (edge[i + 1] < edge[i + width] ? edge[i + 1] : edge[i + width]) + 1;
        if (near < edge[i]) edge[i] = near;
        if (edge[i] > guard) { depth[i] = edge[i] - guard; ++covered; }
    }
    return covered;
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
