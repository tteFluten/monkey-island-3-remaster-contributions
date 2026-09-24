"""Exact-cel packs: Topaz in every scene; Quiver retains its pilot scenes."""
from pathlib import Path


def patch(root, edit):
    # Upgrade existing room-9 patches before the idempotent insertions below.
    # Room 87 only receives separately staged difficulty knife cels.
    upgrades = [
        ('engines/scumm/akos.cpp', 'if (!_actorHitMode && _vm->_currentRoom == 9)',
         'if (!_actorHitMode && (_vm->_currentRoom == 9 || _vm->_currentRoom == 87))'),
        ('engines/scumm/gfx.cpp', 'const bool quiverActive = _currentRoom == 9 &&',
         'const bool quiverActive = (_currentRoom == 9 || _currentRoom == 87) &&'),
    ]
    for name, before, after in upgrades:
        path = root / name
        text = path.read_text()
        if before in text: path.write_text(text.replace(before, after))
    # Upgrade existing two-scene builds before idempotent insertions below.
    for name, before, after in (
        ('engines/scumm/akos.cpp', '(_vm->_currentRoom == 9 || _vm->_currentRoom == 87)', 'playtestExactRoom(_vm->_currentRoom)'),
        ('engines/scumm/gfx.cpp', '(_currentRoom == 9 || _currentRoom == 87)', 'playtestExactRoom(_currentRoom)'),
    ):
        path = root / name
        path.write_text(path.read_text().replace(before, after))
    for name in ('engines/scumm/akos.cpp', 'engines/scumm/gfx.cpp'):
        # Check the header independently: the SVG patch also extends actor.h's
        # include block, so comparing that whole block reinserts both headers.
        if '#include "scumm/exact_costume_rooms.h"' not in (root / name).read_text():
            edit(name, '#include "scumm/actor.h"', '#include "scumm/exact_costume_rooms.h"\n#include "scumm/actor.h"')
    actor = 'engines/scumm/actor.h'
    edit(actor, '\tint _hdCurrentCel = 0;', '''
	struct CoinPixel { int x, y; byte color; };
	struct QuiverDraw {
		Common::Array<CoinPixel> coinPixels;
		int costume, cel, x, y, width, height, scaleX, scaleY, z, codec;
		int screenLeft = 0, screenTop = 0, screenWidth = 0, screenHeight = 0;
		bool mirror;
	};
	Common::Array<QuiverDraw> _quiverDraws;
	Common::Array<byte> _quiverUnder, _quiverAfter;
	int _quiverWidth = 0, _quiverHeight = 0, _quiverCamera = 0;
	int _hdCurrentCel = 0;''')
    edit('engines/scumm/scumm.h', '\tHdCostumeManager *_hdCostumeManager = nullptr;',
         '\tHdCostumeManager *_hdCostumeManager = nullptr;\n\tHdCostumeManager *_hdQuiverManager = nullptr;')
    edit('engines/scumm/scumm.cpp', '\t_hdCostumeManager = new HdCostumeManager(this);',
         '\t_hdCostumeManager = new HdCostumeManager(this);\n\t_hdQuiverManager = new HdCostumeManager(this);')
    edit('engines/scumm/scumm.cpp', '\tdelete _hdCostumeManager;', '\tdelete _hdCostumeManager;\n\tdelete _hdQuiverManager;')
    edit('engines/scumm/scumm.cpp', '\t_hdCostumeManager->init(hdPath);',
         '\t_hdCostumeManager->init(hdPath);\n\t_hdQuiverManager->init(hdPath + "/quiver-cannon", true);')
    manager = 'engines/scumm/hd_costume_manager'
    edit(manager + '.h', 'bool init(const Common::String &hdPath);', 'bool init(const Common::String &hdPath, bool exactFrames = false);')
    edit(manager + '.h', '\tbool _enabled;', '\tbool _enabled;\n\tbool _exactFrames = false;')
    edit(manager + '.cpp', 'bool HdCostumeManager::init(const Common::String &hdPath) {',
         'bool HdCostumeManager::init(const Common::String &hdPath, bool exactFrames) {\n\t_exactFrames = exactFrames;')
    edit(manager + '.cpp', '\t\t// Not found — find total frames for this AKOS+sub and wrap via modulo',
         '\t\tif (_exactFrames) continue;\n\t\t// Not found — find total frames for this AKOS+sub and wrap via modulo')
    edit(manager + '.cpp', '\t\tif (!_availableCostumes.contains(CostumeKey{akosId, *si, frame})) {',
         '\t\tif (!_availableCostumes.contains(CostumeKey{akosId, *si, frame})) {\n\t\t\tif (_exactFrames) continue;')
    edit(manager + '.cpp', '\tremoveWhiteFringe(surf);', '\tif (!_exactFrames) removeWhiteFringe(surf);')
    # Capture after conditional AKOS draw filtering, immediately before paint.
    akos = root / 'engines/scumm/akos.cpp'
    text = akos.read_text()
    marker = '// QUIVER: preserve every actual draw including cel zero'
    if marker not in text:
        capture = '''// QUIVER: preserve every actual draw including cel zero
		if (!_actorHitMode && (playtestExactRoom(_vm->_currentRoom) || _vm->_hdBackgroundSurface.getPixels())) {
			Actor::QuiverDraw d;
			d.costume = a->_costume; d.cel = code & AKC_CelMask;
			d.x = xMoveCur; d.y = yMoveCur; d.width = _width; d.height = _height;
			d.scaleX = _scaleX; d.scaleY = _scaleY; d.z = _zbuf; d.codec = _codec;
			d.mirror = !_drawActorToRight;
			const_cast<Actor *>(a)->_quiverDraws.push_back(d);
		}
		'''
        needle = 'switch (_codec) {'
        if text.count(needle) != 2:
            raise RuntimeError('Pinned AKOS paint dispatch changed')
        text = text.replace(needle, capture + needle)
        akos.write_text(text)
    actorcpp = 'engines/scumm/actor.cpp'
    edit('engines/scumm/akos.cpp', 'void AkosRenderer::markRectAsDirty(Common::Rect rect) {', '''void AkosRenderer::markRectAsDirty(Common::Rect rect) {
	// Preserve the native scale-table result, including rounding and codec anchors.
	if (!_actorHitMode && (playtestExactRoom(_vm->_currentRoom) || _vm->_hdBackgroundSurface.getPixels())) {
		Actor *a = _vm->derefActor(_actorID, "quiver bounds");
		if (!a->_quiverDraws.empty()) {
			Actor::QuiverDraw &d = a->_quiverDraws.back();
			d.screenLeft = rect.left - (_vm->_virtscr[kMainVirtScreen].xstart & 7);
			if (d.codec == 5 ? !d.mirror : d.mirror) ++d.screenLeft;
			d.screenTop = rect.top;
			d.screenWidth = rect.width(); d.screenHeight = rect.height();
		}
	}''')
    edit(actorcpp, '#include "scumm/actor.h"', '#include "scumm/actor.h"\n#include "scumm/hd_costume_manager.h"')
    edit(actorcpp, '\t// If the actor is partially hidden, redraw it next frame.',
         '#include "scumm/quiver_capture.inc"\n\t// If the actor is partially hidden, redraw it next frame.')
    edit(actorcpp, '\t\t// Record the vertical extent of the drawn actor', '''		if (quiverCapture) {
			const VirtScreen &screen = _vm->_virtscr[kMainVirtScreen];
			_quiverAfter.resize(_quiverUnder.size());
			for (int y = 0; y < _quiverHeight; ++y)
				memcpy(&_quiverAfter[y * _quiverWidth], screen.getBasePtr(screen.xstart, y), _quiverWidth);
		}
		// Record the vertical extent of the drawn actor''')
    gfx = 'engines/scumm/gfx.cpp'
    p = root / gfx
    text = p.read_text()
    if 'const bool hdCoinPass = false;' not in text:
        text = text.replace('#include "scumm/quiver_composite.inc"', 'const bool hdCoinPass = false;\n#include "scumm/quiver_composite.inc"', 1)
        p.write_text(text)
    edit(gfx, '\t// Step 2.6: Overlay HD costume textures on top of composite', '''	const bool quiverActive = playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled();
const bool hdCoinPass = false;
#include "scumm/quiver_composite.inc"
	// Step 2.6: Overlay HD costume textures on top of composite''')
    # Keep the older replacement pack isolated; a bad Quiver cel falls back to native.
    needle = '\tif (_hdCostumeManager && _hdCostumeManager->isEnabled()) {\n\t\t// Collect all visible actors'
    edit(gfx, needle, '\tif (!quiverActive && _hdCostumeManager && _hdCostumeManager->isEnabled()) {\n\t\t// Collect all visible actors')
    for name in ('quiver_capture.inc', 'quiver_composite.inc', 'exact_costume_rooms.h'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
