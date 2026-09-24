// Repaint between native ticks using drawing-only actor clones and scratch
// native buffers. No scripts, walking, costume animation, or sound are ticked.
bool ScummEngine::canPresentHDMotion() {
    if ((ConfMan.hasKey("hd_smooth_motion") && !ConfMan.getBool("hd_smooth_motion")) ||
        _game.id != GID_CMI || _hdScale <= 1 || isPaused() || isSmushActive() ||
        _saveLoadFlag || vm.cutSceneStackPointer || _userPut <= 0 || _haveMsg ||
        _roomWidth <= _screenWidth || _roomHeight != _screenHeight ||
        !_hdBackgroundSurface.getPixels() || !_hdCleanBackground.getPixels() || !_hdCleanValid ||
        _currentRoom == 87 || _currentRoom == 92 || _hdVerbSurfaceValid)
        return false;
    for (const auto &glyph : _hdFontChars) if (glyph.dialogue) return false;
    for (const auto &glyph : _hdMotionFonts) if (glyph.dialogue) return false;
    for (int i = 1; i < _numActors; ++i)
        if (_actors[i]->_visible && _actors[i]->_room == _currentRoom && _actors[i]->_layer < 0)
            return false; // Inventory/verb coin remains on the normal UI path.
    return true;
}

void ScummEngine::captureHDMotion() {
    _hdMotionPresented = false;
    const bool enabled = canPresentHDMotion();
    bool reset = _hdMotionClock.sample(_currentRoom, _system->getMillis(), enabled);
    if (ABS(camera._cur.x - _hdMotionCamera.x) > 160 || ABS(camera._cur.y - _hdMotionCamera.y) > 160)
        reset = true;
    _hdMotionCamera.sample(camera._cur.x, camera._cur.y, _currentRoom, reset);
    _hdMotionMoving = _hdMotionCamera.moving;
    _hdMotionActors.resize(_numActors);
    for (int i = 0; i < _numActors; ++i) {
        Actor *a = _actors[i];
        bool visible = a->_visible && a->_room == _currentRoom && a->_layer >= 0;
        _hdMotionActors[i].sample(a->getPos().x, a->getPos().y,
            visible ? a->_costume : -1, reset || !visible);
        if (visible && _hdMotionActors[i].moving) _hdMotionMoving = true;
    }
    _hdMotionFonts = _hdFontChars;
    if (_hdFrameCount % 120 == 0 && enabled)
        hdPrintf("HD-MOTION native interval=%ums moving=%d camera=%d", _hdMotionClock.interval, _hdMotionMoving, camera._cur.x);
}

void ScummEngine::presentHDMotion() {
    if (!_hdMotionClock.valid || !_hdMotionMoving || !canPresentHDMotion() ||
        _hdMotionClock.room != _currentRoom || _hdMotionActors.size() != (uint)_numActors)
        return;
    const uint32 started = _system->getMillis();
    unsigned int fraction = _hdMotionClock.fraction(started);
    bool verify = false;
    Common::Array<byte> endpoint;
    if (getenv("MI3_ENGINE_TEST_INPUT") && ConfMan.hasKey("playtest_session")) {
        Common::String request = ConfMan.get("playtest_session") + "/motion-check";
        FILE *file = fopen(request.c_str(), "r");
        if (file) {
            fclose(file); remove(request.c_str()); verify = true; fraction = 1024;
        }
    }
    // Scratch copies isolate hit testing, saves, script coordinates, masks and
    // dirty-strip bookkeeping from intermediate display positions.
    VirtScreen &screen = _virtscr[kMainVirtScreen];
    const VirtScreen savedScreen = screen;
    const auto savedCamera = camera;
    const int savedStart = _screenStartStrip, savedEnd = _screenEndStrip, savedTop = _screenTop;
    const bool savedFull = _fullRedraw, savedBg = _bgNeedsRedraw;
    const Graphics::Surface savedClean = _hdCleanBackground;
    byte *savedValid = _hdCleanValid;
    const auto savedFonts = _hdFontChars;
    Common::Array<byte> front, back, masks, clean, valid;
    const uint bufferSize = getResourceSize(rtBuffer, kMainVirtScreen + 1);
    front.resize(bufferSize); memcpy(front.data(), screen.getBasePtr(0, 0), bufferSize);
    if (screen.backBuf) { back.resize(bufferSize); memcpy(back.data(), screen.backBuf, bufferSize); }
    const int maskSize = getResourceSize(rtBuffer, 9);
    byte *maskBuffer = getResourceAddress(rtBuffer, 9);
    if (!maskBuffer || maskSize <= 0) return;
    masks.resize(maskSize); memcpy(masks.data(), maskBuffer, maskSize);
    clean.resize(savedClean.pitch * savedClean.h);
    memcpy(clean.data(), savedClean.getPixels(), clean.size());
    valid.resize(_hdCleanValidSize); memcpy(valid.data(), savedValid, valid.size());
    uint32 savedUsage[ARRAYSIZE(gfxUsageBits)];
    memcpy(savedUsage, gfxUsageBits, sizeof(savedUsage));
    Common::Array<Actor *> originals, sorted;
    originals.resize(_numActors); sorted.resize(_numActors);
    memcpy(sorted.data(), _sortedActors, _numActors * sizeof(Actor *));
    for (int i = 0; i < _numActors; ++i) {
        originals[i] = _actors[i];
        // COMI uses Actor_v7, whose drawing state is entirely in Actor.
        // Clones are never animated or walked; only drawActorCostume is called.
        _actors[i] = new Actor(*originals[i]);
        _actors[i]->hdSetDrawPosition(Common::Point(_hdMotionActors[i].atX(fraction), _hdMotionActors[i].atY(fraction)));
        _actors[i]->_cost = originals[i]->_hdRenderCost;
        _actors[i]->_needRedraw = originals[i]->_visible;
    }
    screen.setPixels(front.data());
    if (screen.backBuf) screen.backBuf = back.data();
    _hdCleanBackground.setPixels(clean.data()); _hdCleanValid = valid.data();
    _hdInterpolating = true;
    camera._cur = Common::Point(_hdMotionCamera.atX(fraction), _hdMotionCamera.atY(fraction));
    cameraMoved();
    _fullRedraw = true;
    redrawBGAreas();
    // Preserve COMI's original (non-stable) depth sort, including equal depths.
    int count = 0;
    for (int i = 1; i < _numActors; ++i)
        if (_actors[i]->_layer >= 0 && _actors[i]->isInCurrentRoom()) _sortedActors[count++] = _actors[i];
    for (int j = 0; j < count; ++j)
        for (int i = 0; i < count; ++i)
            if (_sortedActors[j]->getPos().y - _sortedActors[j]->_layer * 2000 <
                _sortedActors[i]->getPos().y - _sortedActors[i]->_layer * 2000)
                SWAP(_sortedActors[i], _sortedActors[j]);
    for (int i = 0; i < count; ++i)
        if (_sortedActors[i]->_costume) _sortedActors[i]->drawActorCostume();
    _hdFontChars = _hdMotionFonts;
    renderHDComposite();
    // All simulation-visible data is restored before polling the next input.
    for (int i = 0; i < _numActors; ++i) {
        delete _actors[i]; _actors[i] = originals[i];
    }
    _hdMotionDrawCamera = camera._cur.x;
    _hdMotionPresented = true;
    memcpy(_sortedActors, sorted.data(), _numActors * sizeof(Actor *));
    screen = savedScreen; camera = savedCamera;
    _screenStartStrip = savedStart; _screenEndStrip = savedEnd; _screenTop = savedTop;
    _fullRedraw = savedFull; _bgNeedsRedraw = savedBg;
    _hdCleanBackground = savedClean; _hdCleanValid = savedValid;
    _hdFontChars = savedFonts;
    memcpy(maskBuffer, masks.data(), maskSize);
    memcpy(gfxUsageBits, savedUsage, sizeof(savedUsage));
    _hdInterpolating = false;
    if (verify) {
        // Compare a target-position replay to the normal compositor using the
        // restored native buffers/actors, rather than the preceding display.
        endpoint.resize(_hdComposite.pitch * _hdComposite.h);
        memcpy(endpoint.data(), _hdComposite.getPixels(), endpoint.size());
        _hdInterpolating = true;
        _hdFontChars = _hdMotionFonts;
        renderHDComposite();
        _hdFontChars = savedFonts;
        _hdInterpolating = false;
        Common::DumpFile replayFile, nativeFile;
        Graphics::Surface replay = _hdComposite;
        replay.setPixels(endpoint.data());
        if (replayFile.open(Common::Path(ConfMan.get("playtest_session") + "/motion-replay.png")))
            Image::writePNG(replayFile, replay);
        if (nativeFile.open(Common::Path(ConfMan.get("playtest_session") + "/motion-native.png")))
            Image::writePNG(nativeFile, _hdComposite);
        unsigned int different = 0;
        const uint32 *expected = (const uint32 *)endpoint.data();
        const uint32 *actual = (const uint32 *)_hdComposite.getPixels();
        for (uint i = 0; i < endpoint.size() / 4; ++i) if (expected[i] != actual[i]) ++different;
        Common::String result = ConfMan.get("playtest_session") + "/motion-check.json";
        FILE *file = fopen(result.c_str(), "w");
        if (file) { fprintf(file, "{\"different_pixels\":%u,\"pixels\":%u,\"room\":%d}\n",
                            different, endpoint.size() / 4, _currentRoom); fclose(file); }
    }
    static uint32 frames = 0, elapsed = 0, maximum = 0;
    static int samples = 0;
    if (samples < 60) {
        hdPrintf("HD-MOTION sample native=%d draw=%d fraction=%u interval=%u", camera._cur.x,
                 _hdMotionDrawCamera, fraction, _hdMotionClock.interval); ++samples;
    }
    uint32 duration = _system->getMillis() - started;
    elapsed += duration; maximum = MAX(maximum, duration);
    if (++frames == 120) {
        hdPrintf("HD-MOTION replays=120 average=%.1fms max=%ums", elapsed / 120.0, maximum);
        frames = elapsed = maximum = 0;
    }
}
