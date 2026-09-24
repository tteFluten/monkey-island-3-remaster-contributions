// Resolve complete replacement poses BEFORE copying native foreground pixels.
// Original actors remain in the simulation buffer for scripts/masking/hit tests,
// but their pixels never become an underpainting beneath valid SVG/PNG poses.
struct QuiverPose {
    Actor *actor;
    Common::Array<Graphics::Surface *> textures;
};
Common::Array<QuiverPose> quiverPoses;
Common::Array<byte> quiverNative, quiverWithoutCoin;
if (_hdUICostumeManager || (playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())) {
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
        // Preserve sparse sea animation with its actual native transparency
        // and palette instead of treating the generated gray matte as paint.
        if (HdSceneVisibility::nativePaletteEffect(_currentRoom, a->_costume)) continue;
        const bool coin = a->_costume == 1 && a->_layer < 0;
        HdCostumeManager *manager = coin ? _hdUICostumeManager :
            (playtestExactRoom(_currentRoom) ? _hdQuiverManager : nullptr);
        if (!manager || !manager->isEnabled()) continue;
        QuiverPose pose;
        pose.actor = a;
        bool valid = true;
        for (uint di = 0; di < a->_quiverDraws.size(); ++di) {
            const Actor::QuiverDraw &d = a->_quiverDraws[di];
            Graphics::Surface *texture = new Graphics::Surface();
            pose.textures.push_back(texture);
            if (coin && d.cel < 63) continue; // Native sparkle captured separately.
            if (d.costume != a->_costume || !manager->loadCostume(d.costume, d.cel, *texture, d.width * scale, d.height * scale) ||
                texture->w != d.width * scale || texture->h != d.height * scale || texture->format.bytesPerPixel != 4) {
                valid = false; break;
            }
        }
        if (valid) quiverPoses.push_back(pose);
        else for (uint i = 0; i < pose.textures.size(); ++i) {
            pose.textures[i]->free(); delete pose.textures[i];
        }
    }
    if (!quiverPoses.empty()) {
        quiverNative.resize(visW * visH);
        for (int y = 0; y < visH; ++y)
            memcpy(&quiverNative[y * visW], vs->getBasePtr(vs->xstart, y), visW);
        // Unwind front to back, restoring the actual scene under each actor.
        // Later dialogue/foreground changes remain intact. Missing poses were
        // excluded above and retain all their original pixels.
        for (int ai = (int)quiverPoses.size() - 1; ai >= 0; --ai) {
            Actor *a = quiverPoses[ai].actor;
            QuiverNative::removeActor(quiverNative.data(), a->_quiverUnder.data(),
                                      a->_quiverAfter.data(), quiverNative.size());
            // HD characters must remain visible through transparent areas of
            // the replacement coin, even inside the wider native silhouette.
            if (a->_costume == 1 && a->_layer < 0)
                quiverWithoutCoin = quiverNative;
        }
    }
}
