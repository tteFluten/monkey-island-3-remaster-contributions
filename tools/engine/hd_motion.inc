// Repaint between native ticks using drawing-only actor clones and scratch
// native buffers. No scripts, walking, costume animation, or sound are ticked.
bool ScummEngine::canPresentHDMotion() {
    if ((ConfMan.hasKey("hd_smooth_motion") && !ConfMan.getBool("hd_smooth_motion")) ||
        _game.id != GID_CMI || _hdScale <= 1 || isPaused() || isSmushActive() ||
        _saveLoadFlag || hdInventoryOpen() ||
        !_hdBackgroundSurface.getPixels() || !_hdCleanBackground.getPixels() || !_hdCleanValid ||
        _currentRoom == 87 || _currentRoom == 92 || _hdVerbSurfaceValid)
        return false;
    for (int i = 1; i < _numActors; ++i)
        if (_actors[i]->_visible && _actors[i]->_room == _currentRoom && _actors[i]->_layer < 0)
            return false; // Inventory/verb coin remains on the normal UI path.
    return true;
}

void ScummEngine::captureHDMotion() {
    const bool enabled = canPresentHDMotion();
    bool reset = _hdMotionClock.sample(_currentRoom, _system->getMillis(), enabled);
    if (ABS(camera._cur.x - _hdMotionCamera.x) > 160 || ABS(camera._cur.y - _hdMotionCamera.y) > 160)
        reset = true;
    _hdMotionCamera.sample(camera._cur.x, camera._cur.y, _currentRoom, reset);
    _hdMotionMoving = _hdMotionCamera.moving;
    _hdMotionActors.resize(_numActors);
    bool cannonFound = false;
    for (int i = 0; i < _numActors; ++i) {
        Actor *a = _actors[i];
        bool visible = a->_visible && a->_room == _currentRoom && a->_layer >= 0;
        _hdMotionActors[i].sample(a->getPos().x, a->getPos().y,
            visible ? a->_costume : -1, reset || !visible);
        if (visible && _hdMotionActors[i].moving) _hdMotionMoving = true;
        if (enabled && _currentRoom == 10 && visible && a->_costume == 35 &&
            playtestExactRoom(_currentRoom) && a->_quiverDraws.size() == 1) {
            const Actor::QuiverDraw &d = a->_quiverDraws[0];
            HdMotion::CannonPose pose;
            pose.cel = d.cel; pose.left = d.screenLeft; pose.top = d.screenTop;
            pose.width = d.screenWidth; pose.height = d.screenHeight;
            pose.sourceWidth = d.width; pose.sourceHeight = d.height; pose.mirror = d.mirror;
            _hdMotionCannon.sample(pose, a->_number, _playtestCommandId, reset);
            cannonFound = true;
            if (_hdMotionCannon.moving) _hdMotionMoving = true;
        }
    }
    if (!cannonFound) _hdMotionCannon = HdMotion::CannonAim();
    // Respect native camera ownership. Ego is Guybrush; scripted pans clear
    // _follows and frozen cameras must never be pulled toward the player.
    const int ego = VAR(VAR_EGO);
    const bool follow = enabled && !_cameraIsFrozen && camera._follows == ego &&
        ego > 0 && ego < _numActors && _actors[ego]->_visible &&
        _actors[ego]->_room == _currentRoom &&
        (_roomWidth > _screenWidth || _roomHeight > _screenHeight);
    if (follow) {
        const auto &track = _hdMotionActors[ego];
        const bool actorCut = ABS(track.x - _hdCameraActorX) > 160 || ABS(track.y - _hdCameraActorY) > 160;
        if (reset || actorCut || _hdFollow.actor != ego)
            _hdFollow.reset(camera._cur.x, camera._cur.y, track.y, ego, HdRemaster::milliseconds());
        _hdCameraActorX = track.x; _hdCameraActorY = track.y;
    } else _hdFollow.actor = 0;
    _hdCameraDirty = true;
    _hdCameraStageValid = false;
    _hdMotionFonts = _hdFontChars;
    if (_hdFrameCount % 120 == 0 && enabled)
        hdPrintf("HD-MOTION native interval=%ums moving=%d camera=%d", _hdMotionClock.interval, _hdMotionMoving, camera._cur.x);
}

void ScummEngine::presentHDMotion() {
    if (!canPresentHDMotion()) {
        _hdMotionClock.valid = false;
        _hdFollow.actor = 0;
        return;
    }
    if (!_hdMotionClock.valid || (!_hdMotionMoving && !_hdFollow.actor) ||
        _hdMotionClock.room != _currentRoom || _hdMotionActors.size() != (uint)_numActors)
        return;
    if (!_hdCameraDirty && !_hdMotionMoving && !_hdFollow.moving()) return;
    const double motionStarted = HdRemaster::milliseconds(), cpuBefore = HdRemaster::state().cpuWork;
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
    _hdMotionFraction = fraction;
    double drawX = _hdMotionCamera.preciseX(fraction), drawY = _hdMotionCamera.preciseY(fraction);
    if (_hdFollow.actor && !verify) {
        Common::Point low(0, 0), high(_roomWidth, _roomHeight);
        clampCameraPos(&low); clampCameraPos(&high);
        // Fixed axes retain their authored framing. Moving axes also stay
        // inside the painting, including tall-room vertical camera limits.
        if (_roomWidth <= _screenWidth) low.x = high.x = camera._cur.x;
        if (_roomHeight <= _screenHeight) low.y = high.y = camera._cur.y;
        else {
            low.y = CLIP<int>(low.y, _screenHeight / 2, _roomHeight - _screenHeight / 2);
            high.y = CLIP<int>(high.y, low.y, _roomHeight - _screenHeight / 2);
        }
        const auto &actor = _hdMotionActors[_hdFollow.actor];
        _hdFollow.step(actor.preciseX(fraction), actor.preciseY(fraction), motionStarted,
            low.x, high.x, low.y, high.y);
        drawX = _hdFollow.x.position; drawY = _hdFollow.y.position;
    }
    if (verify) { drawX = camera._cur.x; drawY = camera._cur.y; }
    _hdCameraDirty = false;
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
    auto &front = _hdMotionFront; auto &back = _hdMotionBack;
    auto &masks = _hdMotionMasks; auto &clean = _hdMotionClean; auto &valid = _hdMotionValid;
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
    auto &originals = _hdMotionOriginals; auto &sorted = _hdMotionSorted;
    originals.resize(_numActors); sorted.resize(_numActors);
    memcpy(sorted.data(), _sortedActors, _numActors * sizeof(Actor *));
    while (_hdMotionClones.size() < (uint)_numActors) _hdMotionClones.push_back(nullptr);
    for (int i = 0; i < _numActors; ++i) {
        originals[i] = _actors[i];
        // COMI uses Actor_v7, whose drawing state is entirely in Actor.
        // Clones are never animated or walked; only drawActorCostume is called.
        if (!_hdMotionClones[i]) _hdMotionClones[i] = new Actor(*originals[i]);
        else *_hdMotionClones[i] = *originals[i];
        _actors[i] = _hdMotionClones[i];
        _actors[i]->hdSetDrawPosition(Common::Point(_hdMotionActors[i].atX(fraction), _hdMotionActors[i].atY(fraction)));
        _actors[i]->_cost = originals[i]->_hdRenderCost;
        _actors[i]->_needRedraw = originals[i]->_visible;
    }
    screen.setPixels(front.data());
    if (screen.backBuf) screen.backBuf = back.data();
    _hdCleanBackground.setPixels(clean.data()); _hdCleanValid = valid.data();
    _hdInterpolating = true;
    const bool wideGpu = !verify && HdRemaster::state().active && hdAspectRatio() == 169 && _screenWidth == 864;
    camera._cur = Common::Point(HdCamera::rasterAnchor(drawX, wideGpu), HdCamera::anchor(drawY));
    cameraMoved();
    // The native raster uses an integral anchor. The backend shifts all world
    // layers together by the remaining fraction, before adding screen UI.
    _hdCameraFractionX = drawX - camera._cur.x;
    _hdCameraFractionY = drawY - camera._cur.y;
    _fullRedraw = true;
    if (wideGpu && _hdCameraStageValid && camera._cur == _hdCameraStageAnchor &&
        _hdCameraStageFront.size() == bufferSize && _hdCameraStageMasks.size() == (uint)maskSize) {
        memcpy(front.data(), _hdCameraStageFront.data(), bufferSize);
        if (screen.backBuf) memcpy(back.data(), _hdCameraStageBack.data(), bufferSize);
        memcpy(maskBuffer, _hdCameraStageMasks.data(), maskSize);
        memcpy(clean.data(), _hdCameraStageClean.data(), clean.size());
        memcpy(valid.data(), _hdCameraStageValidPixels.data(), valid.size());
        memcpy(gfxUsageBits, _hdCameraStageUsage.data(), sizeof(gfxUsageBits));
    } else if (_hdMotionStageRoom == _currentRoom && camera._cur == _hdMotionStageCamera &&
        _hdMotionStageFront.size() == bufferSize && _hdMotionStageMasks.size() == (uint)maskSize) {
        memcpy(front.data(), _hdMotionStageFront.data(), bufferSize);
        memcpy(maskBuffer, _hdMotionStageMasks.data(), maskSize);
    } else redrawBGAreas();
    if (wideGpu && (!_hdCameraStageValid || camera._cur != _hdCameraStageAnchor)) {
        _hdCameraStageFront.resize(bufferSize); _hdCameraStageMasks.resize(maskSize);
        memcpy(_hdCameraStageFront.data(), front.data(), bufferSize);
        if (screen.backBuf) {
            _hdCameraStageBack.resize(bufferSize);
            memcpy(_hdCameraStageBack.data(), back.data(), bufferSize);
        }
        memcpy(_hdCameraStageMasks.data(), maskBuffer, maskSize);
        _hdCameraStageClean.resize(clean.size()); _hdCameraStageValidPixels.resize(valid.size());
        memcpy(_hdCameraStageClean.data(), clean.data(), clean.size());
        memcpy(_hdCameraStageValidPixels.data(), valid.data(), valid.size());
        _hdCameraStageUsage.resize(ARRAYSIZE(gfxUsageBits));
        memcpy(_hdCameraStageUsage.data(), gfxUsageBits, sizeof(gfxUsageBits));
        _hdCameraStageAnchor = camera._cur; _hdCameraStageValid = true;
    }
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
        _actors[i] = originals[i];
    }
    _hdMotionDrawCamera = drawX;
    _hdMotionDrawTop = drawY - _screenHeight / 2;
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
    _hdCameraFractionX = _hdCameraFractionY = 0;
    if (verify) {
        // Compare a target-position replay to the normal compositor using the
        // restored native buffers/actors, rather than the preceding display.
        const Graphics::Surface &actualScene = HdRemaster::state().active ? HdRemaster::state().scene : _hdComposite;
        endpoint.resize(actualScene.pitch * actualScene.h);
        memcpy(endpoint.data(), actualScene.getPixels(), endpoint.size());
        _hdInterpolating = true;
        _hdFontChars = _hdMotionFonts;
        renderHDComposite();
        _hdFontChars = savedFonts;
        _hdInterpolating = false;
        Common::DumpFile replayFile, nativeFile;
        const Graphics::Surface &nativeScene = HdRemaster::state().active ? HdRemaster::state().scene : _hdComposite;
        Graphics::Surface replay = nativeScene;
        replay.setPixels(endpoint.data());
        if (replayFile.open(Common::Path(ConfMan.get("playtest_session") + "/motion-replay.png")))
            Image::writePNG(replayFile, replay);
        if (nativeFile.open(Common::Path(ConfMan.get("playtest_session") + "/motion-native.png")))
            Image::writePNG(nativeFile, nativeScene);
        unsigned int different = 0;
        const uint32 *expected = (const uint32 *)endpoint.data();
        const uint32 *actual = (const uint32 *)nativeScene.getPixels();
        for (uint i = 0; i < endpoint.size() / 4; ++i) if (expected[i] != actual[i]) ++different;
        Common::String result = ConfMan.get("playtest_session") + "/motion-check.json";
        FILE *file = fopen(result.c_str(), "w");
        if (file) { fprintf(file, "{\"different_pixels\":%u,\"pixels\":%u,\"room\":%d}\n",
                            different, endpoint.size() / 4, _currentRoom); fclose(file); }
    }
    static uint32 frames = 0, elapsed = 0, maximum = 0;
    static int samples = 0;
    if (samples < 60) {
        hdPrintf("HD-MOTION sample native=%d draw=%.3f fraction=%u interval=%u", camera._cur.x,
                 _hdMotionDrawCamera, fraction, _hdMotionClock.interval); ++samples;
    }
    HdRemaster::state().cpuMotion += HdRemaster::milliseconds() - motionStarted;
    HdRemaster::state().cpuWork = cpuBefore + HdRemaster::milliseconds() - motionStarted;
    uint32 duration = _system->getMillis() - started;
    elapsed += duration; maximum = MAX(maximum, duration);
    if (++frames == 120) {
        hdPrintf("HD-MOTION replays=120 average=%.1fms max=%ums", elapsed / 120.0, maximum);
        frames = elapsed = maximum = 0;
    }
}
