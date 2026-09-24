"""Scope CaslonAntique to COMI speech and in-game response verbs."""
from pathlib import Path


def patch(root, edit):
    for name in ('dialogue_font.h', 'dialogue_font.cpp'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
    if '// Caslon dialogue patch v2' in (root / 'engines/scumm/charset.cpp').read_text():
        return
    edit('engines/scumm/module.mk', '\thd_font_manager.o \\', '\thd_font_manager.o \\\n\tdialogue_font.o \\')
    edit('engines/scumm/hd_font_manager.h', '#include "common/str.h"', '#include "scumm/dialogue_font.h"\n#include "common/str.h"')
    edit('engines/scumm/hd_font_manager.h', '\tHdFontManager(ScummEngine *vm);', '\tDialogueFont dialogue;\n\tHdFontManager(ScummEngine *vm);')
    edit('engines/scumm/hd_font_manager.cpp', '\t_enabled = (loadedCount > 0);', '''	dialogue.init(_hdPath);
	_enabled = (loadedCount > 0);
	_enabled = _enabled || dialogue.available();''')
    edit('engines/scumm/scumm.h', '\tstruct HdFontChar {', '\tstruct HdFontChar {\n\t\tbool dialogue = false;\n\t\tint dialogueScale = 4;\n\t\tCommon::Rect clip;')
    edit('engines/scumm/scumm_v7.h', '\tstruct BlastText : TextObject {', '\tstruct BlastText : TextObject {\n\t\tbool dialogue = false;')
    for filename in ('string_v7.cpp', 'verbs.cpp'):
        edit('engines/scumm/' + filename, '#include "scumm/charset.h"', '#include "scumm/charset.h"\n#include "scumm/hd_font_manager.h"')
    edit('engines/scumm/string_v7.cpp', '\tbt.charset = charset;', '''	bt.charset = charset;
	bt.dialogue = _game.id == GID_CMI && (ttsIsSubtitle || _hdFontManager->dialogue.active);''')
    edit('engines/scumm/string_v7.cpp', '\t\tBlastText &bt = _blastTextQueue[i];', '''		BlastText &bt = _blastTextQueue[i];
		DialogueFontScope fontScope(_hdFontManager->dialogue,
			bt.dialogue && !_useCJKMode && (_hdScale == 4 || _hdScale == 6) && _hdBackgroundSurface.getPixels(), _hdScale);''')
    edit('engines/scumm/string_v7.cpp', 'void ScummEngine_v7::removeBlastTexts() {', '''void ScummEngine_v7::removeBlastTexts() {
	_hdFontChars.clear(); // frame-local, including frames without an HD background''')
    # Scope measuring and queueing together. COMI's text verbs are dialogue
    # responses; difficulty and save/load/options rooms keep their original UI.
    before = '\t\t// Set the specified charset id\n\t\tint oldID = _charset->getCurID();'
    edit('engines/scumm/verbs.cpp', before, '''		DialogueFontScope fontScope(_hdFontManager->dialogue,
			_game.id == GID_CMI && _currentRoom != 87 && _currentRoom != 92 &&
			!_useCJKMode && (_hdScale == 4 || _hdScale == 6) && _hdBackgroundSurface.getPixels(), _hdScale);
''' + before)
    for method, fallback, replacement in (
        ('getCharWidth', 'return _current->getCharWidth(chr & 0xFF);', 'return font.width(_curId, chr & 0xFF);'),
        ('getCharHeight', 'return _current->getCharHeight(chr & 0xFF);', 'return font.height(_curId);'),
    ):
        before = f'int CharsetRendererNut::{method}(uint16 chr) const {{\n\tassert(_current);\n\t{fallback}'
        edit('engines/scumm/charset.cpp', before, f'''int CharsetRendererNut::{method}(uint16 chr) const {{
	assert(_current);
	const DialogueFont &font = _vm->_hdFontManager->dialogue;
	if (font.active && font.has(_curId, chr & 0xFF)) {replacement}
	{fallback}''')
    before = 'int CharsetRendererNut::getFontHeight() const {\n\tassert(_current);'
    edit('engines/scumm/charset.cpp', before, before + '''
	const DialogueFont &font = _vm->_hdFontManager->dialogue;
	if (font.active && font.height(_curId)) return font.height(_curId);''')
    before = 'int CharsetRendererNut::drawCharV7(byte *buffer, Common::Rect &clipRect, int x, int y, int pitch, int16 col, TextStyleFlags flags, byte chr) {'
    edit('engines/scumm/charset.cpp', before, before + '''
	const DialogueFont &font = _vm->_hdFontManager->dialogue;
	if (font.active) {
		if (font.has(_curId, chr)) {
			ScummEngine::HdFontChar fc;
			fc.dialogue = true;
			fc.dialogueScale = font.scale;
			fc.chr = chr; fc.fontSlot = _curId;
			fc.x = x; fc.y = y; fc.col = col; fc.clip = clipRect;
			_vm->_hdFontChars.push_back(fc);
			return font.width(_curId, chr);
		}
		// Unsupported characters use the original glyph AND original metrics.
		return _current->drawCharV7(buffer, clipRect, x, y, pitch, col, flags, chr);
	}''')
    before = '\t\t\tif (_hdFontManager->drawChar(fi->fontSlot, fi->chr, _hdComposite, hdX, hdY, tR, tG, tB))'
    edit('engines/scumm/gfx.cpp', before, '''			if (fi->dialogue) {
				Common::Rect clip(fi->clip.left * fi->dialogueScale, fi->clip.top * fi->dialogueScale, fi->clip.right * fi->dialogueScale, fi->clip.bottom * fi->dialogueScale);
				_hdFontManager->dialogue.draw(fi->fontSlot, fi->chr, fi->dialogueScale, _hdComposite, hdX, hdY, clip, tR, tG, tB);
				++step27_drawn;
				continue;
			}
''' + before)

    edit('engines/scumm/charset.cpp', '#include "scumm/hd_font_manager.h"', '#include "scumm/hd_font_manager.h"\n// Caslon dialogue patch v2')
