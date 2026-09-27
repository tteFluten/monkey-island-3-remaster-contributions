#ifndef COMMON_HD_UI_UPLOAD_H
#define COMMON_HD_UI_UPLOAD_H
#include <cstring>
namespace HdUIUpload {
struct Rows { int top, bottom; };
// ScummVM's texture updater uploads complete rows. Include erased text and
// both the old/new positions when dialogue moves; an empty UI needs no upload.
inline Rows changed(const unsigned char *previous, int previousPitch,
                    const unsigned char *current, int currentPitch, int widthBytes, int height) {
    int top = 0, bottom = height;
    while (top < bottom && !std::memcmp(previous + top * previousPitch, current + top * currentPitch, widthBytes)) ++top;
    while (bottom > top && !std::memcmp(previous + (bottom - 1) * previousPitch, current + (bottom - 1) * currentPitch, widthBytes)) --bottom;
    return {top, bottom};
}
}
#endif
