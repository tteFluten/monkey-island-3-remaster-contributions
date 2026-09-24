// The actor's native pixels identify its used palette slots. Restrict them to
// costume colors so floor shadows/background pixels are not mistaken for skin
// or clothing. Palette state is already serialized by the original engine.
auto actorLighting = [&](Actor *a) {
    HdActorLighting::Tint neutral;
    if (_game.id != GID_CMI || !a->_costume) return neutral;
    const byte *costume = getResourceAddress(rtCostume, a->_costume);
    if (!costume) return neutral;
    const byte *akpl = findResourceData(MKTAG('A','K','P','L'), costume);
    if (!akpl) return neutral;
    unsigned int usage[256] = {};
    byte mapping[256] = {};
    int colors = MIN(256, getResourceDataSize(akpl));
    for (int i = 0; i < colors; ++i) {
        int index = a->hdPaletteColor(i);
        if (index == 255) index = akpl[i];
        mapping[i] = index;
        // Low palette indices select native shadow operations, not RGB paint.
        if (index >= 16 && index < 255)
            usage[index] = a->_hdPaletteUsage[index];
    }
    const unsigned int *stableUsage = a->_hdLightingSamples.update(_currentRoom, a->_costume, mapping, usage);
    const HdActorLighting::Tint native = HdActorLighting::fromPalette(_darkenPalette, _currentPalette, stableUsage);
    const HdActorLighting::Tint applied = native.enhanced(_currentRoom == 9);
    if (_hdFrameCount % 30 == 0)
        hdPrintf("LIGHTING actor=%d position=%d,%d native=%d,%d,%d applied=%d,%d,%d", a->_number,
                 a->getPos().x, a->getPos().y, native.channel[0], native.channel[1], native.channel[2],
                 applied.channel[0], applied.channel[1], applied.channel[2]);
    return applied;
};
