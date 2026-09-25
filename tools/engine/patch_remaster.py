"""Layered GPU effects and fixed-resolution presentation for the COMI remaster."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_remaster.h', 'hd_color_grade.h'):
        (root / 'common' / name).write_bytes((here / name).read_bytes())
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '\tint hdW, hdH;', '''    auto &remaster = HdRemaster::state();
    remaster.active = remaster.available && (!ConfMan.hasKey("hd_gpu_effects") || ConfMan.getBool("hd_gpu_effects")) &&
        _game.id == GID_CMI && _currentRoom != 87 && _currentRoom != 92 && !hdInventoryOpen() && !_hdVerbSurfaceValid;
    remaster.ui = remaster.dof = false;
    remaster.background = &_hdBackgroundSurface;
    remaster.viewportWidth = _screenWidth; remaster.viewportHeight = _screenHeight;
    remaster.scale = _hdScale; remaster.revision = _playtestCommandId;
\tint hdW, hdH;''')
    edit(gfx, 'int drawY = actorPos.y - a->getElevation();',
         'int drawY = actorPos.y - a->getElevation() - _screenTop;')
    # Vertical camera offset belongs in both the painting and native reference.
    edit(gfx, '\tint srcBgX = MIN(camX, MAX(0, _hdBackgroundSurface.w - hdW));', '''\tint srcBgX = MIN(camX, MAX(0, _hdBackgroundSurface.w - hdW));
    const int srcBgY = CLIP(_screenTop * scale, 0, MAX(0, _hdBackgroundSurface.h - hdH));
    remaster.backgroundX = srcBgX; remaster.backgroundY = srcBgY;''')
    edit(gfx, '_hdBackgroundSurface.getBasePtr(srcBgX, y)', '_hdBackgroundSurface.getBasePtr(srcBgX, y + srcBgY)')
    edit(gfx, '\trenderHDDepthOfField(srcBgX, visW, visH);', '''    // RGB remains the unblurred CPU reference; alpha carries foreground
    // opacity so the shader can replace only the surviving background light.
    if (remaster.active) {
        uint32 *pixels = (uint32 *)_hdComposite.getPixels();
        for (int i = 0; i < hdW * hdH; ++i) pixels[i] &= 0x00ffffff;
    }
\trenderHDDepthOfField(srcBgX, visW, visH);''')
    edit(gfx, '_hdBackgroundSurface.getBasePtr(bgRX, maskY)', '_hdBackgroundSurface.getBasePtr(bgRX, MIN(maskY + srcBgY, (int)_hdBackgroundSurface.h - 1))')
    edit(gfx, 'bgR | (bgG << 8) | (bgB << 16) | (0xFF << 24));',
         'bgR | (bgG << 8) | (bgB << 16) | (remaster.active ? 0 : 0xff000000u));')
    edit(gfx, '// Fully opaque HD pixel: overwrite composite.\n\t\t\t\t\t\tdstRow[ox] = pix;',
         '// Fully opaque HD pixel: overwrite composite.\n\t\t\t\t\t\tdstRow[ox] = pix | 0xff000000u;')
    edit(gfx, '(((sb * alpha + db * (255 - alpha)) / 255) << 16) |\n\t\t\t\t\t\t\t(0xFF << 24);',
         '(((sb * alpha + db * (255 - alpha)) / 255) << 16) |\n                            (HdRemaster::opacity(alpha, dst >> 24) << 24);')
    edit(gfx, 'void ScummEngine::hdPrintf(const char* fmt, ...) {', '''void ScummEngine::hdPrintf(const char* fmt, ...) {
    if (!ConfMan.hasKey("hd_trace") || !ConfMan.getBool("hd_trace")) return;''')
    # Avoid showing the transparent UI staging surface via the software cursor.
    edit('engines/scumm/hd_cursor_present.inc', 'if (hdAspectRatio() == 169) {',
         'if (hdAspectRatio() == 169 || HdRemaster::state().active) {')
    # Preserve alpha on antialiased UI edges (RGB is premultiplied over clear).
    edit('engines/scumm/dialogue_font.cpp', 'dest.format.ARGBToColor(255,',
         'dest.format.ARGBToColor(a + (da * (255 - a) + 127) / 255,')
    edit('engines/scumm/hd_font_manager.cpp', 'byte out_b = (b * a + db * inv) / 255;\n\t\t\t\t\t*dPix = (0xFF << dest.format.aShift)',
         'byte out_b = (b * a + db * inv) / 255;\n\t\t\t\t\t*dPix = ((a + (((d >> dest.format.aShift) & 255) * inv + 127) / 255) << dest.format.aShift)')
    # Actual backend cursor format must be honored in GPU 4:3 mode too.
    gl = 'backends/graphics/opengl/opengl-graphics.cpp'
    edit(gl, '#include "common/hd_color_grade.h"', '#include "common/hd_color_grade.h"\n#include "common/hd_remaster.h"\n#include "graphics/opengl/shader.h"\n#include "backends/graphics/opengl/pipelines/shader.h"')
    edit(gl, 'namespace OpenGL {', 'namespace OpenGL {\n\n#include "hd_remaster_gl.inc"')
    (root / 'backends/graphics/opengl/hd_remaster_gl.inc').write_bytes((here / 'hd_remaster_gl.inc').read_bytes())
    edit(gl, 'void OpenGLGraphicsManager::updateScreen() {', '''void OpenGLGraphicsManager::updateScreen() {
    if (ConfMan.hasKey("playtest_session") && _pipeline) hdRemasterGL().initialize();''')
    edit(gl, '\tif (_gameScreen) {\n\t\t_pipeline->drawTexture(_gameScreen->getGLTexture(), _gameDrawRect.left, _gameDrawRect.top, _gameDrawRect.width(), _gameDrawRect.height());', '''\tif (_gameScreen) {
        if (!hdRemasterGL().draw(_pipeline, _targetBuffer, _gameScreen, _hdWideBackground,
                _gameDrawRect, _windowWidth, _windowHeight, _overlayVisible))
\t\t_pipeline->drawTexture(_gameScreen->getGLTexture(), _gameDrawRect.left, _gameDrawRect.top, _gameDrawRect.width(), _gameDrawRect.height());''')
    edit(gl, 'void OpenGLGraphicsManager::notifyContextDestroy() {',
         'void OpenGLGraphicsManager::notifyContextDestroy() {\n    hdRemasterGL().destroy();')
    edit(gl, 'OpenGLGraphicsManager::~OpenGLGraphicsManager() {',
         'OpenGLGraphicsManager::~OpenGLGraphicsManager() {\n    hdRemasterGL().destroy();')
    edit(gl, '\t// Update changes to textures.', '\thdRemasterGL().beginFrame();\n\t// Update changes to textures.')
    edit(gl, '\trefreshScreen();\n', '\thdRemasterGL().endFrame();\n\trefreshScreen();\n')
    # Reuse interpolation scratch storage and clones for the engine lifetime.
    edit('engines/scumm/scumm.h', '    int _hdMotionDrawCamera = 0;', '''    int _hdMotionDrawCamera = 0, _hdMotionDrawTop = 0;
    Common::Array<byte> _hdMotionFront, _hdMotionBack, _hdMotionMasks, _hdMotionClean, _hdMotionValid;
    Common::Array<Actor *> _hdMotionClones, _hdMotionOriginals, _hdMotionSorted;''')
    edit('engines/scumm/scumm.cpp', 'ScummEngine::~ScummEngine() {',
         'ScummEngine::~ScummEngine() {\n    for (auto *clone : _hdMotionClones) delete clone;')
    edit('engines/scumm/input.cpp', '\t\t_virtualMouse.y += _screenTop;',
         '\t\t_virtualMouse.y += ((_hdMotionPresented && _hdMotionClock.room == _currentRoom) ? _hdMotionDrawTop : _screenTop);')
    # Rebuild the clean native reference for vertical/fixed rooms as well.
    edit('engines/scumm/scumm.cpp', '_roomWidth > _screenWidth && _currentRoom != 92)', '/* Fixed, panoramic, and vertical HD rooms. */ _currentRoom != 92)')
    # Disable stale layering as soon as a movie replaces the game surface.
    edit('engines/scumm/hd_aspect.inc', '    if (movie || isSmushActive()) HdRemaster::state().active = false;',
         '    if (movie || isSmushActive()) HdRemaster::state().active = false;')
    manager = 'engines/scumm/hd_costume_manager'
    edit(manager + '.h', 'int svgWidth = 0, int svgHeight = 0);', 'int svgWidth = 0, int svgHeight = 0, bool borrowed = false);')
    edit(manager + '.h', '\tvoid pruneCache();', '''\tvoid pruneCache();
    int _borrowDepth = 0;
    Common::Array<Graphics::Surface> _retiredTextures;
public:
    void beginBorrow() { ++_borrowDepth; }
    void endBorrow() {
        if (--_borrowDepth) return;
        for (auto &surface : _retiredTextures) surface.free();
        _retiredTextures.clear(); pruneCache();
    }
private:''')
    edit(manager + '.cpp', 'Graphics::Surface &dest, int svgWidth, int svgHeight) {',
         'Graphics::Surface &dest, int svgWidth, int svgHeight, bool borrowed) {')
    edit(manager + '.cpp', '\t\t\tcacheIt->_value.surface.free();',
         '\t\t\tif (_borrowDepth) _retiredTextures.push_back(cacheIt->_value.surface);\n            else cacheIt->_value.surface.free();')
    edit(manager + '.cpp', '\t\t\tdest.copyFrom(cacheIt->_value.surface);',
         '\t\t\tif (borrowed) dest = cacheIt->_value.surface;\n            else dest.copyFrom(cacheIt->_value.surface);')
    edit(manager + '.cpp', '\t\tdest.copyFrom(surf);\n\t\tsurf.free();',
         '\t\tif (borrowed) dest = _textureCache[key].surface;\n        else dest.copyFrom(surf);\n\t\tsurf.free();')
    edit(manager + '.cpp', 'void HdCostumeManager::pruneCache() {',
         'void HdCostumeManager::pruneCache() {\n    if (_borrowDepth) return;')

    edit(gfx, '\t// HD debug dump — trigger dump when _hdDebugDumpCount >= 3', '''    // Explicit same-tick CPU reference: no scripts/animation advance between
    // the two renders. Readbacks happen only when the test asks for comparison.
    if (remaster.active && getenv("MI3_ENGINE_TEST_INPUT")) {
        Common::String request = ConfMan.get("playtest_session") + "/compare-effects";
        FILE *trigger = fopen(request.c_str(), "r");
        if (trigger) {
            fclose(trigger); remove(request.c_str());
            Graphics::Surface ui = _hdComposite;
            _hdComposite = remaster.reference;
            const bool interpolation = _hdInterpolating, hadDof = remaster.dof;
            _hdFontChars = _hdMotionFonts; // The first pass consumed the same-tick UI commands.
            _hdInterpolating = true;
            ConfMan.setBool("hd_gpu_effects", false);
            renderHDComposite();
            ConfMan.setBool("hd_gpu_effects", true);
            _hdInterpolating = interpolation;
            remaster.reference = _hdComposite; _hdComposite = ui;
            remaster.active = remaster.ui = true; remaster.dof = hadDof;
            remaster.compareReady = true;
            _system->copyRectToScreen(ui.getPixels(), ui.pitch, 0, 0, ui.w, ui.h);
        }
    }
\t// HD debug dump — trigger dump when _hdDebugDumpCount >= 3''')

    edit(gfx, '\tif (!_hdInterpolating) captureHDMotion();', '''    if (!_hdInterpolating) {
        captureHDMotion();
        // Native ticks prepare drawing state; the presentation deadline draws
        // its interpolated pose once. Avoid composing both the endpoint and
        // the interpolated scene in the same 16.67 ms budget.
        if (_hdMotionClock.valid && _hdMotionMoving && canPresentHDMotion()) return;
    }''')
    edit(gl, '    if (ConfMan.hasKey("playtest_session") && _pipeline) hdRemasterGL().initialize();', '''    if (ConfMan.hasKey("playtest_session") && _pipeline) hdRemasterGL().initialize();
    // Submit the cached 1440p canvas on each scheduled presentation even when
    // a native animation cel is unchanged. No scene recomposition is needed.
    if (HdRemaster::state().active) _forceRedraw = true;''')
    edit(gfx, '\t\tif (pfBudget && _hdObjectManager && _hdObjectManager->isEnabled()) {',
         '\t\tif (!remaster.active && pfBudget && _hdObjectManager && _hdObjectManager->isEnabled()) {')
    edit(gfx, '\t\t\tprevRoom = _currentRoom;', '''\t\t\tprevRoom = _currentRoom;
            // Decode the selected visible costumes during room loading. This
            // uses the existing bounded cache and batch decoder; no unrelated
            // room textures are decoded on the presentation deadline.
            if (playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())
                for (int ai = 0; ai < _numActors; ++ai) {
                    Actor *actor = _actors[ai];
                    if (actor && actor->_visible && actor->_room == _currentRoom && actor->_costume)
                        _hdQuiverManager->preloadCostumeRange(actor->_costume, 0, 65535);
                }''')
    edit(gfx, '\tconst double hdCpuStarted = HdRemaster::milliseconds();',
         '\tconst double hdCpuStarted = HdRemaster::milliseconds();\n    const bool hdTrace = ConfMan.hasKey("hd_trace") && ConfMan.getBool("hd_trace");')
    path = root / gfx
    text = path.read_text()
    begin = text.index('void ScummEngine::renderHDComposite() {')
    end = text.index('void ScummEngine::hdAppendDebugLog', begin)
    body = text[begin:end].replace('if (_hdFrameCount % 30 == 0)', 'if (hdTrace && _hdFrameCount % 30 == 0)')
    path.write_text(text[:begin] + body + text[end:])
    edit('engines/scumm/camera.cpp', 'void ScummEngine_v7::setCameraAt(int pos_x, int pos_y) {',
         'void ScummEngine_v7::setCameraAt(int pos_x, int pos_y) {\n    _hdMotionClock.valid = false; // Scripted cuts snap; panCameraTo still interpolates.')
    # Native tall-room buffers are in room space; HD layers are viewport space.
    edit(gfx, 'vs->getBasePtr(s * 8, y)', 'vs->getBasePtr(s * 8, y + _screenTop)')
    path = root / gfx
    text = path.read_text()
    begin = text.index('void ScummEngine::renderHDComposite() {')
    end = text.index('void ScummEngine::hdAppendDebugLog', begin)
    body = text[begin:end].replace('vs->getBasePtr(vs->xstart, sy)', 'vs->getBasePtr(vs->xstart, sy + _screenTop)')
    body = body.replace('vs->getBasePtr(vs->xstart + sx, sy)', 'vs->getBasePtr(vs->xstart + sx, sy + _screenTop)')
    body = body.replace('vs->getBasePtr(vs->xstart, y)', 'vs->getBasePtr(vs->xstart, y + _screenTop)')
    body = body.replace('int yPos = (blastY >= 0) ? blastY : od.y_pos;', 'int yPos = (blastY >= 0) ? blastY : od.y_pos - _screenTop;')
    path.write_text(text[:begin] + body + text[end:])
    edit('engines/scumm/akos.cpp', 'd.screenTop = rect.top;', 'd.screenTop = rect.top - _vm->_screenTop;')
    edit('engines/scumm/actor.cpp', 'screen.getBasePtr(screen.xstart, y)', 'screen.getBasePtr(screen.xstart, y + _vm->_screenTop)')

    # Cache the original RGB painting as RGBA once, including its zero foreground
    # alpha. Camera movement becomes row copies, not two full pixel conversions.
    edit(gfx, '\tfor (int y = 0; y < _hdBackgroundSurface.h && y < hdH; y++) {', """    if (remaster.active) {
        static Graphics::Surface rgbaBackground;
        static const void *source = nullptr;
        static int room = -1, revision = -1;
        if (source != _hdBackgroundSurface.getPixels() || room != _currentRoom || revision != remaster.revision) {
            source = _hdBackgroundSurface.getPixels(); room = _currentRoom; revision = remaster.revision;
            rgbaBackground.convertFrom(_hdBackgroundSurface, rgbaFmt);
            uint32 *pixels = (uint32 *)rgbaBackground.getPixels();
            for (int i = 0; i < rgbaBackground.w * rgbaBackground.h; ++i) pixels[i] &= 0x00ffffffu;
        }
        for (int y = 0; y < hdH; ++y)
            memcpy(_hdComposite.getBasePtr(0, y), rgbaBackground.getBasePtr(srcBgX, y + srcBgY), hdW * 4);
    } else for (int y = 0; y < _hdBackgroundSurface.h && y < hdH; y++) {""")
    edit(gfx, """    if (remaster.active) {
        uint32 *pixels = (uint32 *)_hdComposite.getPixels();
        for (int i = 0; i < hdW * hdH; ++i) pixels[i] &= 0x00ffffff;
    }""", '    // Foreground opacity was initialized in the cached background.')
    # Explicit thumbnail/screenshot requests may read back the finished canvas.
    # Ordinary presentation never reads pixels back from the GPU.
    thumbnail = 'graphics/scaler/thumbnail_intern.cpp'
    edit(thumbnail, '#include "common/system.h"', '#include "common/system.h"\n#include "common/hd_remaster.h"')
    edit(thumbnail, 'static bool grabScreen565(Graphics::Surface *surf) {', """static bool grabScreen565(Graphics::Surface *surf) {
    auto &remaster = HdRemaster::state();
    if (remaster.active && remaster.capture) {
        Graphics::Surface captured;
        if (remaster.capture(captured)) {
            surf->convertFrom(captured, Graphics::PixelFormat(2, 5, 6, 5, 0, 11, 5, 0, 0));
            captured.free(); return true;
        }
    }""")
    edit(thumbnail, 'bool createScreenShot(Graphics::Surface &surf) {', """bool createScreenShot(Graphics::Surface &surf) {
    auto &remaster = HdRemaster::state();
    if (remaster.active && remaster.capture && remaster.capture(surf)) return true;""")
    # One backend deadline waits after rendering. The native engine's timer
    # still owns simulation, but adds no second presentation delay in GPU mode.
    sdl = 'backends/graphics/openglsdl/openglsdl-graphics.cpp'
    (root / 'common/hd_frame_pacer.h').write_bytes((here / 'hd_frame_pacer.h').read_bytes())
    edit(sdl, '#include "common/hd_remaster.h"', '#include "common/hd_remaster.h"\n#include "common/hd_frame_pacer.h"\n#include "graphics/opengl/debug.h"')
    edit(sdl, '\t\tif (!sdlSetSwapInterval(_vsync ? 1 : 0)) {', '''        HdRemaster::state().synchronized60 = _vsync && ConfMan.hasKey("playtest_session");
        if (!sdlSetSwapInterval(_vsync ? 1 : 0)) {
            HdRemaster::state().synchronized60 = false;''')
    edit(sdl, '\tSDL_GL_SwapWindow(_window->getSDLWindow());', '''    static HdPresentation::SwapPacer remasterPacer;
    const bool paced = HdRemaster::state().active && HdRemaster::state().synchronized60;
    if (paced) {
        const double now = 1000.0 * SDL_GetPerformanceCounter() / SDL_GetPerformanceFrequency();
        const uint32 delay = remasterPacer.delay(now);
        if (delay) SDL_Delay(delay);
    } else remasterPacer.reset();
\tSDL_GL_SwapWindow(_window->getSDLWindow());
    if (paced) remasterPacer.presented(1000.0 * SDL_GetPerformanceCounter() / SDL_GetPerformanceFrequency());''')
    edit('engines/scumm/scumm.cpp', 'if (!hdPresentation || _hdPresentationPacer.due(cur)) {',
         'if (!hdPresentation || (HdRemaster::state().active && HdRemaster::state().synchronized60) || _hdPresentationPacer.due(cur)) {')
    edit('engines/scumm/scumm.cpp', 'if (hdPresentation) sleepMs = MIN(sleepMs, _hdPresentationPacer.delay(cur));', '''if (hdPresentation) sleepMs = (HdRemaster::state().active && HdRemaster::state().synchronized60)
            ? 0 : MIN(sleepMs, _hdPresentationPacer.delay(cur));''')
    # Room-owned costumes can appear later in scripted ambient animation.
    # Decode them at room entry instead of discovering each cel during motion.
    edit(manager + '.h', '    void beginBorrow() { ++_borrowDepth; }', '''    void preloadRoomCostumes(int room) {
        for (auto it = _akosSubs.begin(); it != _akosSubs.end(); ++it)
            for (auto owner = it->_value.begin(); owner != it->_value.end(); ++owner)
                if (*owner == room && !HdSceneVisibility::nativePaletteEffect(room, it->_key)) { preloadCostumeRange(it->_key, 0, 65535); break; }
    }
    void beginBorrow() { ++_borrowDepth; }''')
    edit(gfx, '            if (playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())\n                for', '''            if (playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())
                _hdQuiverManager->preloadRoomCostumes(_currentRoom);
            if (playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())
                for''')
    # Include native background/mask and actor drawing in CPU work diagnostics.
    edit('engines/scumm/scumm.cpp', '\t\tscummLoop_handleDrawing();\n\n\t\tscummLoop_handleActors();', '''        {
            const double drawingStarted = HdRemaster::milliseconds();
            scummLoop_handleDrawing();
            scummLoop_handleActors();
            HdRemaster::state().cpuNative += HdRemaster::milliseconds() - drawingStarted;
            HdRemaster::state().cpuWork += HdRemaster::milliseconds() - drawingStarted;
        }''')

    # The GPU consumes the UI staging surface directly. Avoid copying the full
    # 4x transparent layer into the backend's software game buffer every frame.
    edit(gfx, '\t\tif (copyW > 0 && copyH > 0)', '\t\tif (!remaster.active && copyW > 0 && copyH > 0)')

    edit(manager + '.h', '#include "graphics/surface.h"', '#include "graphics/surface.h"\n#include "scumm/hd_scene_visibility.h"')
    edit(gfx, 'if (actor && actor->_visible && actor->_room == _currentRoom && actor->_costume)',
         'if (actor && actor->_visible && actor->_room == _currentRoom && actor->_costume && !HdSceneVisibility::nativePaletteEffect(_currentRoom, actor->_costume))')

    # SDL2-compat reads this setting while initializing its SDL3 backend,
    # before the graphics manager is constructed. This remaster uses desktop
    # fullscreen rather than a separate macOS Space.
    edit('backends/platform/sdl/macosx/macosx-main.cpp', '\tSDL_SetMainReady();',
         '\tSDL_setenv("SDL_VIDEO_MAC_FULLSCREEN_SPACES", "0", 1);\n\tSDL_SetMainReady();')

    # Both aspect ratios are fullscreen in normal play. Only the isolated
    # native test harness can opt into windows for resize/input regressions.
    fullscreen = 'ConfMan.hasKey("playtest_session") && !(SDL_getenv("MI3_ENGINE_TEST_INPUT") && SDL_getenv("MI3_ENGINE_TEST_WINDOWED"))'
    edit(sdl, '\t\t_wantsFullScreen = enable;', '\t\t_wantsFullScreen = (' + fullscreen + ') || enable;')
    edit(sdl, 'bool OpenGLSdlGraphicsManager::loadVideoMode(uint requestedWidth, uint requestedHeight, bool resizable, int antialiasing) {',
         '''bool OpenGLSdlGraphicsManager::loadVideoMode(uint requestedWidth, uint requestedHeight, bool resizable, int antialiasing) {
    if (''' + fullscreen + ''') {
        _wantsFullScreen = true;
#if defined(MACOSX) && SDL_VERSION_ATLEAST(2, 0, 0) && !SDL_VERSION_ATLEAST(3, 0, 0)
        // Borderless desktop fullscreen avoids asynchronous macOS Spaces
        // transitions that can leave SDL2-compat reporting a windowed surface.
        SDL_SetHint("SDL_VIDEO_MAC_FULLSCREEN_SPACES", "0");
#endif
    }''')
    edit(sdl, 'bool OpenGLSdlGraphicsManager::canSwitchFullscreen() const {',
         'bool OpenGLSdlGraphicsManager::canSwitchFullscreen() const {\n    if (' + fullscreen + ') return false;')

    # The same GPU path serves fullscreen 4:3 without double-scaling HD cursors.
    path = root / gl
    text = path.read_text().replace('ConfMan.getInt("hd_aspect_ratio") == 169',
        '(ConfMan.getInt("hd_aspect_ratio") == 169 || HdRemaster::state().active)')
    path.write_text(text)

    # A fixed integral expansion is common to every staged 4x room. Keep the
    # original CPU implementation for the same-tick reference checks.
    (root / 'engines/scumm/hd_native_foreground.inc').write_bytes((here / 'hd_native_foreground.inc').read_bytes())
    edit(gfx, '\t// Step 2 (optimized): Composite 8-bit foreground over HD background',
         '#include "scumm/hd_native_foreground.inc"\n\t// Step 2 (optimized): Composite 8-bit foreground over HD background')
    path = root / gfx
    text = path.read_text()
    begin = text.index('\t// Step 2.6b: Re-overlay')
    end = text.index('\t// Alpha mask persists', begin)
    body = text[begin:end]
    for old, new in [('sy * hdH / visH', 'sy * scale'), ('(sy + 1) * hdH / visH', '(sy + 1) * scale'),
                     ('sx * hdW / visW', 'sx * scale'), ('(sx + 1) * hdW / visW', '(sx + 1) * scale')]:
        body = body.replace(old, new)
    text = text[:begin] + body + text[end:]
    path.write_text(text)

    (root / 'engines/scumm/hd_costume_raster.h').write_bytes((here / 'hd_costume_raster.h').read_bytes())
    edit(gfx, '#include "scumm/hd_costume_edge.h"', '#include "scumm/hd_costume_edge.h"\n#include "scumm/hd_costume_raster.h"')

    # Reuse the native scene before actors when an interpolated camera does
    # not move. Re-decoding the identical room at 60 Hz serves no purpose.
    edit('engines/scumm/scumm.h', '    Common::Array<Actor *> _hdMotionClones, _hdMotionOriginals, _hdMotionSorted;',
         '    Common::Array<Actor *> _hdMotionClones, _hdMotionOriginals, _hdMotionSorted;\n    Common::Array<byte> _hdMotionStageFront, _hdMotionStageMasks;\n    Common::Point _hdMotionStageCamera;\n    int _hdMotionStageRoom = -1;')
    edit('engines/scumm/scumm.cpp', '            scummLoop_handleDrawing();\n            scummLoop_handleActors();', '''            scummLoop_handleDrawing();
            if (_game.id == GID_CMI && _hdScale > 1 && _hdCleanValid && !isSmushActive()) {
                VirtScreen &stage = _virtscr[kMainVirtScreen];
                const uint size = getResourceSize(rtBuffer, kMainVirtScreen + 1);
                _hdMotionStageFront.resize(size);
                memcpy(_hdMotionStageFront.data(), stage.getBasePtr(0, 0), size);
                const uint maskSize = getResourceSize(rtBuffer, 9);
                _hdMotionStageMasks.resize(maskSize);
                if (maskSize) memcpy(_hdMotionStageMasks.data(), getResourceAddress(rtBuffer, 9), maskSize);
                _hdMotionStageCamera = camera._cur; _hdMotionStageRoom = _currentRoom;
            } else _hdMotionStageRoom = -1;
            scummLoop_handleActors();''')
    actor = 'engines/scumm/actor.cpp'
    edit(actor, '            for (uint i = 0; i < _quiverAfter.size(); ++i)',
         '            if (!_vm->_hdInterpolating) for (uint i = 0; i < _quiverAfter.size(); ++i)')

    edit(actor, '        memset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));',
         '        if (!_vm->_hdInterpolating) memset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));')

    # Diagnostic pixels must never consume the game's random sequence, even
    # in a tracing build or an interpolated drawing-only replay.
    edit(gfx, 'int sx = _rnd.getRandomNumber(srcW - 1), sy = _rnd.getRandomNumber(srcH - 1);',
         'int sx = (i * 97) % srcW, sy = (i * 53) % srcH;')
    edit(gfx, '\t\t\t{\n\t\t\t\tconst char *vname =', '\t\t\tif (hdTrace) {\n\t\t\t\tconst char *vname =')

    (root / 'common/hd_depth_of_field.h').write_bytes((here / 'hd_depth_of_field.h').read_bytes())
    edit(gl, '#include "common/hd_remaster.h"', '#include "common/hd_remaster.h"\n#include "common/hd_depth_of_field.h"')

    edit(gl, '#include "backends/graphics/opengl/opengl-graphics.h"',
         '#include <vector>\n#include "backends/graphics/opengl/opengl-graphics.h"')

    edit(gfx, '\tHdRemaster::state().cpuWork += HdRemaster::milliseconds() - hdCpuStarted;',
         '\tif (!_hdInterpolating) HdRemaster::state().cpuScene += HdRemaster::milliseconds() - hdCpuStarted;\n\tHdRemaster::state().cpuWork += HdRemaster::milliseconds() - hdCpuStarted;')

    # Edge correction is artwork data; cache it for static room objects too.
    edit(gfx, '\t\t\tHdObjectDepth::blit((uint32 *)_hdComposite.getPixels(),', '''            static HdCostumeRaster::Cache objectRaster;
            objectRaster.scope(_currentRoom, _playtestCommandId);
            const bool cleanObject = _currentRoom == 9 && od.obj_nr == 275;
            const uint32 *objectPixels = (const uint32 *)hdObjSurfPtr->getPixels();
            int objectPitch = hdObjSurfPtr->pitch / 4;
            const uint32 *corrected = remaster.active && cleanObject ? objectRaster.get(objectPixels,
                objectPitch, hdObjW, hdObjH, hdObjW, hdObjH, -od.obj_nr, objState, false, 2, HdActorLighting::Tint()) : nullptr;
            if (corrected) { objectPixels = corrected; objectPitch = hdObjW; }
\t\t\tHdObjectDepth::blit((uint32 *)_hdComposite.getPixels(),''')
    edit(gfx, 'hdW, hdH, (const uint32 *)hdObjSurfPtr->getPixels(), hdObjSurfPtr->pitch / 4,', 'hdW, hdH, objectPixels, objectPitch,')
    edit(gfx, 'nativeActorMask.data(), hdAlphaMask, _currentRoom == 9 && od.obj_nr == 275);', 'nativeActorMask.data(), hdAlphaMask, cleanObject && !corrected);')

    (root / 'common/hd_ui_upload.h').write_bytes((here / 'hd_ui_upload.h').read_bytes())
    edit(gl, '#include "common/hd_remaster.h"', '#include "common/hd_remaster.h"\n#include "common/hd_ui_upload.h"')

    # SDL/macOS can retain a windowed state after startup/context transactions.
    # Reconcile the actual window state too, including OS-level fullscreen exits.
    edit(sdl, 'void OpenGLSdlGraphicsManager::refreshScreen() {', '''void OpenGLSdlGraphicsManager::refreshScreen() {
#if SDL_VERSION_ATLEAST(2, 0, 0) && !SDL_VERSION_ATLEAST(3, 0, 0)
        static uint32 lastFullscreenRequest = 0;
        if (ConfMan.hasKey("playtest_session") &&
            !(SDL_getenv("MI3_ENGINE_TEST_INPUT") && SDL_getenv("MI3_ENGINE_TEST_WINDOWED")) &&
            !(SDL_GetWindowFlags(_window->getSDLWindow()) & SDL_WINDOW_FULLSCREEN) &&
            (!lastFullscreenRequest || SDL_GetTicks() - lastFullscreenRequest >= 1000)) {
            lastFullscreenRequest = SDL_GetTicks();
            _wantsFullScreen = true;
            if (SDL_SetWindowFullscreen(_window->getSDLWindow(), SDL_WINDOW_FULLSCREEN_DESKTOP) != 0)
                warning("Could not restore remaster fullscreen: %s", SDL_GetError());
        }
#endif''')

    # Per-call GL error polling is useful in debug builds, but introduces driver
    # synchronization around every texture/uniform operation during normal play.
    edit('graphics/opengl/debug.h', '#ifndef __EMSCRIPTEN__\n#define OPENGL_DEBUG',
         '#if !defined(__EMSCRIPTEN__) && !defined(NDEBUG)\n#define OPENGL_DEBUG')
