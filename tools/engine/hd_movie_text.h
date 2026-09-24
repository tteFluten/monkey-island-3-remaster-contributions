#ifndef SCUMM_HD_MOVIE_TEXT_H
#define SCUMM_HD_MOVIE_TEXT_H

#include "common/rect.h"

namespace Scumm {
struct HdMovieGlyph {
	int slot, chr, x100, y;
	byte color;
	Common::Rect clip;
};
}
#endif
