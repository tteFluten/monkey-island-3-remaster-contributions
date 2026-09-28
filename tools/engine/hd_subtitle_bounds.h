#ifndef HD_SUBTITLE_BOUNDS_H
#define HD_SUBTITLE_BOUNDS_H

#include "common/hd_aspect.h"

namespace HdSubtitleBounds {
// Native viewport coordinates, after the same uniform crop used for display.
// The renderer owns only the central surface in rooms with painted side panels.
inline HdAspect::Rect safeArea(int drawableWidth, int drawableHeight,
                              int viewportWidth, bool cover) {
    HdAspect::Rect visible = HdAspect::visibleGame(drawableWidth, drawableHeight,
        169, viewportWidth, cover);
    const int left = visible.x > 0 ? visible.x : 0;
    const int top = visible.y > 0 ? visible.y : 0;
    const int right = visible.x + visible.w < viewportWidth ? visible.x + visible.w : viewportWidth;
    const int bottom = visible.y + visible.h < 480 ? visible.y + visible.h : 480;
    const int width = right - left, height = bottom - top;
    const int marginX = width / 40 > 2 ? width / 40 : 2;
    const int marginY = height / 40 > 2 ? height / 40 : 2;
    return {left + marginX, top + marginY, width - marginX * 2, height - marginY * 2};
}
}
#endif
