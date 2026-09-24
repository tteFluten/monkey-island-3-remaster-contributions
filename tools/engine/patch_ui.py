"""Use staged UI images for every cursor, with exact states and clipped alpha."""
from pathlib import Path


def patch(root, edit):
    edit('engines/scumm/cursor.cpp', '#include "scumm/bomp.h"',
         '#include "scumm/hd_object_manager.h"\n#include "scumm/bomp.h"')
    edit('engines/scumm/cursor.cpp', 'if (img > 105 && img <= 274) {', '''if (_hdObjectManager && _hdObjectManager->isEnabled() &&
                                _hdObjectManager->hasObject(img, _hdObjectManager->findObjectRoom(img), MAX(0, (int)imgindex - 1))) {''')
    edit('engines/scumm/cursor.cpp', 'if (!(_game.version == 8 && img > 105 && img <= 274))',
         'if (!(_game.version == 8 && _hdCursorObject > 0))')
    edit('engines/scumm/cursor.cpp', 'void ScummEngine_v7::setDefaultCursor() {',
         'void ScummEngine_v7::setDefaultCursor() {\n\t_hdCursorObject = 0;')
    path = root / 'engines/scumm/gfx.cpp'
    text = path.read_text()
    marker = '#include "scumm/ui_cursor.inc"'
    if marker not in text:
        start = text.index('\t// Step 2.9: HD cursor overlay')
        end = text.index('\n\t// Step 3: Copy the entire HD composite', start)
        edit('engines/scumm/gfx.cpp', text[start:end], '\t' + marker + '\n')
    text = path.read_text()
    if '// Step 3b: Overwrite SD cursor area' in text:
        start = text.index('\t// Step 3b: Overwrite SD cursor area')
        end = text.index('\n\t// HD debug dump', start)
        edit('engines/scumm/gfx.cpp', text[start:end], '\t// Cursor already composited in the single screen copy above.\n')
    (root / 'engines/scumm/ui_cursor.inc').write_bytes((Path(__file__).parent / 'ui_cursor.inc').read_bytes())
