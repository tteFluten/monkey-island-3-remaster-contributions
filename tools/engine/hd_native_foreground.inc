// Integral 4x expansion avoids per-pixel division and tiny variable-sized
// fills. The CPU reference below remains available for visual comparisons.
if (remaster.active && scale == 4 && hdW == visW * 4 && hdH == visH * 4) {
    uint32 palette[256];
    for (int i = 0; i < 256; ++i)
        palette[i] = _currentPalette[i * 3] | (_currentPalette[i * 3 + 1] << 8) |
            (_currentPalette[i * 3 + 2] << 16) | 0xff000000u;
    for (int y = 0; y < visH; ++y) {
        const byte *native = quiverNative.empty() ? (const byte *)vs->getBasePtr(vs->xstart, y + _screenTop) : quiverNative.data() + y * visW;
        const byte *clean = _hdCleanBackground.getPixels() ? (const byte *)_hdCleanBackground.getBasePtr(0, y) : nullptr;
        const bool useClean = _hdCurrentRoom == _currentRoom && _hdCleanValid && clean;
        uint32 *row = (uint32 *)_hdComposite.getBasePtr(0, y * 4);
        const int pitch = _hdComposite.pitch / 4;
        for (int x = 0; x < visW; ++x) {
            const byte pixel = native[x];
            if (pixel == 255 || (useClean && (!_hdCleanValid[y * visW + x] || pixel == clean[x]))) continue;
            const uint32 color = palette[pixel];
            for (int dy = 0; dy < 4; ++dy) {
                uint32 *out = row + dy * pitch + x * 4;
                out[0] = color; out[1] = color; out[2] = color; out[3] = color;
            }
            ++step2_fgPixels;
        }
    }
} else
