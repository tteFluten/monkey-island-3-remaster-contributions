#ifndef SCUMM_HD_FONT_SIZE_H
#define SCUMM_HD_FONT_SIZE_H

namespace Scumm {

// Percent of the original game's text size; the atlas stays at runtime scale.
inline int hdFontSizePercent(int percent) {
	return percent >= 25 && percent <= 100 && percent % 5 == 0 ? percent : 65;
}

inline int hdFontSizeMetric(int pixels, int percent) {
	return pixels <= 0 ? pixels : (pixels * percent + 99) / 100;
}

} // namespace Scumm
#endif
