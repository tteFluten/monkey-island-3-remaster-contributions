// Validated poses have already been removed from quiverNative before the native
// foreground copy. Draw only their replacement textures, in original depth order.
if (!quiverPoses.empty()) {
    for (uint ai = 0; ai < quiverPoses.size(); ++ai) {
        Actor *a = quiverPoses[ai].actor;
        const bool coin = a->_costume == 1 && a->_layer < 0;
        if (coin != hdCoinPass) continue;
        const HdActorLighting::Tint lighting = coin ? HdActorLighting::Tint() : actorLighting(a);
        if (quiverPoses[ai].nativeColorFallback) {
            for (int y = 0; y < visH; ++y) {
                const byte *native = !quiverWithoutCoin.empty() ? &quiverWithoutCoin[y * visW] :
                    !quiverWithoutWater.empty() ? &quiverWithoutWater[y * visW] :
                    (const byte *)vs->getBasePtr(vs->xstart, y + _screenTop);
                for (int x = 0; x < visW; ++x) {
                    const int offset = y * visW + x;
                    const byte index = a->_quiverAfter[offset];
                    if (index == a->_quiverUnder[offset] || native[x] != index) continue;
                    const byte *rgb = _darkenPalette + index * 3;
                    const uint32 color = lighting.apply(0xff000000u | rgb[0] | (rgb[1] << 8) | (rgb[2] << 16));
                    for (int yy = y * scale; yy < MIN(hdH, (y + 1) * scale); ++yy)
                        for (int xx = x * scale; xx < MIN(hdW, (x + 1) * scale); ++xx) {
                            *(uint32 *)_hdComposite.getBasePtr(xx, yy) = color;
                            hdAlphaMask[yy * hdW + xx] = 1;
                        }
                }
            }
            continue;
        }
        Common::Array<Graphics::Surface *> &textures = quiverPoses[ai].textures;
        for (uint di = 0; di < textures.size(); ++di) {
            const Actor::QuiverDraw &d = a->_quiverDraws[di];
            const Graphics::Surface &texture = *textures[di];
            if (coin && d.cel < 63) {
                for (uint pi = 0; pi < d.coinPixels.size(); ++pi) {
                    const Actor::CoinPixel &p = d.coinPixels[pi];
                    const byte *rgb = _currentPalette + p.color * 3;
                    uint32 color = _hdComposite.format.RGBToColor(rgb[0], rgb[1], rgb[2]);
                    for (int y = p.y * scale; y < MIN(hdH, (p.y + 1) * scale); ++y)
                        for (int x = p.x * scale; x < MIN(hdW, (p.x + 1) * scale); ++x) {
                            *(uint32 *)_hdComposite.getBasePtr(x, y) = color;
                            hdAlphaMask[y * hdW + x] = 1;
                        }
                }
                continue;
            }
            int edgeTreatment = HdCostumeEdge::guybrushHead(d.costume, d.cel) ? 1 : 0;
            // The last alpha row of this Topaz head is empty, exposing a line
            // between the head and torso. Extend its adjacent edge row only
            // when the original matching body is present at the native join.
            if (quiverPoses[ai].topaz && _currentRoom == 9 && d.costume == 2 && d.cel == 52)
                for (uint bi = 0; bi < textures.size(); ++bi) {
                    const Actor::QuiverDraw &body = a->_quiverDraws[bi];
                    if (body.cel == 31 && body.mirror == d.mirror &&
                        d.screenTop + d.screenHeight == body.screenTop + 1)
                        edgeTreatment = 3;
                }
            // Bounds come from the original decoder's scale table, not a
            // floating-point approximation of actor scaling.
            int w = d.screenWidth * scale;
            int h = d.screenHeight * scale;
            if (!w || !h) continue;
            int left = d.screenLeft * scale;
            int top = d.screenTop * scale;
            unsigned int cannonFraction = 1024;
            const Graphics::Surface &cannonFrom = quiverPoses[ai].cannonFrom;
            if (cannonFrom.getPixels()) {
                cannonFraction = _hdMotionFraction;
                const auto &from = _hdMotionCannon.from;
                const auto &to = _hdMotionCannon.to;
                // Align the two barrel poses to interpolated bounds before
                // blending their pixels, so the base and outline move together.
                left = HdMotion::Track::mix(from.left * scale, to.left * scale, cannonFraction);
                top = HdMotion::Track::mix(from.top * scale, to.top * scale, cannonFraction);
                w = HdMotion::Track::mix(from.width * scale, to.width * scale, cannonFraction);
                h = HdMotion::Track::mix(from.height * scale, to.height * scale, cannonFraction);
            }
            static HdCostumeRaster::Cache rasterCache;
            rasterCache.scope(_currentRoom, _playtestCommandId);
            const uint32 *raster = HdRemaster::state().active ? rasterCache.get(
                (const uint32 *)texture.getPixels(), texture.pitch / 4, texture.w, texture.h,
                w, h, d.costume, d.cel, d.mirror, edgeTreatment, lighting) : nullptr;
            const uint32 *cannonRaster = cannonFraction < 1024 && HdRemaster::state().active ? rasterCache.get(
                (const uint32 *)cannonFrom.getPixels(), cannonFrom.pitch / 4, cannonFrom.w, cannonFrom.h,
                w, h, 35, _hdMotionCannon.from.cel, _hdMotionCannon.from.mirror, 0, lighting) : nullptr;
            for (int yy = MAX(0, top); yy < MIN(hdH, top + h); ++yy) {
                const int ny = yy / scale;
                const byte *nativeRow = !coin && !quiverWithoutCoin.empty()
                    ? &quiverWithoutCoin[ny * visW] : !coin && !quiverWithoutWater.empty()
                    ? &quiverWithoutWater[ny * visW] : (const byte *)vs->getBasePtr(vs->xstart, ny + _screenTop);
                const byte *actorRow = &a->_quiverAfter[ny * visW];
                // Resolve the z-buffer resource once per row, never once per HD
                // pixel. Preserve sub-strip camera offsets in the byte lookup.
                const byte *maskRow = d.z >= 0 && d.z < _gdi->_numZBuffer ? getMaskBuffer(0, ny + _screenTop, d.z) : nullptr;
                const int maskOffset = vs->xstart & 7;
                int sourceY = (yy - top) * texture.h / h;
                uint32 *dest = (uint32 *)_hdComposite.getBasePtr(0, yy);
                for (int xx = MAX(0, left); xx < MIN(hdW, left + w); ++xx) {
                    int nx = xx / scale;
                    if (nativeRow[nx] != actorRow[nx]) continue;
                    if (!coin && HdObjectDepth::masked(maskRow, nx, maskOffset)) continue;
                    int sourceX = (xx - left) * texture.w / w;
                    if (d.mirror) sourceX = texture.w - 1 - sourceX;
                    // Extend real outline RGB into the soft matte BEFORE room
                    // lighting; retain alpha and the native geometry exactly.
                    uint32 color = raster ? raster[(yy - top) * w + xx - left] : lighting.apply(HdCostumeEdge::sample(
                        (const uint32 *)texture.getPixels(), texture.pitch / 4,
                        texture.w, texture.h, sourceX, sourceY, edgeTreatment));
                    if (cannonFraction < 1024) {
                        int oldX = (xx - left) * cannonFrom.w / w;
                        if (_hdMotionCannon.from.mirror) oldX = cannonFrom.w - 1 - oldX;
                        const int oldY = (yy - top) * cannonFrom.h / h;
                        const uint32 oldColor = cannonRaster ? cannonRaster[(yy - top) * w + xx - left] :
                            lighting.apply(*(const uint32 *)cannonFrom.getBasePtr(oldX, oldY));
                        color = HdMotion::CannonAim::blend(oldColor, color, cannonFraction);
                    }
                    uint32 alpha = color >> 24;
                    if (!alpha) continue;
                    if (alpha == 255) {
                        dest[xx] = color; hdAlphaMask[yy * hdW + xx] = 1; continue;
                    }
                    uint32 previous = dest[xx];
                    uint32 r = ((color & 255) * alpha + (previous & 255) * (255 - alpha) + 127) / 255;
                    uint32 g = (((color >> 8) & 255) * alpha + ((previous >> 8) & 255) * (255 - alpha) + 127) / 255;
                    uint32 b = (((color >> 16) & 255) * alpha + ((previous >> 16) & 255) * (255 - alpha) + 127) / 255;
                    dest[xx] = r | (g << 8) | (b << 16) |
                        ((alpha + ((previous >> 24) * (255 - alpha) + 127) / 255) << 24);
                    hdAlphaMask[yy * hdW + xx] = 1;
                }
            }
            if (_hdFrameCount % 30 == 0)
                hdPrintf("QUIVER actor=%d costume=%d cel=%d at=%d,%d size=%d,%d mirror=%d light=%d,%d,%d", a->_number, d.costume, d.cel, left, top, w, h, d.mirror, lighting.channel[0], lighting.channel[1], lighting.channel[2]);
        }
        for (uint i = 0; i < textures.size(); ++i) {
            delete textures[i];
        }
    }
}

if (hdCoinPass) {
    if (_hdUICostumeManager) _hdUICostumeManager->endBorrow();
    if (_hdQuiverManager) _hdQuiverManager->endBorrow();
}
