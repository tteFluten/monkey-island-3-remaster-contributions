// Floor-only pass: native foreground, HD objects, actors, dialogue and cursor
// are all composited afterwards. The original z-buffer clips baked foreground.
if (_game.id == GID_CMI && _currentRoom != 87 && !hdColorGradeState().shadowBypass &&
    hdSceneLookValue(_currentRoom, HdSceneLook::kShadowOpacity) > 0) {
    const int shadowOffsetX = hdSceneLookValue(_currentRoom, HdSceneLook::kShadowX);
    const int shadowOffsetY = hdSceneLookValue(_currentRoom, HdSceneLook::kShadowY);
    const float shadowWidth = hdSceneLookValue(_currentRoom, HdSceneLook::kShadowWidth) / 100.0f;
    const float shadowOvalness = hdSceneLookValue(_currentRoom, HdSceneLook::kShadowOvalness) / 100.0f;
    const int shadowAlpha = (hdSceneLookValue(_currentRoom, HdSceneLook::kShadowOpacity) * 255 + 50) / 100;
    const uint32 shadowColor = hdSceneLookValue(_currentRoom, HdSceneLook::kShadowRed) |
        (hdSceneLookValue(_currentRoom, HdSceneLook::kShadowGreen) << 8) |
        (hdSceneLookValue(_currentRoom, HdSceneLook::kShadowBlue) << 16);
    static Common::Array<HdActorShadow::GroundAnchor> groundAnchors;
    groundAnchors.resize(_numActors);
    for (int ai = 0; ai < _numActors; ++ai) {
        Actor *a = _actors[ai];
        if (!a || !a->_visible || !a->_costume || a->_room != _currentRoom || a->_layer < 0) continue;
        // Follow the game's shadow-enabled actors, plus the known main walking
        // costume and Wally. Animated scenery/cursor actors are not casters.
        if (a->_shadowMode != 3 && a->_costume != 2 && !(_currentRoom == 9 && a->_costume == 25)) continue;
        if (a->_quiverWidth != visW || a->_quiverHeight != visH || a->_quiverCamera != vs->xstart ||
            a->_quiverUnder.size() != (uint)(visW * visH) || a->_quiverAfter.size() != a->_quiverUnder.size()) continue;
        // Native dirty draws may repaint only a talking head. Use the complete
        // replacement pose's alpha for feet whenever a validated pose exists.
        Common::Array<byte> silhouette, empty;
        const byte *under = a->_quiverUnder.data(), *after = a->_quiverAfter.data();
        for (uint pi = 0; pi < quiverPoses.size(); ++pi) {
            if (quiverPoses[pi].actor != a || quiverPoses[pi].nativeColorFallback) continue;
            silhouette.resize(visW * visH); empty.resize(visW * visH);
            memset(silhouette.data(), 0, silhouette.size());
            memset(empty.data(), 0, empty.size());
            for (uint di = 0; di < quiverPoses[pi].textures.size(); ++di) {
                const Actor::QuiverDraw &d = a->_quiverDraws[di];
                const Graphics::Surface &texture = *quiverPoses[pi].textures[di];
                if (!texture.getPixels() || d.screenWidth <= 0 || d.screenHeight <= 0) continue;
                for (int y = MAX(0, d.screenTop); y < MIN(visH, d.screenTop + d.screenHeight); ++y) {
                    int sy = MIN<int>(texture.h - 1, (2 * (y - d.screenTop) + 1) * texture.h / (2 * d.screenHeight));
                    const uint32 *row = (const uint32 *)texture.getBasePtr(0, sy);
                    for (int x = MAX(0, d.screenLeft); x < MIN(visW, d.screenLeft + d.screenWidth); ++x) {
                        int sx = MIN<int>(texture.w - 1, (2 * (x - d.screenLeft) + 1) * texture.w / (2 * d.screenWidth));
                        if (d.mirror) sx = texture.w - 1 - sx;
                        if ((row[sx] >> 24) >= 128) silhouette[y * visW + x] = 200;
                    }
                }
            }
            under = empty.data(); after = silhouette.data();
            break;
        }
        const bool sceneAligned = a->getPos().x == 0 && a->getPos().y == a->getElevation();
        const int elevation = HdActorShadow::groundElevation(a->getPos().x, a->getPos().y, a->getElevation());
        HdActorShadow::Footprint shadow = HdActorShadow::footprint(
            under, after, visW, visH,
            a->getPos().x - vs->xstart, a->getPos().y - _screenTop + hdVoodooExteriorActorOffset(a),
            elevation, sceneAligned);
        if (_hdFrameCount % 120 == 0 && !shadow.valid)
            hdPrintf("CONTACT-SHADOW-SKIP actor=%d position=%d,%d elevation=%d pose=%d", a->_number,
                     a->getPos().x, a->getPos().y, a->getElevation(), !silhouette.empty());
        if (!shadow.valid) continue;
        auto &anchor = groundAnchors[ai];
        if (sceneAligned) {
            if (anchor.room != _currentRoom || anchor.costume != a->_costume || anchor.revision != _playtestCommandId) {
                anchor.room = _currentRoom; anchor.costume = a->_costume; anchor.revision = _playtestCommandId;
                anchor.actorY = a->getPos().y;
                anchor.worldY = shadow.y + _screenTop;
            }
            // Camera motion and actual actor movement still follow the room;
            // changing costume pixels cannot move this calibrated baseline.
            shadow.y = anchor.worldY + a->getPos().y - anchor.actorY - _screenTop;
        } else {
            anchor.room = -1;
        }
        // Offsets are in original game pixels, so 4:3, 16:9 and HD scaling
        // follow the same feet position without changing actor coordinates.
        shadow.x += shadowOffsetX;
        shadow.y += shadowOffsetY;
        shadow.radiusX *= shadowWidth;
        shadow.radiusY = shadow.radiusX * shadowOvalness;
        shadow.opacity = shadowAlpha * (80 - elevation) / 80;
        if (!shadow.opacity) continue;
        int z = -1, lowest = -1;
        for (uint di = 0; di < a->_quiverDraws.size(); ++di) {
            const Actor::QuiverDraw &d = a->_quiverDraws[di];
            if (d.screenTop + d.screenHeight > lowest) {
                lowest = d.screenTop + d.screenHeight; z = d.z;
            }
        }
        if (a->_quiverDraws.empty()) continue;
        const float cx = shadow.x * scale, cy = shadow.y * scale;
        const float rx = shadow.radiusX * scale, ry = shadow.radiusY * scale;
        const int x0 = MAX(0, (int)(cx - rx)), x1 = MIN(hdW, (int)(cx + rx) + 1);
        const int y0 = MAX(0, (int)(cy - ry)), y1 = MIN(hdH, (int)(cy + ry) + 1);
        for (int y = y0; y < y1; ++y) {
            uint32 *dest = (uint32 *)_hdComposite.getBasePtr(0, y);
            const byte *mask = z >= 0 && z < _gdi->_numZBuffer ? getMaskBuffer(0, y / scale + _screenTop, z) : nullptr;
            const float dy = (y + 0.5f - cy) / ry;
            for (int x = x0; x < x1; ++x) {
                if (HdObjectDepth::masked(mask, x / scale, vs->xstart & 7)) continue;
                const float dx = (x + 0.5f - cx) / rx;
                dest[x] = HdActorShadow::shade(dest[x], dx, dy, shadow.opacity, shadowColor);
                if (HdRemaster::state().active && dx * dx + dy * dy < 1.0f)
                    dest[x] = (dest[x] & 0xffffffu) | (HdRemaster::opacity(shadow.opacity, dest[x] >> 24) << 24);
            }
        }
        if (_hdFrameCount % 120 == 0)
            hdPrintf("CONTACT-SHADOW actor=%d center=%.1f,%.1f radius=%.1f,%.1f opacity=%d", a->_number,
                     shadow.x, shadow.y, shadow.radiusX, shadow.radiusY, shadow.opacity);
    }
}
