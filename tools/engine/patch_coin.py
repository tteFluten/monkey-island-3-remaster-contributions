"""Keep the verb coin on the exact-cel path independently of character packs."""
from pathlib import Path


def patch(root, edit):
    edit('engines/scumm/scumm.h', '\tHdCostumeManager *_hdCostumeManager = nullptr;',
         '\tHdCostumeManager *_hdUICostumeManager = nullptr;\n\tHdCostumeManager *_hdCostumeManager = nullptr;')
    edit('engines/scumm/scumm.cpp', '\t_hdCostumeManager = new HdCostumeManager(this);',
         '\t_hdUICostumeManager = new HdCostumeManager(this);\n\t_hdCostumeManager = new HdCostumeManager(this);')
    edit('engines/scumm/scumm.cpp', '\tdelete _hdCostumeManager;',
         '\tdelete _hdUICostumeManager;\n\tdelete _hdCostumeManager;')
    edit('engines/scumm/scumm.cpp', '\t_hdCostumeManager->init(hdPath);',
         '\t_hdUICostumeManager->init(hdPath, true);\n\t_hdCostumeManager->init(hdPath);')
    edit('engines/scumm/actor.h', '\tstruct QuiverDraw {', '\tstruct CoinPixel { int x, y; byte color; };\n\tstruct QuiverDraw {\n\t\tCommon::Array<CoinPixel> coinPixels;')
    manager = root / 'engines/scumm/hd_object_manager.cpp'
    text = manager.read_text()
    previous = '\t// Preserve supplied cursor whites and near-empty highlight states.\n\tif (!path.contains("/objects/0003_")) removeWhiteFringe(surf);'
    text = text.replace(previous, '\tremoveWhiteFringe(surf);')
    manager.write_text(text)
    edit('engines/scumm/hd_object_manager.cpp', '\tremoveWhiteFringe(surf);',
         '\t// Preserve supplied cursor whites and near-empty highlight states.\n\tif (!(path.contains("/objects/0003_bullseye-icon_") || path.contains("/objects/0003_decrement-inventory-arrow_") || path.contains("/objects/0003_dialog-decrement-icon_") || path.contains("/objects/0003_dialog-increment-icon_") || path.contains("/objects/0003_east-arrow-icon_") || path.contains("/objects/0003_increment-inventory-arrow_") || path.contains("/objects/0003_next-page-arrow-icon_") || path.contains("/objects/0003_north-arrow-icon_") || path.contains("/objects/0003_northeast-arrow-icon_") || path.contains("/objects/0003_northwest-arrow-icon_") || path.contains("/objects/0003_prev-page-arrow-icon_") || path.contains("/objects/0003_south-arrow-icon_") || path.contains("/objects/0003_southeast-arrow-icon_") || path.contains("/objects/0003_southwest-arrow-icon_") || path.contains("/objects/0003_system-cursor-icon_") || path.contains("/objects/0003_system-wait-icon_") || path.contains("/objects/0003_west-arrow-icon_"))) removeWhiteFringe(surf);')
    # Record the native coin geometry even outside the character pack's rooms.
    p = root / 'engines/scumm/akos.cpp'
    s = p.read_text().replace('if (!_actorHitMode && playtestExactRoom(_vm->_currentRoom)) {',
                             'if (!_actorHitMode && (playtestExactRoom(_vm->_currentRoom) || _vm->_hdBackgroundSurface.getPixels())) {')
    if '#include "scumm/hd_coin_capture.inc"' not in s:
        s = s.replace('switch (_codec) {', '#include "scumm/hd_coin_capture.inc"\n\t\tswitch (_codec) {')
    p.write_text(s)
    # The legacy costume path must not paint a second coin under the exact one.
    edit('engines/scumm/gfx.cpp', '\t\t\tif (!a || a->_costume == 0 || !a->_visible) {',
         '\t\t\tif (!a || a->_costume == 0 || !a->_visible || (a->_costume == 1 && a->_layer < 0)) {')
    edit('engines/scumm/gfx.cpp', '\t// Step 2.9: (reserved)',
         '\t// Upper coin actors sit above the inventory panel and item icons.\n\t{ const bool hdCoinPass = true;\n#include "scumm/quiver_composite.inc"\n\t}\n\t// Step 2.9: (reserved)')
    for name in ('quiver_prepare.inc', 'quiver_composite.inc', 'hd_coin_capture.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
