#ifndef SCUMM_HD_ACTOR_SHADOW_H
#define SCUMM_HD_ACTOR_SHADOW_H

namespace HdActorShadow {
struct Footprint {
    bool valid = false;
    float x = 0, y = 0, radiusX = 0, radiusY = 0;
    int opacity = 0;
};

inline int groundElevation(int actorX, int actorY, int elevation) {
    // Scene-aligned costumes use (0, y) with elevation=y merely to put their
    // drawing origin at (0, 0). That is layering metadata, not a physical jump.
    return actorX == 0 && actorY == elevation ? 0 : elevation;
}

// Derive feet from native painted pixels, including split-limb and fallback
// poses. Some scripted actors (Wally) have an origin far outside their sprite.
inline Footprint footprint(const unsigned char *under, const unsigned char *after,
                           int width, int height, int actorX, int floorY, int elevation) {
    Footprint result;
    int left = width, right = -1, top = height, bottom = -1;
    for (int y = 0; y < height; ++y)
        for (int x = 0; x < width; ++x) {
            const int i = y * width + x;
            if (under[i] == after[i] || after[i] < 16 || after[i] == 255) continue;
            if (x < left) left = x;
            if (x > right) right = x;
            if (y < top) top = y;
            if (y > bottom) bottom = y;
        }
    const int bodyHeight = bottom - top + 1;
    // No floor shadow for props, portraits clipped at the viewport edge, or
    // actors whose feet are hidden well above their ground position.
    if (bodyHeight < 32 || right - left + 1 > bodyHeight || bottom >= height - 2 ||
        floorY - elevation - bottom > bodyHeight / 4 || elevation < 0 || elevation > 80)
        return result;
    int footLeft = width, footRight = -1;
    const int band = bodyHeight / 12 + 1;
    for (int y = bottom - band; y <= bottom; ++y)
        for (int x = left; x <= right; ++x) {
            const int i = y * width + x;
            if (under[i] == after[i] || after[i] < 16 || after[i] == 255) continue;
            if (x < footLeft) footLeft = x;
            if (x > footRight) footRight = x;
        }
    float center = (footLeft + footRight) * 0.5f;
    // A real walking origin gives a steady center across alternating footsteps.
    if (actorX >= footLeft && actorX <= footRight) center = (center + actorX) * 0.5f;
    float radius = bodyHeight * 0.14f;
    if (radius < 10) radius = 10;
    if (radius > 38) radius = 38;
    result.valid = true;
    result.x = center;
    // Tuck the oval under the feet and give it a slightly wider footprint.
    result.y = bottom + 1 + elevation - 3;
    result.radiusX = (radius + elevation * 0.08f) * 1.20f;
    result.radiusY = result.radiusX * 0.24f;
    result.opacity = 38 * (80 - elevation) / 80;
    return result;
}

// Uniform black oval at 15% opacity when grounded, with a hard boundary.
// Nothing extends into the bounding box corners. Preserve floor hue and alpha.
inline unsigned int shade(unsigned int rgba, float dx, float dy, int opacity) {
    if (dx * dx + dy * dy >= 1.0f) return rgba;
    const int alpha = opacity;
    unsigned int result = rgba & 0xff000000u;
    for (int c = 0; c < 3; ++c) {
        unsigned int value = (rgba >> (c * 8)) & 255;
        result |= ((value * (255 - alpha) + 127) / 255) << (c * 8);
    }
    return result;
}
}
#endif
