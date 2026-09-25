// Included in object.cpp, inside namespace Scumm.
int ScummEngine::hdInventoryOffset() const {
    return _game.id == GID_CMI && ConfMan.hasKey("playtest_session") && hdInventoryOpen()
        ? HdInventory::centerOffset(_screenWidth) : 0;
}

void ScummEngine::beginHDInventoryOverlay() {
    // Native scripts temporarily clear/rebuild the blast queue. Input for
    // the next tick must use the layout that was actually presented.
    _hdInventoryInputOffset = hdInventoryOffset();
    _hdInventoryLayer = _hdInventoryInputOffset > 0;
    if (!_hdInventoryLayer || HdRemaster::state().active) return;
    // The GPU already separates scene and UI. Give CPU fallback the same
    // separation so centering the inventory never translates the background.
    _hdInventoryScene.copyFrom(_hdComposite);
    memset(_hdComposite.getPixels(), 0, _hdComposite.pitch * _hdComposite.h);
}

void ScummEngine::finishHDInventoryOverlay() {
    if (!_hdInventoryLayer) return;
    const int offset = hdInventoryOffset() * _hdScale;
    for (int y = 0; y < _hdComposite.h; ++y) {
        uint32 *row = (uint32 *)_hdComposite.getBasePtr(0, y);
        memmove(row + offset, row, (_hdComposite.w - offset) * sizeof(uint32));
        memset(row, 0, offset * sizeof(uint32));
        if (!HdRemaster::state().active) {
            const uint32 *scene = (const uint32 *)_hdInventoryScene.getBasePtr(0, y);
            for (int x = 0; x < _hdComposite.w; ++x) row[x] = HdInventory::overScene(row[x], scene[x]);
        }
    }
    _hdInventoryScene.free();
    _hdInventoryLayer = false;
}

bool ScummEngine_v6::hasHDInventory() {
    if (_game.id != GID_CMI || !_hdBackgroundSurface.getPixels() ||
        !_hdObjectManager || !_hdObjectManager->isEnabled()) return false;
    for (int i = 0; i < _blastObjectQueuePos; ++i) {
        const BlastObject &eo = _blastObjectQueue[i];
        if (eo.number == 114 && _hdObjectManager->getObjectSurface(114, 3,
                HdInventory::imageIndex(eo.image))) return true;
    }
    return false;
}

void ScummEngine_v6::drawHDInventory() {
    if (_game.id != GID_CMI || !_hdObjectManager || !_hdObjectManager->isEnabled()) return;
    // The queue is authoritative: picked-up items, paging and closing the
    // inventory all take effect in the same frame, without cached ghost icons.
    for (int pass = 0; pass < 2; ++pass) {
        for (int i = 0; i < _blastObjectQueuePos; ++i) {
            BlastObject &eo = _blastObjectQueue[i];
            if (!HdInventory::isObject(eo.number) || (eo.number == 114) != (pass == 0)) continue;
            drawBlastObject(&eo, true);
        }
    }
}
