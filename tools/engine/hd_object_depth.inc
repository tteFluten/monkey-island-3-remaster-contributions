// Keep unreplaced native actors in front of HD objects wherever the native
// renderer placed them. Validated replacement poses are drawn later, so their
// original silhouettes must not punch holes through objects underneath them.
Common::Array<byte> nativeActorMask;
nativeActorMask.resize(visW * visH);
memset(nativeActorMask.data(), 0, nativeActorMask.size());
for (int ai = 0; ai < _numActors; ++ai) {
    Actor *a = _actors[ai];
    if (!a || !a->_visible || !a->_costume || a->_room != _currentRoom ||
        a->_quiverWidth != visW || a->_quiverHeight != visH ||
        a->_quiverCamera != vs->xstart ||
        a->_quiverUnder.size() != nativeActorMask.size() ||
        a->_quiverAfter.size() != nativeActorMask.size()) continue;
    bool replaced = false;
    for (uint pi = 0; pi < quiverPoses.size(); ++pi)
        if (quiverPoses[pi].actor == a) { replaced = true; break; }
    if (replaced) continue;
    for (int y = 0; y < visH; ++y)
        HdObjectDepth::protectActor(&nativeActorMask[y * visW],
            (const byte *)vs->getBasePtr(vs->xstart, y),
            &a->_quiverUnder[y * visW], &a->_quiverAfter[y * visW], visW);
}
