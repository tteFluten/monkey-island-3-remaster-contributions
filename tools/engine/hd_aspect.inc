// Included in gfx.cpp. Changes display buffers only, never re-enters a room.
int ScummEngine::hdAspectRatio() const {
    return ConfMan.hasKey("hd_aspect_ratio") ? HdAspect::preference(ConfMan.getInt("hd_aspect_ratio")) : 169;
}

void ScummEngine::publishHDWideBackground(bool movie) {
    if (_game.id != GID_CMI || !ConfMan.hasKey("playtest_session")) return;
    if (movie || isSmushActive()) {
        HdRemaster::state().active = false;
        HdRemaster::state().entryRoom = 0; // Movies own their presentation.
    }
    HdRemaster::state().wideRoom = _currentRoom;
    Common::String path;
    if (!movie && !isSmushActive() && _roomWidth == 640 &&
        _roomHeight == 480 && hdAspectRatio() == 169)
        path = ConfMan.get("hd_path") + Common::String::format("/widescreen/bg_%04d.png", _currentRoom);
    ConfMan.set("hd_wide_background", path, Common::ConfigManager::kTransientDomain);
    ConfMan.setInt("hd_wide_background_revision", _playtestCommandId,
        Common::ConfigManager::kTransientDomain);
}

bool ScummEngine::hdInventoryOpen() const {
    // COMI normally draws its inventory background as a blast object; some
    // overlay paths use a verb instead. Inspect native visibility, not pixels.
    const ScummEngine_v6 *v6 = static_cast<const ScummEngine_v6 *>(this);
    for (int i = 0; i < v6->getBlastCount(); ++i)
        if (v6->getBlastObject(i).number == 114) return true;
    for (int i = 0; i < _numVerbs; ++i)
        if (_verbs[i].hd_obj_nr == 114 && _verbs[i].curmode && !_verbs[i].saveid)
            return true;
    return false;
}

void ScummEngine::refreshHDInventoryViewport() {
    if (_game.id != GID_CMI || !ConfMan.hasKey("playtest_session") || isSmushActive()) return;
    const int width = HdAspect::viewport(hdAspectRatio(), _roomWidth, _roomHeight);
    if (width != _screenWidth) refreshHDViewport(false);
}

void ScummEngine::configureHDViewport(bool movie) {
    if (_game.id != GID_CMI || !ConfMan.hasKey("playtest_session")) return;
    const bool previousMovie = ConfMan.hasKey("hd_movie_active") && ConfMan.getBool("hd_movie_active");
    ConfMan.setBool("hd_movie_active", movie, Common::ConfigManager::kTransientDomain);
    publishHDWideBackground(movie);
    auto &presentation = HdRemaster::state();
    if (previousMovie && !movie && presentation.available &&
        (!ConfMan.hasKey("hd_gpu_effects") || ConfMan.getBool("hd_gpu_effects"))) {
        // Arm, but do not start, the fade until the next completed scene.
        // A following movie leaves it pending; returning to this same room
        // must rebuild its composition before the backend reveals it.
        presentation.movieFadePending = true;
        if (_currentRoom != 1 && _currentRoom != 92 && _hdBackgroundSurface.getPixels()) {
            presentation.entryRoom = _currentRoom;
            presentation.entryPrepared = presentation.entryComposed = false;
            presentation.active = presentation.ui = false;
        }
    }
    const int width = movie ? 640 : HdAspect::viewport(hdAspectRatio(), _roomWidth, _roomHeight);
    _hdMotionClock.valid = _hdMotionPresented = _hdMotionMoving = false;
    _hdPresentedCursor = Common::Rect();
    _hdBackendCursor = nullptr;
    if (_screenWidth == width) {
        // Fixed rooms and movies both use 640 native pixels. Refresh the
        // backend rectangle even when no framebuffer allocation changes.
        if (previousMovie != movie) {
            _system->beginGFXTransaction();
            _system->endGFXTransaction();
            _fullRedraw = _completeScreenRedraw = true;
        }
        return;
    }
    _screenWidth = width;
    initScreens(0, _screenHeight);
    _textSurface.free();
    _textSurface.create(width * _textSurfaceMultiplier, _screenHeight * _textSurfaceMultiplier,
                        Graphics::PixelFormat::createFormatCLUT8());
    clearTextSurface();
    free(_compositeBuf);
    _compositeBuf = (byte *)calloc(width * _textSurfaceMultiplier * _screenHeight * _textSurfaceMultiplier,
                                   _outputPixelFormat.bytesPerPixel);
    _hdComposite.free();
    _hdCleanBackground.free();
    free(_hdCleanValid);
    _hdCleanValid = nullptr;
    _hdCleanValidSize = 0;
    _hdFontChars.clear();
    _hdMotionFonts.clear();
    const Graphics::PixelFormat format = _system->getScreenFormat();
    _system->beginGFXTransaction();
    _system->initSize(width * MAX(1, _hdScale), _screenHeight * MAX(1, _hdScale), &format);
    _system->endGFXTransaction();
    _fullRedraw = _completeScreenRedraw = true;
}

void ScummEngine::fadeHDPresentation() {
    auto &presentation = HdRemaster::state();
    if (!presentation.available || !ConfMan.hasKey("playtest_session") ||
        (ConfMan.hasKey("hd_gpu_effects") && !ConfMan.getBool("hd_gpu_effects"))) return;
    // Keep the outgoing texture and its geometry until completely black.
    // Poll input without advancing scripts, decoding or rebuilding the scene.
    presentation.exitFadeActive = true;
    const double started = HdRemaster::milliseconds();
    do {
        parseEvents();
        const float progress = CLIP(float((HdRemaster::milliseconds() - started) / 1000.0), 0.0f, 1.0f);
        presentation.exitFadeOpacity = progress * progress * (3.0f - 2.0f * progress);
        _system->updateScreen();
        if (progress >= 1.0f) break;
        _system->delayMillis(10);
    } while (!shouldQuit());
    presentation.exitFadeActive = false;
    // The first completed destination frame releases this black hold.
    presentation.exitFadeOpacity = 1.0f;
    presentation.movieFadePending = true;
}

void ScummEngine::refreshHDViewport(bool movie) {
    const int previous = _screenWidth;
    configureHDViewport(movie);
    if (previous != _screenWidth && _currentRoom > 0) {
        initBGBuffers(_roomHeight);
        cameraMoved();
        _fullRedraw = _completeScreenRedraw = true;
    }
}

// Players get 16:9 only. hd_aspect_ratio=43 in the config (or the playtest
// "aspect" command) remains available to isolated checks.
bool ScummEngine::handleHDAspectEvent(const Common::Event &) {
    return false;
}

void ScummEngine::drawHDAspectMenu() {
    publishHDWideBackground();
}
