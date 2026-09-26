#ifndef SCUMM_HD_MOVIE_TEXT_H
#define SCUMM_HD_MOVIE_TEXT_H

#include "common/rect.h"
#include "common/hd_aspect.h"
#include "common/util.h"

namespace Scumm {
namespace HdMovieText {
inline int sizePercent(int gameplayPercent) {
    // Keep the existing size preference, with a smaller cinematic treatment.
    return MAX(25, ((gameplayPercent * 80 / 100 + 2) / 5) * 5);
}
inline Common::Rect safeArea(int width, int height, int aspect) {
    const HdAspect::Rect crop = HdAspect::frame(width, height, aspect);
    const int marginX = MAX(1, crop.w / 20), marginY = MAX(1, crop.h / 20);
    return Common::Rect(crop.x + marginX, crop.y + marginY,
        crop.x + crop.w - marginX, crop.y + crop.h - marginY);
}
}
struct HdMovieGlyph {
	int slot, chr, x100, y, sizePercent;
	byte color;
	Common::Rect clip;
};
}
#endif
