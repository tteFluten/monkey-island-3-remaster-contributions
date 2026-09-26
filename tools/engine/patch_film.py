"""Opt-in film texture over the completed native presentation, including movies."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_film.h', 'hd_film_text.h'):
        (root / 'common' / name).write_bytes((here / name).read_bytes())
    edit('engines/scumm/gfx.cpp', '#include "common/hd_remaster.h"',
         '#include "common/hd_remaster.h"\n#include "common/hd_film.h"\n#include "common/hd_film_text.h"')
    gl = 'backends/graphics/opengl/opengl-graphics.cpp'
    (root / 'backends/graphics/opengl/hd_film_gl.inc').write_bytes((here / 'hd_film_gl.inc').read_bytes())
    edit(gl, '#include "common/hd_remaster.h"',
         '#include "common/hd_remaster.h"\n#include "common/hd_film.h"\n#include "common/hd_film_text.h"')
    edit(gl, '#include "hd_remaster_gl.inc"',
         '#include "hd_remaster_gl.inc"\n#include "hd_film_gl.inc"')
    edit(gl, 'void OpenGLGraphicsManager::updateScreen() {', '''void OpenGLGraphicsManager::updateScreen() {
    if (hdFilmGL().needsRedraw()) _forceRedraw = true;''')
    # Backend dialogs and OSD use separate font renderers. Shift the game
    # before those layers, then apply the remaining film texture at the end.
    edit(gl, '\t// Third step: Draw the overlay if visible.', '''    bool filmTextOverlay = _overlayVisible;
#ifdef USE_OSD
    filmTextOverlay = filmTextOverlay || _osdMessageSurface;
#endif
    if (filmTextOverlay)
        hdFilmGL().draw(_pipeline, _targetBuffer, _gameDrawRect,
            _windowWidth, _windowHeight, false, _hdWideBackground != nullptr, true);
\t// Third step: Draw the overlay if visible.''')
    edit(gl, '\thdRemasterGL().endFrame();', '''    hdFilmGL().draw(_pipeline, _targetBuffer, _gameDrawRect,
        _windowWidth, _windowHeight, _overlayVisible, _hdWideBackground != nullptr, false, filmTextOverlay);
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

    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '\trenderHDColorGrade();', '\trenderHDColorGrade();\n    HdFilmText::begin(_hdComposite);')
    for name in ('hd_font_manager.cpp', 'dialogue_font.cpp'):
        source = 'engines/scumm/' + name
        edit(source, '#include "common/fs.h"', '#include "common/fs.h"\n#include "common/hd_film_text.h"')
    edit('engines/scumm/hd_font_manager.cpp', '\t\t\t// Write to destination (use dest channel shifts)',
         '\t\t\tHdFilmText::pixel(dest, px, py, a);\n\t\t\t// Write to destination (use dest channel shifts)')
    edit('engines/scumm/dialogue_font.cpp', '\t\t\tif (!a) continue;',
         '\t\t\tif (!a) continue;\n\t\t\tHdFilmText::pixel(dest, x + sx, y + sy, a);')
    # Text-size labels are drawn into a temporary glyph-only surface first.
    edit('engines/scumm/hd_font_size_menu.inc', '\t\t\t\tif (a)\n',
         '\t\t\t\tHdFilmText::pixel(_hdComposite, targetX + x - minX, targetY + y - minY, a);\n\t\t\t\tif (a)\n')
    player = 'engines/scumm/smush/smush_player.cpp'
    edit(player, '#include "common/hd_remaster.h"',
         '#include "common/hd_remaster.h"\n#include "common/hd_film_text.h"')
    edit(player, '                        const byte *pixels = _hdFrameBuffer;',
         '                        HdFilmText::begin(w, h);\n                        const byte *pixels = _hdFrameBuffer;')
    edit(player, '                                    _vm->_screenWidth, _vm->_screenHeight, _pal);',
         '                                    _vm->_screenWidth, _vm->_screenHeight, _pal,\n                                    (byte *)HdFilmText::state().mask.getPixels(), HdFilmText::state().mask.pitch);\n                                HdFilmText::state().any = true;')
    edit(player, '                                frame.init(w, h, w * 4, _hdScaleBuffer, Graphics::PixelFormat::createFormatRGBA32());',
         '                                frame.init(w, h, w * 4, _hdScaleBuffer, Graphics::PixelFormat::createFormatRGBA32());\n                                HdFilmText::target(frame);')

    # Native NUT fallback glyphs travel with the existing frame-local font
    # queue, including its copies for interpolated presentation frames.
    edit('engines/scumm/scumm.h', '\tstruct HdFontChar {', '''\tstruct HdFontChar {
        Common::Array<byte> filmCoverage;
        int filmWidth = 0, filmHeight = 0;''')
    edit('engines/scumm/nut_renderer.cpp', '\tif (minY) {\n\t\tsrc += minY * _chars[chr].width;', '''    if (_vm->_game.id == GID_CMI && _vm->_hdScale > 1 && !smushColorMode && width > minX && height > minY) {
        ScummEngine::HdFontChar glyph;
        glyph.chr = chr; glyph.fontSlot = -1; glyph.col = col;
        glyph.x = x + minX; glyph.y = y + minY;
        glyph.filmWidth = width - minX; glyph.filmHeight = height - minY;
        glyph.filmCoverage.resize(glyph.filmWidth * glyph.filmHeight);
        for (int gy = minY; gy < height; ++gy)
            for (int gx = minX; gx < width; ++gx)
                glyph.filmCoverage[(gy - minY) * glyph.filmWidth + gx - minX] =
                    _chars[chr].src[gy * _chars[chr].width + gx] != _chars[chr].transparency ? 255 : 0;
        _vm->_hdFontChars.push_back(glyph);
    }
\tif (minY) {
\t\tsrc += minY * _chars[chr].width;''')
    edit(gfx, '\t\tfor (Common::List<HdFontChar>::iterator fi = _hdFontChars.begin(); fi != _hdFontChars.end(); ++fi) {', '''\t\tfor (Common::List<HdFontChar>::iterator fi = _hdFontChars.begin(); fi != _hdFontChars.end(); ++fi) {
            if (!fi->filmCoverage.empty()) {
                for (int gy = 0; gy < fi->filmHeight; ++gy)
                    for (int gx = 0; gx < fi->filmWidth; ++gx) if (fi->filmCoverage[gy * fi->filmWidth + gx])
                        for (int py = 0; py < scale; ++py)
                            for (int px = 0; px < scale; ++px)
                                HdFilmText::pixel(_hdComposite, (fi->x + gx) * scale + px,
                                    (fi->y + gy) * scale + py, 255);
                continue;
            }''')

    edit('engines/scumm/object.cpp', '#include "common/hd_remaster.h"',
         '#include "common/hd_remaster.h"\n#include "common/hd_film_text.h"')
    edit('engines/scumm/object.cpp', '#include "common/hd_remaster.h"',
         '#include "common/hd_remaster.h"\n#include "common/hd_film_text.h"')
    edit('engines/scumm/hd_inventory.inc', '    const int offset = hdInventoryOffset() * _hdScale;',
         '    const int offset = hdInventoryOffset() * _hdScale;\n    HdFilmText::shiftX(_hdComposite, offset);')
