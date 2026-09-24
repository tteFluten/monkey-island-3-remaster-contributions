#ifndef SCUMM_HD_VIDEO_SUPPORT_H
#define SCUMM_HD_VIDEO_SUPPORT_H

namespace HdVideoSupport {
// Native COMI SMUSH maps the selected text color to white and index 225 to black.
inline unsigned char textColor(unsigned char value, int col) {
    const signed char color = (col != -1) ? col : 1;
    if ((signed char)value == -color) return 255;
    if ((signed char)value == -31) return 0;
    return value;
}
// Two renders against different backgrounds distinguish text (including black
// outlines and palette index 255) from untouched transparent pixels.
inline void subtitles(unsigned int *frame, int width, int height,
                      const unsigned char *dark, const unsigned char *light,
                      int textWidth, int textHeight, const unsigned char *palette) {
    for (int y = 0; y < height; ++y) {
        int sy = y * textHeight / height;
        for (int x = 0; x < width; ++x) {
            int i = sy * textWidth + x * textWidth / width;
            if (dark[i] != light[i]) continue;
            const unsigned char *rgb = palette + dark[i] * 3;
            frame[y * width + x] = rgb[0] | (rgb[1] << 8) | (rgb[2] << 16) | 0xff000000u;
        }
    }
}
}
#endif
