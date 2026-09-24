// Retain the native sparkle/glint draws over the replacement coin. The guard
// records only pixels actually changed by this cel, using the live palette.
struct CoinGlintCapture {
    Actor::QuiverDraw *draw;
    VirtScreen &screen;
    int width, height;
    Common::Array<byte> before;
    CoinGlintCapture(Actor::QuiverDraw *d, VirtScreen &s, int w, int h)
        : draw(d), screen(s), width(w), height(h) {
        if (!draw) return;
        before.resize(w * h);
        for (int y = 0; y < h; ++y)
            memcpy(&before[y * w], screen.getBasePtr(screen.xstart, y), w);
    }
    ~CoinGlintCapture() {
        if (!draw) return;
        for (int y = 0; y < height; ++y) {
            const byte *row = (const byte *)screen.getBasePtr(screen.xstart, y);
            for (int x = 0; x < width; ++x)
                if (row[x] != before[y * width + x])
                    draw->coinPixels.push_back(Actor::CoinPixel{x, y, row[x]});
        }
    }
};
CoinGlintCapture coinGlint(
    !_actorHitMode && a->_costume == 1 && a->_layer < 0 &&
    !a->_quiverDraws.empty() && (code & AKC_CelMask) < 63
        ? &const_cast<Actor *>(a)->_quiverDraws.back() : nullptr,
    _vm->_virtscr[kMainVirtScreen], _vm->_screenWidth, _vm->_screenHeight);
