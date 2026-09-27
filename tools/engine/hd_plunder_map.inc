// Included after the Look and scene-picker implementations in gfx.cpp.
bool ScummEngine::hdPlunderMapActive() {
    return _game.id == GID_CMI && _currentRoom == 13 && _hdCurrentRoom == 13 &&
        _hdScale > 1 && hdAspectRatio() == 169 && !isSmushActive() &&
        HdRemaster::state().wideRoom == 13 && HdRemaster::state().plunderMap;
}

void ScummEngine::publishHDPlunderMapInput() {
    HdRemaster::state().plunderMapInput = hdPlunderMapActive() &&
        !hdInventoryOpen() && !hdColorGradeState().panel && !_hdSceneJump.open && !isPaused();
}

void ScummEngine::placeHDPlunderMapForeground() {
    if (!hdPlunderMapActive() || hdInventoryOpen()) return;
    // The composition's alpha contains foreground coverage. Reproject only
    // that foreground, before text/UI, onto the unchanged new center painting.
    // This also handles original-pack actors and the scripted boat eraser.
    static Graphics::Surface before;
    before.copyFrom(_hdComposite);
    const int w = before.w, h = before.h, scale = _hdScale;
    int first = h, last = 0;
    for (int y = 0; y < h; ++y) {
        const uint32 *row = (const uint32 *)before.getBasePtr(0, y);
        uint32 *out = (uint32 *)_hdComposite.getBasePtr(0, y);
        const uint32 *bg = (const uint32 *)_hdBackgroundSurface.getBasePtr(0, y);
        for (int x = 0; x < w; ++x) if (row[x] >> 24) {
            first = MIN(first, y); last = y + 1;
            out[x] = bg[x] & 0x00ffffffu;
        }
    }
    if (first == h) return;
    Common::Array<int> sourceX;
    sourceX.resize(w);
    for (int x = 0; x < w; ++x)
        sourceX[x] = int(HdPlunderMap::sourceX((x + 0.5) / scale) * scale);
    for (int y = 0; y < h; ++y) {
        const int sy = int(HdPlunderMap::sourceY((y + 0.5) / scale) * scale);
        if (sy < first || sy >= last) continue;
        const uint32 *row = (const uint32 *)before.getBasePtr(0, sy);
        const uint32 *oldBg = (const uint32 *)_hdBackgroundSurface.getBasePtr(0, sy);
        const uint32 *newBg = (const uint32 *)_hdBackgroundSurface.getBasePtr(0, y);
        uint32 *out = (uint32 *)_hdComposite.getBasePtr(0, y);
        for (int x = 0; x < w; ++x) {
            const int sx = sourceX[x];
            if (sx < 0 || sx >= w) continue;
            const uint32 pixel = row[sx], alpha = pixel >> 24;
            if (!alpha) continue;
            uint32 placed = alpha << 24;
            // RGB is already composited: remove the old background share to
            // keep soft edges from carrying the previous location's colors.
            for (int shift = 0; shift <= 16; shift += 8) {
                const int value = int((pixel >> shift) & 255) +
                    (int((newBg[x] >> shift) & 255) - int((oldBg[sx] >> shift) & 255)) * (255 - int(alpha)) / 255;
                placed |= uint32(CLIP(value, 0, 255)) << shift;
            }
            out[x] = placed;
        }
    }
}
