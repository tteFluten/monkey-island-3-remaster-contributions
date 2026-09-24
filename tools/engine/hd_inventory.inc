// Included in object.cpp, inside namespace Scumm.
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
