"""Scale all HD NUT text and expose a persistent control in COMI's book menu."""
from pathlib import Path


def patch(root, edit):
    for name in ('hd_font_size.h', 'hd_font_size_menu.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
    edit('engines/scumm/hd_font_manager.h', '#include "scumm/dialogue_font.h"',
         '#include "scumm/dialogue_font.h"\n#include "scumm/hd_font_size.h"')
    edit('engines/scumm/hd_font_manager.h', '\tDialogueFont dialogue;', '''	int getSizePercent() const { return _sizePercent; }
	void setSizePercent(int percent) { _sizePercent = hdFontSizePercent(percent); }
	int scaleMetric(int pixels) const { return hdFontSizeMetric(pixels, _sizePercent); }
	DialogueFont dialogue;''')
    edit('engines/scumm/hd_font_manager.h', '\tint _scale;', '\tint _scale;\n\tint _sizePercent = 65;')
    edit('engines/scumm/hd_font_manager.cpp', '\t_hdPath = hdPath;', '''	setSizePercent(ConfMan.hasKey("hd_font_size") ? ConfMan.getInt("hd_font_size") : 65);
	_hdPath = hdPath;''')
    edit('engines/scumm/hd_font_manager.cpp', 'int drawW = MIN(glyphW, dest.w - x);',
         'int drawW = MIN(scaleMetric(glyphW), dest.w - x);')
    edit('engines/scumm/hd_font_manager.cpp', 'int drawH = MIN(glyphH, dest.h - y);',
         'int drawH = MIN(scaleMetric(glyphH), dest.h - y);')
    edit('engines/scumm/hd_font_manager.cpp', '// 1:1 blit from the glyph bbox to the destination',
         '// Nearest-neighbor sampling keeps the supplied binary alpha and hard shadows.')
    edit('engines/scumm/hd_font_manager.cpp', '\t\t\t// Source pixel — 1:1 from the cell top (x offset from bbox)', '''			const int sampleX = sx * 100 / _sizePercent;
			const int sampleY = sy * 100 / _sizePercent;
			// Sample relative to the cell top, retaining the original baseline.''')
    for prefix in ('uint32 p = *(uint32 *)', 'const byte *sPix = (const byte *)'):
        edit('engines/scumm/hd_font_manager.cpp',
             prefix + 'src.getBasePtr(srcX + minX + sx, srcY + sy);',
             prefix + 'src.getBasePtr(srcX + minX + sampleX, srcY + sampleY);')
    # Use the very same scaled metrics for wrapping, centering, response hitboxes,
    # and the advance returned by drawing. Preserve the native fallback path.
    for expression in ('_current->getCharHeight(chr & 0xFF)', '_current->getCharWidth(chr & 0xFF)', '_current->getFontHeight()'):
        edit('engines/scumm/charset.cpp', '\treturn ' + expression + ';', '''	if (!font.active && _vm->_hdFontManager->hasFont(_curId))
		return _vm->_hdFontManager->scaleMetric(''' + expression + ''');
	return ''' + expression + ';')
    edit('engines/scumm/charset.cpp', '\t\t\tif (nut)\n\t\t\t\treturn nut->getCharWidth(chr);',
         '\t\t\tif (nut)\n\t\t\t\treturn getCharWidth(chr);')
    # Keep advances at hundredth-pixel precision until HD compositing. Rounding
    # each letter at the original 640x480 resolution would add visible tracking.
    edit('engines/scumm/charset_v7.h', '\tvirtual int getCharWidth(uint16 chr) const = 0;', '''	virtual bool usesFractionalWidths() const { return false; }
	virtual int getCharWidth100(uint16 chr) const { return getCharWidth(chr) * 100; }
	virtual void setHDXFraction(int) {}
	virtual int getCharWidth(uint16 chr) const = 0;''')
    edit('engines/scumm/charset.h', 'class CharsetRendererNut : public CharsetRenderer, public GlyphRenderer_v7 {\npublic:', '''class CharsetRendererNut : public CharsetRenderer, public GlyphRenderer_v7 {
public:
	bool usesFractionalWidths() const override { return true; }
	int getCharWidth100(uint16 chr) const override;
	void setHDXFraction(int fraction) override { _hdXFraction = fraction; }''')
    edit('engines/scumm/charset.h', '\tNutRenderer *_fr[5];', '\tint _hdXFraction = 0;\n\tNutRenderer *_fr[5];')
    edit('engines/scumm/charset.cpp', 'int CharsetRendererNut::getCharHeight(uint16 chr) const {', '''int CharsetRendererNut::getCharWidth100(uint16 chr) const {
	if (!_vm->_hdFontManager->dialogue.active && _vm->_hdFontManager->hasFont(_curId))
		return _current->getCharWidth(chr & 0xFF) * _vm->_hdFontManager->getSizePercent();
	return getCharWidth(chr) * 100;
}

int CharsetRendererNut::getCharHeight(uint16 chr) const {''')
    # The Classic renderer has a matching capture block but no fractional
    # advance field. Restrict this insertion to COMI's Nut renderer.
    charset = root / 'engines/scumm/charset.cpp'
    text = charset.read_text()
    start = text.index('int CharsetRendererNut::drawCharV7(')
    prefix = text[:start].replace('\t\t\tfc.xFraction = _hdXFraction;\n', '')
    suffix = text[start:]
    if 'fc.xFraction = _hdXFraction;' not in suffix:
        suffix = suffix.replace('\t\t\tfc.fontSlot = _curId;\n',
                                '\t\t\tfc.fontSlot = _curId;\n\t\t\tfc.xFraction = _hdXFraction;\n', 1)
    charset.write_text(prefix + suffix)
    edit('engines/scumm/scumm.h', '\tstruct HdFontChar {', '\tstruct HdFontChar {\n\t\tint xFraction = 0;')
    edit('engines/scumm/gfx.cpp', 'int hdX = fi->x * hdW / MAX(1, visW);',
         'int hdX = (fi->x * 100 + fi->xFraction) * hdW / (100 * MAX(1, visW));')
    edit('engines/scumm/string_v7.cpp', 'int TextRenderer_v7::getStringWidth(const char *str, uint numBytesMax) {', '''int TextRenderer_v7::getStringWidth(const char *str, uint numBytesMax) {
	const GlyphRenderer_v7 *hdFont = _gr->usesFractionalWidths() ? _gr : nullptr;''')
    edit('engines/scumm/string_v7.cpp', '\t\t\twidth += _2byteCharWidth + _spacing;',
         '\t\t\twidth += (_2byteCharWidth + _spacing) * 100;')
    edit('engines/scumm/string_v7.cpp', '\t\t\t\treturn width;', '\t\t\t\treturn (width + 99) / 100;')
    edit('engines/scumm/string_v7.cpp', '\t\t\twidth += _gr->getCharWidth((uint8)*str);',
         '\t\t\twidth += hdFont ? hdFont->getCharWidth100((uint8)*str) : _gr->getCharWidth((uint8)*str) * 100;')
    edit('engines/scumm/string_v7.cpp', '\treturn MAX<int>(width, maxWidth);',
         '\treturn (MAX<int>(width, maxWidth) + 99) / 100;')
    before = 'void TextRenderer_v7::drawSubstring(const char *str, uint numBytesMax, byte *buffer, Common::Rect &clipRect, int x, int y, int pitch, int16 &col, TextStyleFlags flags) {'
    edit('engines/scumm/string_v7.cpp', before, before + '''
	GlyphRenderer_v7 *hdFont = _gr->usesFractionalWidths() ? _gr : nullptr;
	int x100 = x * 100;''')
    before = '\t\t\tx += _gr->draw2byte(buffer, clipRect, x, y, pitch, col, (byte)str[i] + 256 * (byte)str[i + 1]);'
    edit('engines/scumm/string_v7.cpp', before, before + '\n\t\t\tx100 = x * 100;')
    edit('engines/scumm/string_v7.cpp', '\t\t\tx += _gr->drawCharV7(buffer, clipRect, x, y, pitch, col, flags, str[i]);', '''			if (hdFont) {
				hdFont->setHDXFraction(x100 % 100);
				_gr->drawCharV7(buffer, clipRect, x, y, pitch, col, flags, str[i]);
				x100 += hdFont->getCharWidth100((uint8)str[i]);
				x = x100 / 100;
				hdFont->setHDXFraction(0);
			} else {
				x += _gr->drawCharV7(buffer, clipRect, x, y, pitch, col, flags, str[i]);
			}''')
    edit('engines/scumm/scumm.h', '\tHdFontManager *_hdFontManager = nullptr;', '''	HdFontManager *_hdFontManager = nullptr;
	bool hasHDFontSizeMenu() const;
	bool handleHDFontSizeEvent(const Common::Event &event);
	void drawHDFontSizeMenu();
	bool _hdFontSizeMouseDown = false;''')
    edit('engines/scumm/gfx.cpp', '#include "common/config-manager.h"',
         '#include "common/config-manager.h"\n#include "common/events.h"')
    if '#include "scumm/hd_font_size_menu.inc"' not in (root / 'engines/scumm/gfx.cpp').read_text():
        edit('engines/scumm/gfx.cpp', 'void ScummEngine::renderHDComposite() {',
             '#include "scumm/hd_font_size_menu.inc"\n\nvoid ScummEngine::renderHDComposite() {')
    edit('engines/scumm/gfx.cpp', '\t// Step 3: Copy the entire HD composite to the system buffer',
         '\tdrawHDFontSizeMenu();\n\n\t// Step 3: Copy the entire HD composite to the system buffer')
    edit('engines/scumm/input.cpp', 'void ScummEngine::parseEvent(Common::Event event) {', '''void ScummEngine::parseEvent(Common::Event event) {
	if (handleHDFontSizeEvent(event)) return;''')
