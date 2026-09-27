#ifndef COMMON_HD_FILM_TEXT_H
#define COMMON_HD_FILM_TEXT_H

#include "graphics/surface.h"
#include "common/util.h"

// Actual rendered glyph coverage, including antialiasing and black outlines.
// The engine writes this alongside text; the final GPU pass only uploads it.
namespace HdFilmText {
struct State {
    Graphics::Surface mask;
    const byte *target = nullptr;
    int pitch = 0;
    uint generation = 0;
    bool any = false;
};
inline State &state() { static State value; return value; }
inline void clear() {
    auto &s = state();
    s.target = nullptr; s.pitch = 0; s.any = false; ++s.generation;
}
inline void begin(int width, int height) {
    clear();
    auto &s = state();
    if (width <= 0 || height <= 0) return;
    if (s.mask.w != width || s.mask.h != height) {
        s.mask.free();
        s.mask.create(width, height, Graphics::PixelFormat::createFormatCLUT8());
    }
    memset(s.mask.getPixels(), 0, s.mask.pitch * s.mask.h);
}
inline void target(const Graphics::Surface &surface) {
    auto &s = state();
    s.target = (const byte *)surface.getPixels(); s.pitch = surface.pitch;
}
inline void begin(const Graphics::Surface &surface) {
    begin(surface.w, surface.h); target(surface);
}
inline void shiftX(const Graphics::Surface &surface, int offset) {
    auto &s = state();
    if (!s.any || surface.getPixels() != s.target || offset <= 0 || offset >= s.mask.w) return;
    for (int y = 0; y < s.mask.h; ++y) {
        byte *row = (byte *)s.mask.getBasePtr(0, y);
        memmove(row + offset, row, s.mask.w - offset);
        memset(row, 0, offset);
    }
}
inline void pixel(const Graphics::Surface &surface, int x, int y, byte alpha) {
    auto &s = state();
    if (!alpha || !s.target || !s.pitch || surface.pitch != s.pitch ||
        surface.format.bytesPerPixel != 4 || x < 0 || y < 0 || x >= surface.w || y >= surface.h) return;
    // A clipped cinematic glyph uses a sub-surface with the parent's pitch.
    const uintptr address = (uintptr)surface.getBasePtr(x, y), base = (uintptr)s.target;
    if (address < base || address - base >= (uintptr)s.pitch * s.mask.h) return;
    const uintptr offset = address - base;
    const int mx = (offset % s.pitch) / 4, my = offset / s.pitch;
    if (mx >= s.mask.w) return;
    *(byte *)s.mask.getBasePtr(mx, my) = 255;
    s.any = true;
}
}
#endif
