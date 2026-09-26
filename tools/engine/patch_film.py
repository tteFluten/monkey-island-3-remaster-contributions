"""Opt-in film texture over the completed native presentation, including movies."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'common/hd_film.h').write_bytes((here / 'hd_film.h').read_bytes())
    edit('engines/scumm/gfx.cpp', '#include "common/hd_remaster.h"',
         '#include "common/hd_remaster.h"\n#include "common/hd_film.h"')
    gl = 'backends/graphics/opengl/opengl-graphics.cpp'
    (root / 'backends/graphics/opengl/hd_film_gl.inc').write_bytes((here / 'hd_film_gl.inc').read_bytes())
    edit(gl, '#include "common/hd_remaster.h"',
         '#include "common/hd_remaster.h"\n#include "common/hd_film.h"')
    edit(gl, '#include "hd_remaster_gl.inc"',
         '#include "hd_remaster_gl.inc"\n#include "hd_film_gl.inc"')
    edit(gl, 'void OpenGLGraphicsManager::updateScreen() {', '''void OpenGLGraphicsManager::updateScreen() {
    if (hdFilmGL().needsRedraw()) _forceRedraw = true;''')
    edit(gl, '\thdRemasterGL().endFrame();', '''    hdFilmGL().draw(_pipeline, _targetBuffer, _gameDrawRect,
        _windowWidth, _windowHeight, _overlayVisible, _hdWideBackground != nullptr);
\thdRemasterGL().endFrame();''')
    for signature in ('void OpenGLGraphicsManager::notifyContextDestroy() {',
                      'OpenGLGraphicsManager::~OpenGLGraphicsManager() {'):
        edit(gl, signature, signature + '\n    hdFilmGL().destroy();')
    events = 'backends/events/sdl/sdl2-events.cpp'
    edit(events, '#include "common/scummsys.h"',
         '#include "common/scummsys.h"\n#include "common/hd_film.h"')
    # Consume both edges before keymapping or engine/movie event handling. Avoid
    # autorepeat; modified F combinations retain their existing behavior.
    edit(events, 'bool SdlEventSource::dispatchSDLEvent(SDL_Event &ev, Common::Event &event) {', '''bool SdlEventSource::dispatchSDLEvent(SDL_Event &ev, Common::Event &event) {
    if (ConfMan.hasKey("playtest_session") &&
        (ev.type == SDL_KEYDOWN || ev.type == SDL_KEYUP) && ev.key.keysym.sym == SDLK_f &&
        !(ev.key.keysym.mod & (KMOD_CTRL | KMOD_SHIFT | KMOD_ALT | KMOD_GUI))) {
        if (ev.type == SDL_KEYDOWN && !ev.key.repeat) HdFilm::toggle();
        return false;
    }''')
