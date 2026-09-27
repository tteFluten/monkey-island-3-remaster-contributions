#ifndef SCUMM_HD_INVENTORY_H
#define SCUMM_HD_INVENTORY_H

namespace HdInventory {
inline bool isObject(int number) { return number >= 105 && number <= 274; }
inline int imageIndex(int image) { return image > 0 ? image - 1 : -1; }
inline int centerOffset(int viewportWidth) { return viewportWidth > 640 ? (viewportWidth - 640) / 2 : 0; }

// UI pixels are premultiplied; the scene behind them is opaque.
inline unsigned int overScene(unsigned int ui, unsigned int scene) {
    const unsigned int inverse = 255 - (ui >> 24);
    unsigned int result = 0xff000000;
    for (int shift = 0; shift < 24; shift += 8)
        result |= (((ui >> shift) & 255) + (((scene >> shift) & 255) * inverse + 127) / 255) << shift;
    return result;
}

// RGBA surfaces in the HD compositor use the high byte for alpha. Blend edges
// instead of replacing them with a second, thresholded outline.
inline unsigned int over(unsigned int source, unsigned int dest) {
    unsigned int a = source >> 24;
    if (!a) return dest;
    if (a == 255) return source;
    // The GPU UI layer is transparent; retain premultiplied coverage there.
    unsigned int result = (a + (((dest >> 24) * (255 - a) + 127) / 255)) << 24;
    for (int shift = 0; shift < 24; shift += 8)
        result |= ((((source >> shift) & 255) * a +
                    ((dest >> shift) & 255) * (255 - a) + 127) / 255) << shift;
    return result;
}

// Destination coordinates remain the native game's coordinates scaled once.
// Clip before obtaining pointers so partly offscreen icons are safe too.
template<class Surface>
void blit(Surface &dest, const Surface &source, int x, int y, int width, int height,
          const unsigned char *palette = nullptr) {
    if (width <= 0 || height <= 0 || source.w <= 0 || source.h <= 0) return;
    int left = x < 0 ? 0 : x, top = y < 0 ? 0 : y;
    int right = x + width < dest.w ? x + width : dest.w;
    int bottom = y + height < dest.h ? y + height : dest.h;
    for (int dy = top; dy < bottom; ++dy) {
        unsigned int *out = (unsigned int *)dest.getBasePtr(0, dy);
        int sy = (dy - y) * source.h / height;
        for (int dx = left; dx < right; ++dx) {
            int sx = (dx - x) * source.w / width;
            unsigned int pixel;
            if (palette) {
                unsigned char index = *(const unsigned char *)source.getBasePtr(sx, sy);
                if (index == 255) continue; // Native BOMP transparency.
                pixel = 0xff000000 | palette[index * 3] |
                    (palette[index * 3 + 1] << 8) | (palette[index * 3 + 2] << 16);
            } else {
                pixel = *(const unsigned int *)source.getBasePtr(sx, sy);
            }
            out[dx] = over(pixel, out[dx]);
        }
    }
}
}
#endif
