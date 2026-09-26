"""Draw HD movie subtitles from the shared sharp font sheets after video decode."""
from pathlib import Path


def patch(root, edit):
    for name in ('hd_movie_text.h', 'hd_smush_font.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
    # Make fractional advances available to SMUSH as well as gameplay text.
    edit('engines/scumm/charset_v7.h', '\tvirtual int getCharWidth(uint16 chr) const = 0;', '''	virtual bool usesFractionalWidths() const { return false; }
	virtual int getCharWidth100(uint16 chr) const { return getCharWidth(chr) * 100; }
	virtual void setHDXFraction(int) {}
	virtual int getCharWidth(uint16 chr) const = 0;''')
    edit('engines/scumm/charset.h', '\tint getCharWidth100(uint16 chr) const;\n\tvoid setHDXFraction(int fraction) { _hdXFraction = fraction; }', '''	bool usesFractionalWidths() const override { return true; }
	int getCharWidth100(uint16 chr) const override;
	void setHDXFraction(int fraction) override { _hdXFraction = fraction; }''')
    edit('engines/scumm/string_v7.cpp', '\tconst CharsetRendererNut *hdFont = dynamic_cast<const CharsetRendererNut *>(_gr);',
         '\tconst GlyphRenderer_v7 *hdFont = _gr->usesFractionalWidths() ? _gr : nullptr;')
    edit('engines/scumm/string_v7.cpp', '\tCharsetRendererNut *hdFont = dynamic_cast<CharsetRendererNut *>(_gr);',
         '\tGlyphRenderer_v7 *hdFont = _gr->usesFractionalWidths() ? _gr : nullptr;')

    font = 'engines/scumm/smush/smush_font.h'
    edit(font, '#include "scumm/nut_renderer.h"', '''#include "scumm/nut_renderer.h"
#include "scumm/hd_font_manager.h"
#include "scumm/hd_movie_text.h"
#include "scumm/hd_video_support.h"
#include "common/array.h"''')
    edit(font, '\tTextRenderer_v7 *_r;', '#include "scumm/hd_smush_font.inc"\n\tTextRenderer_v7 *_r;')
    for method, arg in (('getCharWidth', 'chr & 0xFF'), ('getCharHeight', 'chr & 0xFF'), ('getFontHeight', '')):
        edit(font, f'return NutRenderer::{method}({arg});', f'return hdMetric(NutRenderer::{method}({arg}));')
    original = '\t\treturn NutRenderer::drawCharV7(buffer, clipRect, x, y, pitch, col, flags, chr, _hardcodedFontColors, true);'
    edit(font, original, '''		if (_hdGlyphs) {
			HdMovieGlyph glyph;
			glyph.slot = _hdSlot; glyph.chr = chr;
			glyph.x100 = x * 100 + _hdFraction; glyph.y = y;
			glyph.sizePercent = _vm->_hdFontManager->getSizePercent();
			glyph.color = hdColor(chr, col); glyph.clip = clipRect;
			_hdGlyphs->push_back(glyph);
			return getCharWidth(chr);
		}
''' + original)

    header = 'engines/scumm/smush/smush_player.h'
    edit(header, '#define SCUMM_SMUSH_PLAYER_H', '#define SCUMM_SMUSH_PLAYER_H\n#include "scumm/hd_movie_text.h"')
    edit(header, '    bool _hdHasSubtitles = false;', '    Common::Array<HdMovieGlyph> _hdMovieGlyphs;\n    bool _hdHasSubtitles = false;')
    player = 'engines/scumm/smush/smush_player.cpp'
    edit(player, '    _hdHasSubtitles = false;', '    _hdMovieGlyphs.clear();\n    _hdHasSubtitles = false;')
    for method in ('drawStringWrap', 'drawString'):
        old = f'''            sf->{method}(str, _hdSubtitleDark.data(), clipRect, pos_x, pos_y, color, flg);
            sf->{method}(str, _hdSubtitleLight.data(), clipRect, pos_x, pos_y, color, flg);'''
        new = f'            // Crop-aware HD layout for {method}.\n' + '''            // Native drawing mutates clipRect to its text bounds. The HD
            // pass needs fresh crop-aware bounds, not that narrowed rectangle.
            const Common::Rect safe = HdMovieText::safeArea(_width, _height,
                _vm->hdAspectRatio());
            const int textX = (safe.left + safe.right) / 2;
            // Dialogue sits above the lower picture edge. Keep non-dialogue
            // captions near their authored vertical position within the crop.
            const int textY = (flags & 8) ? safe.bottom :
                safe.top + CLIP<int>(pos_y, 0, _height) * safe.height() / MAX(1, _height);
            const TextStyleFlags textFlags = (TextStyleFlags)((flg & ~kStyleAlignRight) |
                kStyleAlignCenter | kStyleWordWrap);
            Common::Rect textClip = safe;
            if (sf->beginHD(fontId, _hdMovieGlyphs)) {
                sf->drawStringWrap(str, _dst, textClip, textX, textY, color, textFlags);
                sf->endHD();
            } else {
                sf->drawStringWrap(str, _hdSubtitleDark.data(), textClip, textX, textY, color, textFlags);
                textClip = safe; // Each native mask pass also mutates its bounds.
                sf->drawStringWrap(str, _hdSubtitleLight.data(), textClip, textX, textY, color, textFlags);
            }'''
        edit(player, old, new)
    original = '                                pixels = (const byte *)_hdScaleBuffer;'
    edit(player, original, '''                                // Draw crisp glyphs at final resolution, after scaling the movie.
                                Graphics::Surface frame;
                                frame.init(w, h, w * 4, _hdScaleBuffer, Graphics::PixelFormat::createFormatRGBA32());
                                const int previousTextSize = _vm->_hdFontManager ?
                                    _vm->_hdFontManager->getSizePercent() : 65;
                                for (uint i = 0; i < _hdMovieGlyphs.size(); ++i) {
                                    const HdMovieGlyph &g = _hdMovieGlyphs[i];
                                    _vm->_hdFontManager->setSizePercent(g.sizePercent);
                                    Common::Rect clip(g.clip.left * w / _vm->_screenWidth,
                                        g.clip.top * h / _vm->_screenHeight,
                                        g.clip.right * w / _vm->_screenWidth,
                                        g.clip.bottom * h / _vm->_screenHeight);
                                    clip.clip(Common::Rect(w, h));
                                    if (clip.isEmpty()) continue;
                                    Graphics::Surface target = frame.getSubArea(clip);
                                    const byte *rgb = _pal + g.color * 3;
                                    _vm->_hdFontManager->drawChar(g.slot, g.chr, target,
                                        g.x100 * w / (100 * _vm->_screenWidth) - clip.left,
                                        g.y * h / _vm->_screenHeight - clip.top, rgb[0], rgb[1], rgb[2]);
                                }
                                if (_vm->_hdFontManager) _vm->_hdFontManager->setSizePercent(previousTextSize);
''' + original)
