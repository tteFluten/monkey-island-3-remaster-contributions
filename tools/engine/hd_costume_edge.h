#ifndef SCUMM_HD_COSTUME_EDGE_H
#define SCUMM_HD_COSTUME_EDGE_H

#include "hd_object_depth.h"

namespace HdCostumeEdge {
// Separate head cels in Guybrush's normal costume. Match resource identity,
// never actor number or limb order: walking/turning changes both pose and order.
inline bool guybrushHead(int costume, int cel) {
    if (costume != 2) return false;
    switch (cel) {
    case 4: case 34: case 47: case 52: case 58: case 63: return true;
    default: return false;
    }
}

inline unsigned int sample(const unsigned int *source, int pitch, int width,
                           int height, int x, int y, bool cleanMatte) {
    const unsigned int pixel = source[y * pitch + x];
    const unsigned int r = pixel & 255, g = (pixel >> 8) & 255, b = (pixel >> 16) & 255;
    const unsigned int lo = r < g ? (r < b ? r : b) : (g < b ? g : b);
    const unsigned int hi = r > g ? (r > b ? r : b) : (g > b ? g : b);
    // Black antialiased ink is intentional. Recolor only the light, neutral
    // gray matte, never the soft ink line or colored hair/skin highlights.
    return cleanMatte && lo > 60 && hi - lo < 24
        ? HdObjectDepth::edgeColor(source, pitch, width, height, x, y) : pixel;
}
}
#endif
