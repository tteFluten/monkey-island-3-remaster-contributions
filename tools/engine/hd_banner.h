#ifndef SCUMM_HD_BANNER_H
#define SCUMM_HD_BANNER_H
// Engine banners (quit, pause, restart, sliders, messages) draw rectangles into
// the native 8-bit screen while the game is paused. Everything else on screen
// comes from HD records that the paused engine never re-emits, so the last
// complete HD frame is retained and only the banner area is replaced.

namespace HdBanner {

typedef unsigned char U8;
typedef unsigned int U32;

struct Rect {
    int left = 0, top = 0, right = 0, bottom = 0; // right/bottom exclusive
    bool empty() const { return right <= left || bottom <= top; }
};

// Bounding box of every native pixel the banner changed. Filling the whole box
// (not just differing pixels) keeps banner fill colors that happen to match
// the underlying native palette index from exposing the HD frame through it.
inline Rect changed(const U8 *native, int nativePitch, const U8 *base, int basePitch,
                    int width, int height) {
    Rect r;
    r.left = width; r.top = height;
    for (int y = 0; y < height; ++y) {
        const U8 *n = native + y * nativePitch, *b = base + y * basePitch;
        int first = -1, last = -1;
        for (int x = 0; x < width; ++x)
            if (n[x] != b[x]) { if (first < 0) first = x; last = x; }
        if (first < 0) continue;
        if (first < r.left) r.left = first;
        if (last + 1 > r.right) r.right = last + 1;
        if (y < r.top) r.top = y;
        r.bottom = y + 1;
    }
    if (r.empty()) r = Rect();
    return r;
}

// Paints the native box into the HD frame (R in the low byte, opaque alpha, so
// the same pixels serve the CPU composite and the GPU UI layer).
inline void paint(U32 *frame, int framePitch, int frameWidth, int frameHeight,
                  const U8 *native, int nativePitch, const Rect &r, int scale,
                  const U8 *palette) {
    for (int y = r.top; y < r.bottom; ++y) {
        const U8 *n = native + y * nativePitch;
        for (int dy = 0; dy < scale; ++dy) {
            const int hy = y * scale + dy;
            if (hy < 0 || hy >= frameHeight) continue;
            U32 *row = frame + hy * framePitch;
            for (int x = r.left; x < r.right; ++x) {
                const U8 *c = palette + n[x] * 3;
                const U32 color = (U32)c[0] | (U32)c[1] << 8 | (U32)c[2] << 16 | 0xff000000u;
                for (int dx = 0; dx < scale; ++dx) {
                    const int hx = x * scale + dx;
                    if (hx >= 0 && hx < frameWidth) row[hx] = color;
                }
            }
        }
    }
}

// Box or button behind a line of banner text: the rectangle of the fill
// colour under the line. HD glyphs replace the native ones, so native text is
// never drawn and the pixels under the line are its container; bevels and
// buttons (other colours) bound it. Coordinates are native, right/bottom
// exclusive; `row` is the line's centre row, [left, right) its columns.
inline bool container(const U8 *native, int pitch, int width, int height,
                      int left, int right, int row, Rect &out) {
    if (row < 0 || row >= height) return false;
    if (left < 0) left = 0;
    if (right > width) right = width;
    if (right <= left) return false;
    const U8 *line = native + row * pitch;
    int counts[256] = {0}, fill = line[left];
    for (int x = left; x < right; ++x)
        if (++counts[line[x]] > counts[fill]) fill = line[x];
    int top = 0, bottom = height;
    for (int x = left; x < right; ++x) {
        if (line[x] != fill) continue;
        int y = row;
        while (y > 0 && native[(y - 1) * pitch + x] == fill) --y;
        if (y > top) top = y;
        y = row + 1;
        while (y < height && native[y * pitch + x] == fill) ++y;
        if (y < bottom) bottom = y;
    }
    int l = left, r = right;
    while (l > 0 && line[l - 1] == fill) --l;
    while (r < width && line[r] == fill) ++r;
    out.left = l; out.top = top; out.right = r; out.bottom = bottom;
    return !out.empty();
}

// HD offset that centres [inkStart, inkEnd) inside native [boxStart, boxEnd).
inline int centreOffset(int inkStart, int inkEnd, int boxStart, int boxEnd, int scale) {
    return ((boxStart + boxEnd) * scale - (inkStart + inkEnd)) / 2;
}

// Only lines already roughly centred were meant to be: left-aligned text keeps
// its position.
inline bool meantCentred(int inkStart, int inkEnd, int boxStart, int boxEnd, int scale) {
    const int offset = centreOffset(inkStart, inkEnd, boxStart, boxEnd, scale);
    const int slack = (boxEnd - boxStart) * scale - (inkEnd - inkStart);
    return slack >= 0 && 4 * (offset < 0 ? -offset : offset) <= slack;
}

} // namespace HdBanner

#endif
