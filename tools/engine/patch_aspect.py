"""Port native widescreen presentation without replacing any room artwork."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'common/hd_aspect.h').write_bytes((here / 'hd_aspect.h').read_bytes())
    (root / 'engines/scumm/hd_aspect.inc').write_bytes((here / 'hd_aspect.inc').read_bytes())
    header = 'engines/scumm/scumm.h'
    edit(header, '#include "scumm/hd_motion.h"', '#include "common/hd_aspect.h"\n#include "scumm/hd_motion.h"')
    edit(header, '\tbool _hdFontSizeMouseDown = false;', '''\tbool _hdFontSizeMouseDown = false;
    int hdAspectRatio() const;
    bool hdInventoryOpen() const;
    void refreshHDInventoryViewport();
    void refreshHDRoomBackground();
    void configureHDViewport(bool movie = false);
    void refreshHDViewport(bool movie);
    void fadeHDPresentation();
    bool handleHDAspectEvent(const Common::Event &event);
    void drawHDAspectMenu();
    bool _hdAspectMouseDown = false;
    const Graphics::Surface *_hdBackendCursor = nullptr;''')
    # Inspection labels are authored at the original 640px screen center.
    # Translate only screen-anchored captions; overhead speech already uses
    # actor/camera coordinates and must not receive this offset a second time.
    text = 'engines/scumm/string_v7.cpp'
    edit(text, '\t\tenqueueText(msg, st.xpos, st.ypos, st.color, st.charset, (TextStyleFlags)flags);', '''        const int textX = _game.id == GID_CMI && _hdScale > 1 && !hdInventoryOpen() && !_hdInventoryInputOffset && hdAspectRatio() == 169
            ? HdAspect::centeredTextX(st.xpos, st.center, _screenWidth) : st.xpos;
        enqueueText(msg, textX, st.ypos, st.color, st.charset, (TextStyleFlags)flags);''')
    edit(text, '\t\tsubtitlePos.x = _string[0].xpos;', '''        subtitlePos.x = _string[0].xpos;
        if (_game.id == GID_CMI && _hdScale > 1 && !hdInventoryOpen() && !_hdInventoryInputOffset && hdAspectRatio() == 169 &&
            !(a && _string[0].overhead))
            subtitlePos.x = HdAspect::centeredTextX(subtitlePos.x, _string[0].center, _screenWidth);''')
    # Constructor clip rectangles are still 640px after a panorama is opened.
    # Center the original wrapping area for centered captions, preserving line
    # breaks; other text can use the current viewport without right-edge clipping.
    for clip in ('_wrappedTextClipRect', '_defaultTextClipRect'):
        before = '\t\t\tbt.rect = ' + clip + ';'
        edit(text, before, before + '''
            if (_game.id == GID_CMI && _hdScale > 1 && !hdInventoryOpen() && !_hdInventoryInputOffset && hdAspectRatio() == 169 && _screenWidth > 640) {
                if ((bt.flags & kStyleAlignCenter) && bt.xpos == _screenWidth / 2)
                    bt.rect.translate((_screenWidth - 640) / 2, 0);
                else
                    bt.rect.right += _screenWidth - 640;
            }''')

    # A scrolling viewport also needs its extra feed strip.
    edit('engines/scumm/gfx.h', 'uint16 tdirty[80 + 1];', 'uint16 tdirty[108 + 1];')
    edit('engines/scumm/gfx.h', 'uint16 bdirty[80 + 1];', 'uint16 bdirty[108 + 1];')
    edit('engines/scumm/gfx.h', 'for (int i = 0; i < 80 + 1; i++) {', 'for (uint i = 0; i < ARRAYSIZE(tdirty); i++) {')
    # Runs on both normal room entry and save restoration, before buffers/masks
    # are rebuilt by the caller. Do not run room scripts when toggling modes.
    edit('engines/scumm/room.cpp', '\t//\n\t// Find the room image data\n\t//\n\tif (_game.version == 8) {',
         '\tconfigureHDViewport();\n\n\t//\n\t// Find the room image data\n\t//\n\tif (_game.version == 8) {')
    edit('engines/scumm/camera.cpp', '\tpt->x = CLIP<int>(pt->x, minX, maxX);', '''\tif (_game.id == GID_CMI && _screenWidth == 864) {
        pt->x = HdAspect::camera(pt->x, _roomWidth, _screenWidth, minX, maxX);
    } else {
        pt->x = CLIP<int>(pt->x, minX, maxX);
    }''')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "common/file.h"', '#include "common/file.h"\n#include "common/fs.h"')
    if '#include "scumm/hd_aspect.inc"' not in (root / gfx).read_text():
        edit(gfx, 'void ScummEngine::initScreens(int b, int h) {',
             '#include "scumm/hd_aspect.inc"\n\nvoid ScummEngine::initScreens(int b, int h) {')
    # Reconcile room presentation after scripts without shrinking panoramas
    # when inventory opens; its UI is centered independently of the scene.
    edit('engines/scumm/scumm.cpp', '\t\twalkActors();\n\t\tmoveCamera();',
         '\t\trefreshHDInventoryViewport();\n\t\twalkActors();\n\t\tmoveCamera();')
    edit(gfx, '\tdrawHDFontSizeMenu();', '\tdrawHDAspectMenu();\n\tdrawHDFontSizeMenu();')
    # Save restoration can render in the same tick, before the bridge's next
    # 100 ms poll. Never sample the smaller options-book texture as a panorama.
    edit('engines/scumm/saveload.cpp', '\tsetupRoomSubBlocks();',
         '\tsetupRoomSubBlocks();\n\trefreshHDRoomBackground();')
    source = 'engines/scumm/input.cpp'
    # Preserve the font patch's complete anchor on repeat application.
    edit(source, '\tif (handleHDFontSizeEvent(event)) return;',
         '\tif (handleHDFontSizeEvent(event)) return;\n\tif (handleHDAspectEvent(event)) return;')
    edit(source, 'void ScummEngine_v8::processKeyboard(Common::KeyState lastKeyHit) {', '''void ScummEngine_v8::processKeyboard(Common::KeyState lastKeyHit) {
    if (ConfMan.hasKey("playtest_session") && _currentRoom != 92 &&
        lastKeyHit.keycode == Common::KEYCODE_o && lastKeyHit.hasFlags(0))
        lastKeyHit = Common::KeyState(Common::KEYCODE_F5, 319);''')
    # Movies keep their native 640x480 buffers; the backend crops their
    # presentation to 16:9 with uniform zoom. Release restores the movie flag for
    # completion, Escape, and decoder failure. Missing SANs return before entry.
    smush = 'engines/scumm/smush/smush_player.cpp'
    edit(smush, '\t// Check for HD video replacement', '\t_vm->refreshHDViewport(true);\n\n\t// Check for HD video replacement')
    edit(smush, '\t_vm->_gdi->_numStrips = _origNumStrips;', '\t_vm->_gdi->_numStrips = _origNumStrips;\n\t_vm->refreshHDViewport(false);')
    edit('engines/scumm/cursor.cpp', 'void ScummEngine::updateCursor() {',
         'void ScummEngine::updateCursor() {\n\t_hdBackendCursor = nullptr;')
    edit('engines/scumm/cursor.cpp', 'void ScummEngine_v7::updateCursor() {',
         'void ScummEngine_v7::updateCursor() {\n\t_hdBackendCursor = nullptr;')
    edit('engines/scumm/cursor.cpp', '''\tif (_macScreen)
\t\tmac_scaleCursor(cursor, hotspotX, hotspotY, width, height);

#ifdef USE_RGB_COLOR
\tGraphics::PixelFormat format = _system->getScreenFormat();''', '''\tif (_macScreen)
\t\tmac_scaleCursor(cursor, hotspotX, hotspotY, width, height);

#ifdef USE_RGB_COLOR
    // COMI's native cursor is indexed even when the game surface is RGBA.
\tGraphics::PixelFormat format = _game.id == GID_CMI ? Graphics::PixelFormat::createFormatCLUT8() : _system->getScreenFormat();''')

    window = 'backends/graphics/windowed.h'
    edit(window, '#include "common/rect.h"', '#include "common/rect.h"\n#include "common/config-manager.h"\n#include "common/hd_aspect.h"')
    edit(window, '\n\t\tif (getOverlayHeight()) {', '''
        // Presentation-only fit: 4x textures retain their original pixels.
        // 864 native pixels are uniformly scaled with 5 1/3 pixels of overscan
        // per side; the same rectangle is used to invert pointer coordinates.
        if (ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169 && getHeight()) {
            const int nativeWidth = getWidth() * 480 / getHeight();
            const HdAspect::Rect rect = HdAspect::game(safeArea.width(), safeArea.height(), 169, nativeWidth,
                nativeWidth >= 864 || (ConfMan.hasKey("hd_wide_background_active") && ConfMan.getBool("hd_wide_background_active")),
                ConfMan.hasKey("hd_movie_active") && ConfMan.getBool("hd_movie_active"));
            _gameDrawRect = Common::Rect(safeArea.left + rect.x, safeArea.top + rect.y,
                safeArea.left + rect.x + rect.w, safeArea.top + rect.y + rect.h);
        }

\t\tif (getOverlayHeight()) {''')
    # Block before SDL edge clamping, which otherwise activates edge objects.
    sdl = 'backends/graphics/sdl/sdl-graphics.cpp'
    # SDL applies this rectangle as a physical OS pointer confinement in
    # fullscreen, before notifyMousePosition sees any events. Fixed-width
    # rooms retain a 4:3 gameplay rectangle, but the pointer must reach all of
    # the 16:9 presentation. Keep virtual input mapping and margin rejection
    # below unchanged; this applies to every room and refreshes on resizing,
    # aspect changes and GUI transitions through notifyActiveAreaChanged.
    edit(sdl, '\t_window->setMouseRect(_activeArea.drawRect);', '''    const bool widePointer = !_overlayInGUI && ConfMan.hasKey("playtest_session") &&
        ConfMan.getInt("hd_aspect_ratio") == 169;
    _window->setMouseRect(widePointer ? Common::Rect(_windowWidth, _windowHeight) : _activeArea.drawRect);''')
    edit(sdl, '\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);', '''\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);
    if (ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169 &&
        !_overlayInGUI && !_activeArea.drawRect.contains(mouse)) {
        _cursorLastInActiveArea = false;
        setMousePosition(mouse.x, mouse.y);
        showSystemMouseCursor(false);
        return false;
    }''')
    edit(sdl, '\tshowSystemMouseCursor(showCursor);\n\n\treturn WindowedGraphicsManager::showMouse(visible);', '''    if (ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169 && !_overlayInGUI)
        showCursor = false;
\tshowSystemMouseCursor(showCursor);

\treturn WindowedGraphicsManager::showMouse(visible);''')
    events = 'backends/events/sdl/sdl-events.h'
    edit(events, '\tint _mouseX;', '\tHdAspect::Buttons _hdAspectButtons;\n\tint _mouseX;')
    edit('backends/events/sdl/sdl-common-events.cpp', '\t\treturn _graphicsManager->notifyMousePosition(event.mouse);', '''        bool accepted = _graphicsManager->notifyMousePosition(event.mouse);
        if (ConfMan.hasKey("playtest_session")) {
            const unsigned down = event.type == Common::EVENT_LBUTTONDOWN ? 1 : event.type == Common::EVENT_RBUTTONDOWN ? 2 : event.type == Common::EVENT_MBUTTONDOWN ? 4 : 0;
            const unsigned up = event.type == Common::EVENT_LBUTTONUP ? 1 : event.type == Common::EVENT_RBUTTONUP ? 2 : event.type == Common::EVENT_MBUTTONUP ? 4 : 0;
            int mx = event.mouse.x, my = event.mouse.y;
            accepted = _hdAspectButtons.accept(accepted, down, up, mx, my);
            event.mouse = Common::Point(mx, my);
            if (ConfMan.hasKey("hd_aspect_test_input") && ConfMan.getBool("hd_aspect_test_input") && (down || up))
                warning("HD-ASPECT input %s type=%d game=(%d,%d)", accepted ? "accepted" : "blocked", event.type, mx, my);
        }
        return accepted;''')
    # The hardware presentation cursor must not be clipped to the 4:3 center.
    gl = 'backends/graphics/opengl/opengl-graphics.cpp'
    edit(gl, '''\t// HD cursor scaling: auto-detect from game screen size
\tif (_gameScreen && _gameScreen->getWidth() > 640) {
\t\tint hdScale = _gameScreen->getWidth() / 640;''', '''\t// HD RGBA sprites already contain the asset scale. Native indexed
    // cursors still need it, measured vertically for horizontal panoramas.
    const bool wideHD = ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169;
\tif (_gameScreen && _gameScreen->getWidth() > 640 && !wideHD) {
\t\tint hdScale = _gameScreen->getWidth() / 640;''')
    edit(gl, '''\t_cursorHeightScaled   = fracToDouble(cursorHeight       * screenScaleFactorY);
\t}''', '''\t_cursorHeightScaled   = fracToDouble(cursorHeight       * screenScaleFactorY);
\t}
    // Include native cursor asset scaling in every recalculation, including
    // resize/fullscreen. HD RGBA sprites have already been scaled once.
    if (_gameScreen && !_overlayVisible && _cursor->getFormat().bytesPerPixel == 1 &&
        ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169) {
        const int scale = MAX<int>(1, _gameScreen->getHeight() / 480);
        _cursorHotspotXScaled *= scale;
        _cursorHotspotYScaled *= scale;
        _cursorWidthScaled *= scale;
        _cursorHeightScaled *= scale;
    }''')
    edit(gl, '\t\tif (inputFormat.bytesPerPixel != 1)\n\t\t\tinputFormat = Graphics::PixelFormat::createFormatCLUT8();', '''        // Widescreen COMI supplies the actual format for both native indexed
        // cursors and HD RGBA sprites. Retain the old workaround otherwise.
\t\tif (inputFormat.bytesPerPixel != 1 && !(ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169))
\t\t\tinputFormat = Graphics::PixelFormat::createFormatCLUT8();''')
    edit(gl, 'void OpenGLGraphicsManager::renderCursor() {\n\tif (!_cursorVisible)\n\t\treturn;', '''void OpenGLGraphicsManager::renderCursor() {
\tif (!_cursorVisible)
\t\treturn;
    const bool wideCursor = !_overlayVisible && ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169;
    if (wideCursor) _targetBuffer->enableScissorTest(false);''')
    edit(gl, '\t\t\t\t\t\t   _cursorWidthScaled, _cursorHeightScaled);\n}\n\nvoid OpenGLGraphicsManager::updateScreen()',
         '\t\t\t\t\t\t   _cursorWidthScaled, _cursorHeightScaled);\n    if (wideCursor) _targetBuffer->enableScissorTest(true);\n}\n\nvoid OpenGLGraphicsManager::updateScreen()')
    # A mode change updates the window ratio once; ordinary room transitions
    # retain the user's resized window. Fullscreen is never resized.
    header = root / 'backends/graphics/sdl/sdl-graphics.h'
    if 'int _hdWindowAspect = 0;' not in header.read_text():
        edit('backends/graphics/sdl/sdl-graphics.h', '\tbool _allowWindowSizeReset;', '\tbool _allowWindowSizeReset;\n\tint _hdWindowAspect = 0;')
    edit(sdl, '\t// width *=3;\n\t// height *=3;', '''    if (ConfMan.hasKey("playtest_session")) {
        const int aspect = ConfMan.hasKey("hd_aspect_ratio") ? HdAspect::preference(ConfMan.getInt("hd_aspect_ratio")) : 43;
        if (_hdWindowAspect && aspect != _hdWindowAspect && _window->getSDLWindow() &&
            !(flags & (SDL_WINDOW_FULLSCREEN | SDL_WINDOW_FULLSCREEN_DESKTOP | SDL_WINDOW_MAXIMIZED))) {
            int currentWidth, currentHeight;
            SDL_GetWindowSize(_window->getSDLWindow(), &currentWidth, &currentHeight);
            SDL_SetWindowSize(_window->getSDLWindow(), currentWidth,
                currentWidth * (aspect == 169 ? 9 : 3) / (aspect == 169 ? 16 : 4));
        }
        _hdWindowAspect = aspect;
    }''')
