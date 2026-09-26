// Only the decoder runs on the worker. Queue selection, cache ownership and
// eviction stay on the engine thread, including when an actor needs the same
// frame before the worker finishes. Keep at most one decoded surface in flight.
struct HdCostumeManager::RoomPrefetch {
    Common::Array<CostumeKey> queue;
    Common::HashMap<int, bool> costumes;
    uint cursor = 0;
    int room = -1;
    CostumeKey key;
    HdDecodeJob job;
    SDL_Thread *thread = nullptr;
    SDL_atomic_t done;

    static int decode(void *data) {
        RoomPrefetch *pending = (RoomPrefetch *)data;
        pending->job.ok = hdDecodeOne(pending->job.path, pending->job.surface);
        SDL_AtomicSet(&pending->done, 1);
        return 0;
    }
    ~RoomPrefetch() {
        if (thread) SDL_WaitThread(thread, nullptr);
        job.surface.free();
    }
};

void HdCostumeManager::stopRoomPrefetch() {
    delete _roomPrefetch;
    _roomPrefetch = nullptr;
}

void HdCostumeManager::queueRoomCostume(int room, int costume) {
    if (!_enabled || !_exactFrames || !usesAsyncRoomLoading(room)) return;
    if (!_roomPrefetch) _roomPrefetch = new RoomPrefetch();
    RoomPrefetch &pending = *_roomPrefetch;
    if (pending.room != room) {
        // An in-flight decode owns its path/surface independently of this
        // queue. Let it finish; changing rooms must never join a busy worker.
        pending.queue.clear(); pending.costumes.clear(); pending.cursor = 0;
        pending.room = room;
    }
    if (pending.costumes.contains(costume)) return;
    pending.costumes[costume] = true;
    if (HdSceneVisibility::nativePaletteEffect(room, costume) ||
        (HdRemaster::state().active && HdWater::ambient(room, costume) &&
         (!ConfMan.hasKey("hd_water_shader") || ConfMan.getBool("hd_water_shader")))) return;
    Common::Array<CostumeKey> frames;
    for (auto it = _availableCostumes.begin(); it != _availableCostumes.end(); ++it)
        if (it->_key.akosId == costume && !_svgCostumes.contains(it->_key) &&
            !_textureCache.contains(it->_key)) frames.push_back(it->_key);
    Common::sort(frames.begin(), frames.end(), [](const CostumeKey &a, const CostumeKey &b) {
        return a.frame != b.frame ? a.frame < b.frame : a.akosSub < b.akosSub;
    });
    for (const auto &key : frames) pending.queue.push_back(key);
}

void HdCostumeManager::queueRoomCostumes(int room) {
    for (auto it = _akosSubs.begin(); it != _akosSubs.end(); ++it)
        for (auto owner = it->_value.begin(); owner != it->_value.end(); ++owner)
            if (*owner == room) { queueRoomCostume(room, it->_key); break; }
}

void HdCostumeManager::prefetchRoomStep(int room) {
    if (!_roomPrefetch || _borrowDepth) return;
    RoomPrefetch &pending = *_roomPrefetch;
    if (pending.thread) {
        if (!SDL_AtomicGet(&pending.done)) return;
        SDL_WaitThread(pending.thread, nullptr);
        pending.thread = nullptr;
        // A demanded frame can have reached the cache while decoding. Never
        // replace its surface: the renderer may have retained its identity.
        if (pending.job.ok && !_textureCache.contains(pending.key)) {
            TextureCacheEntry entry;
            entry.surface = pending.job.surface;
            entry.lastUsed = ++_lruCounter;
            _textureCache[pending.key] = entry;
            pending.job.surface = Graphics::Surface(); // transfer ownership
            pruneCache();
        }
        pending.job.surface.free();
    }
    if (!usesAsyncRoomLoading(room) || pending.room != room) return;
    while (pending.cursor < pending.queue.size()) {
        const CostumeKey key = pending.queue[pending.cursor++];
        if (_textureCache.contains(key)) continue;
        pending.key = key;
        pending.job.path = buildCostumePath(key.akosId, key.akosSub, key.frame);
        pending.job.ok = false;
        SDL_AtomicSet(&pending.done, 0);
        pending.thread = SDL_CreateThread(RoomPrefetch::decode, "hd-room-prefetch", &pending);
        // Failed thread creation falls back to normal on-demand loading,
        // never a synchronous room-wide batch on the presentation thread.
        return;
    }
}
