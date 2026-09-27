// Resolve complete replacement poses BEFORE copying native foreground pixels.
// Original actors remain in the simulation buffer for scripts/masking/hit tests,
// but their pixels never become an underpainting beneath valid SVG/PNG poses.
struct QuiverPose {
    Actor *actor;
    bool water = false;
    bool nativeColorFallback = false;
    bool topaz = false;
    Graphics::Surface cannonFrom;
    Common::Array<Graphics::Surface *> textures;
};
// Pin decoded surfaces until both scene and coin passes finish. Views borrow
// pixel storage; no full costume texture is copied for an interpolated frame.
if (_hdUICostumeManager) _hdUICostumeManager->beginBorrow();
if (_hdQuiverManager) _hdQuiverManager->beginBorrow();
Common::Array<QuiverPose> quiverPoses;
Common::Array<byte> quiverNative, quiverWithoutCoin, quiverWithoutWater;
bool quiverHasWater = false;
auto &waterState = HdRemaster::state();
const bool waterRequested = waterState.active && HdWater::room(_currentRoom) &&
    (!ConfMan.hasKey("hd_water_shader") || ConfMan.getBool("hd_water_shader"));
waterState.water = false;
waterState.waterSurface = false;
if (waterRequested) {
    if (waterState.waterCoverage.w != visW || waterState.waterCoverage.h != visH) {
        waterState.waterCoverage.free();
        waterState.waterCoverage.create(visW, visH, Graphics::PixelFormat::createFormatCLUT8());
    }
    memset(waterState.waterCoverage.getPixels(), 0, waterState.waterCoverage.pitch * visH);
    auto &surface = hdWaterSurface();
    if (surface.prepare(_hdBackgroundSurface, _currentRoom, _playtestCommandId, scale)) {
        waterState.water = waterState.waterSurface = true;
        waterState.waterReflectionIntercept = surface.reflectionIntercept;
        waterState.waterReflectionSlope = surface.reflectionSlope;
        for (int y = 0; y < visH; ++y) {
            const int sourceY = y + waterState.backgroundY / scale;
            const int sourceX = waterState.backgroundX / scale;
            if (sourceY < 0 || sourceY >= surface.height || sourceX < 0 || sourceX >= surface.width) continue;
            memcpy(waterState.waterCoverage.getBasePtr(0, y), surface.depth.data() + sourceY * surface.width + sourceX,
                MIN(visW, surface.width - sourceX));
        }
    }
}
if (waterRequested || _hdUICostumeManager || (playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())) {
    Common::Array<Actor *> actors;
    for (int ai = 0; ai < _numActors; ++ai) {
        Actor *a = _actors[ai];
        if (a && a->_visible && a->_room == _currentRoom && !a->_quiverDraws.empty())
            actors.push_back(a);
    }
    for (uint i = 1; i < actors.size(); ++i) {
        Actor *a = actors[i];
        int key = a->getPos().y - a->_layer * 2000;
        uint j = i;
        while (j && actors[j - 1]->getPos().y - actors[j - 1]->_layer * 2000 > key) {
            actors[j] = actors[j - 1]; --j;
        }
        actors[j] = a;
    }
    for (uint ai = 0; ai < actors.size(); ++ai) {
        Actor *a = actors[ai];
        if (a->_quiverWidth != visW || a->_quiverHeight != visH || a->_quiverCamera != vs->xstart ||
            a->_quiverAfter.size() != (uint)(visW * visH) || a->_quiverUnder.size() != a->_quiverAfter.size())
            continue;
        if (waterRequested && HdWater::ambient(_currentRoom, a->_costume)) {
            QuiverPose pose;
            pose.actor = a; pose.water = true;
            quiverPoses.push_back(pose);
            quiverHasWater = true;
            waterState.water = true;
            continue; // No PNG decode, upload or replacement draw for water.
        }
        // Preserve sparse sea animation with its actual native transparency
        // and palette instead of treating the generated gray matte as paint.
        if (HdSceneVisibility::nativePaletteEffect(_currentRoom, a->_costume)) continue;
        const bool coin = a->_costume == 1 && a->_layer < 0;
        HdCostumeManager *manager = coin ? _hdUICostumeManager :
            (playtestExactRoom(_currentRoom) ? _hdQuiverManager : nullptr);
        if (!manager || !manager->isEnabled()) continue;
        QuiverPose pose;
        pose.actor = a;
        const Common::String pack = ConfMan.hasKey("playtest_character_pack")
            ? ConfMan.get("playtest_character_pack") : Common::String();
        pose.topaz = pack == "topaz" || pack == "topaz-crisp";
        // Rejected stand-up PNGs retain the original complete silhouette, but
        // must pass through the same fixed room lighting as adjacent HD cels.
        if (pose.topaz && _currentRoom == 9 && a->_costume == 3 && a->_quiverDraws.size() == 1 &&
            (a->_quiverDraws[0].cel == 15 || a->_quiverDraws[0].cel == 16)) {
            pose.nativeColorFallback = true;
            quiverPoses.push_back(pose);
            continue;
        }
        bool valid = true;
        for (uint di = 0; di < a->_quiverDraws.size(); ++di) {
            const Actor::QuiverDraw &d = a->_quiverDraws[di];
            Graphics::Surface *texture = new Graphics::Surface();
            pose.textures.push_back(texture);
            if (coin && d.cel < 63) continue; // Native sparkle captured separately.
            if (d.costume != a->_costume || !manager->loadCostume(d.costume, d.cel, *texture, d.width * scale, d.height * scale, true) ||
                texture->w != d.width * scale || texture->h != d.height * scale || texture->format.bytesPerPixel != 4) {
                valid = false; break;
            }
        }
        if (valid) {
            if (_hdInterpolating && _currentRoom == 10 && a->_costume == 35 &&
                a->_number == _hdMotionCannon.actor && _hdMotionCannon.moving &&
                a->_quiverDraws.size() == 1 && a->_quiverDraws[0].cel == _hdMotionCannon.to.cel) {
                const auto &from = _hdMotionCannon.from;
                // Borrow both endpoint textures under the existing cache pin.
                if (!manager->loadCostume(35, from.cel, pose.cannonFrom,
                        from.sourceWidth * scale, from.sourceHeight * scale, true) ||
                    pose.cannonFrom.w != from.sourceWidth * scale ||
                    pose.cannonFrom.h != from.sourceHeight * scale || pose.cannonFrom.format.bytesPerPixel != 4)
                    pose.cannonFrom = Graphics::Surface(); // Missing art keeps the current exact pose.
            }
            quiverPoses.push_back(pose);
        }
        else for (uint i = 0; i < pose.textures.size(); ++i) {
            delete pose.textures[i];
        }
    }
    if (!quiverPoses.empty()) {
        quiverNative.resize(visW * visH);
        for (int y = 0; y < visH; ++y)
            memcpy(&quiverNative[y * visW], vs->getBasePtr(vs->xstart, y + _screenTop), visW);
        // Shader water replaces these native sprites completely. Keep a
        // separate foreground reference with only water removed: otherwise
        // invisible ripples still occlude the cannonball and other HD actors.
        // Retain every other actor, text and foreground pixel for clipping.
        if (quiverHasWater) quiverWithoutWater = quiverNative;
        // Unwind front to back, restoring the actual scene under each actor.
        // Later dialogue/foreground changes remain intact. Missing poses were
        // excluded above and retain all their original pixels.
        for (int ai = (int)quiverPoses.size() - 1; ai >= 0; --ai) {
            Actor *a = quiverPoses[ai].actor;
            const bool water = quiverPoses[ai].water;
            const bool mixedWater = water && HdWater::mixedOverlay(_currentRoom, a->_costume);
            if (water)
                HdWater::removeOverlay(quiverWithoutWater.data(), a->_quiverUnder.data(),
                    a->_quiverAfter.data(), quiverWithoutWater.size(), _currentPalette, mixedWater);
            if (quiverPoses[ai].water && !waterState.waterSurface)
                for (int y = 0; y < visH; ++y)
                    HdWater::coverage((byte *)waterState.waterCoverage.getBasePtr(0, y),
                        &quiverNative[y * visW], &a->_quiverUnder[y * visW],
                        &a->_quiverAfter[y * visW], visW);
            if (water)
                HdWater::removeOverlay(quiverNative.data(), a->_quiverUnder.data(),
                    a->_quiverAfter.data(), quiverNative.size(), _currentPalette, mixedWater);
            else
                QuiverNative::removeActor(quiverNative.data(), a->_quiverUnder.data(),
                                          a->_quiverAfter.data(), quiverNative.size());
            // HD characters must remain visible through transparent areas of
            // the replacement coin, even inside the wider native silhouette.
            if (a->_costume == 1 && a->_layer < 0)
                quiverWithoutCoin = quiverNative;
        }
    }
}
