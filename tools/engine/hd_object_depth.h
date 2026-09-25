#ifndef SCUMM_HD_OBJECT_DEPTH_H
#define SCUMM_HD_OBJECT_DEPTH_H
#include <cstddef>

namespace HdObjectDepth {
// A mask row starts at floor(cameraX / 8). Include the remaining camera bits
// when indexing it, so cached rows match native per-pixel z-buffer lookups.
inline bool masked(const unsigned char *row, int x, int cameraBitOffset) {
    return row && (row[(x + cameraBitOffset) / 8] & (0x80 >> ((x + cameraBitOffset) & 7)));
}
// Native drawing has already applied the original scene's occlusion masks.
// Only protect surviving actor pixels, not its rectangle or later UI pixels.
inline void protectActor(unsigned char *mask, const unsigned char *display,
                         const unsigned char *under, const unsigned char *after,
                         size_t count) {
    for (size_t i = 0; i < count; ++i)
        if (under[i] != after[i] && display[i] == after[i]) mask[i] = 1;
}

// Some matted scenery textures retain the enhancement input's gray background
// in soft edge RGB. Extend nearby opaque artwork into those pixels at draw time;
// preserve their coverage, and never alter the stored PNG or opaque interior.
inline unsigned int edgeColor(const unsigned int *source, int pitch, int width,
                              int height, int x, int y) {
    const unsigned int pixel = source[y * pitch + x];
    const unsigned int alpha = pixel >> 24;
    if (!alpha || alpha >= 250) return pixel;
    unsigned int rgb = pixel & 0xffffff;
    int closest = 19;
    for (int oy = -3; oy <= 3; ++oy) {
        if (y + oy < 0 || y + oy >= height) continue;
        for (int ox = -3; ox <= 3; ++ox) {
            const int distance = ox * ox + oy * oy;
            if (x + ox < 0 || x + ox >= width || distance >= closest) continue;
            const unsigned int candidate = source[(y + oy) * pitch + x + ox];
            if ((candidate >> 24) < 250) continue;
            closest = distance;
            rgb = candidate & 0xffffff;
        }
    }
    return (pixel & 0xff000000) | rgb;
}

template<int FixedScale>
inline void blitScaled(unsigned int *dest, int destPitch, int screenWidth, int screenHeight,
                 const unsigned int *source, int sourcePitch, int width, int height,
                 int left, int top, int dynamicScale, const unsigned char *actors,
                 unsigned char *hdAlphaMask, bool cleanMatteEdge = false) {
    const int scale = FixedScale ? FixedScale : dynamicScale;
    for (int y = 0; y < height; ++y) {
        const int dy = top + y;
        if (dy < 0 || dy >= screenHeight) continue;
        for (int x = 0; x < width; ++x) {
            const int dx = left + x;
            if (dx < 0 || dx >= screenWidth) continue;
            if (actors[(dy / scale) * (screenWidth / scale) + dx / scale]) continue;
            const unsigned int pixel = cleanMatteEdge
                ? edgeColor(source, sourcePitch, width, height, x, y)
                : source[y * sourcePitch + x];
            const unsigned int alpha = pixel >> 24;
            if (alpha == 255) {
                dest[dy * destPitch + dx] = pixel;
            } else if (alpha) {
                // The scene is opaque. Blend the PNG's soft cutout edge into
                // it rather than thresholding coverage or leaking PNG alpha
                // into the final framebuffer (visible as a pale dotted seam).
                const unsigned int previous = dest[dy * destPitch + dx];
                const unsigned int r = ((pixel & 255) * alpha + (previous & 255) * (255 - alpha) + 127) / 255;
                const unsigned int g = (((pixel >> 8) & 255) * alpha + ((previous >> 8) & 255) * (255 - alpha) + 127) / 255;
                const unsigned int b = (((pixel >> 16) & 255) * alpha + ((previous >> 16) & 255) * (255 - alpha) + 127) / 255;
                dest[dy * destPitch + dx] = r | (g << 8) | (b << 16) |
                    ((alpha + ((previous >> 24) * (255 - alpha) + 127) / 255) << 24);
            }
            hdAlphaMask[dy * screenWidth + dx] = 1;
        }
    }
}
inline void blit(unsigned int *dest, int destPitch, int screenWidth, int screenHeight,
                 const unsigned int *source, int sourcePitch, int width, int height,
                 int left, int top, int scale, const unsigned char *actors,
                 unsigned char *hdAlphaMask, bool cleanMatteEdge = false) {
    if (scale == 4) blitScaled<4>(dest, destPitch, screenWidth, screenHeight, source, sourcePitch,
        width, height, left, top, scale, actors, hdAlphaMask, cleanMatteEdge);
    else blitScaled<0>(dest, destPitch, screenWidth, screenHeight, source, sourcePitch,
        width, height, left, top, scale, actors, hdAlphaMask, cleanMatteEdge);
}
}
#endif
