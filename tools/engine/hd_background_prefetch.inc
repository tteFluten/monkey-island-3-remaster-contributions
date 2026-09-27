// Called before outgoing room scripts/fades, and by save/hot-reload loads.
// Room numbers provide a small speculative lookahead, not a navigation map.
void HDAssetManager::prefetchBackground(int room) {
    if (_hdPath.empty() || room <= 0 || !ConfMan.hasKey("playtest_session")) return;
    auto &cache = HdBackground::cache();
    cache.beginRoom(room);
    auto requestRoom = [&](int candidate) {
        if (candidate <= 0 || candidate == 1 || !_bgFiles.contains(candidate)) return;
        cache.request(_bgFiles[candidate]);
        const Common::String wide = _hdPath + Common::String::format("/widescreen/bg_%04d.png", candidate);
        if (Common::FSNode(Common::Path(wide)).exists()) cache.request(wide);
    };
    requestRoom(room); // The actual destination always precedes speculation.
    int before = -1, after = -1;
    for (auto it = _bgFiles.begin(); it != _bgFiles.end(); ++it) {
        const int candidate = it->_key;
        if (candidate < room && candidate > before) before = candidate;
        if (candidate > room && (after < 0 || candidate < after)) after = candidate;
    }
    requestRoom(after); requestRoom(before);
    cache.step();
}
