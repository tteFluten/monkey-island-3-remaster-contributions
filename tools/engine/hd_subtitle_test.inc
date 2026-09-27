// Deterministic layout probes, available only in isolated engine test sessions.
// No speech scripts, player preferences or saves are changed by this hook.
if (_hdSubtitleProbeEnabled && ConfMan.hasKey("playtest_session")) {
    Common::File probe;
    if (probe.open(Common::FSNode(Common::Path(ConfMan.get("playtest_session") + "/subtitle-probe.bin")))) {
        const int x = probe.readSint16LE(), y = probe.readSint16LE();
        const int flags = probe.readUint16LE(), font = probe.readUint16LE();
        const Common::String text = probe.readLine();
        if (font < 5 && !text.empty() && text.size() < 200)
            enqueueText((const byte *)text.c_str(), x, y, 15, font,
                (TextStyleFlags)flags, false, true);
    }
}
