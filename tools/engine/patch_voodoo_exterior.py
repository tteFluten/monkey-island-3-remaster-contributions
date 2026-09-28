"""Register room 29's foreground and input to its supplied widescreen painting."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'common/hd_voodoo_exterior.h').write_bytes((here / 'hd_voodoo_exterior.h').read_bytes())
    (root / 'engines/scumm/hd_voodoo_exterior.inc').write_bytes((here / 'hd_voodoo_exterior.inc').read_bytes())
    edit('engines/scumm/scumm.h', '\tvoid playtestTick();', '''\tvoid playtestTick();
    bool hdVoodooExteriorActive();
    int hdVoodooExteriorActorOffset(const Actor *actor);
    void publishHDVoodooExteriorInput();
    void placeHDVoodooExteriorForeground();''')
    edit('engines/scumm/gfx.cpp', '#include "scumm/hd_plunder_map.inc"',
         '#include "scumm/hd_plunder_map.inc"\n#include "scumm/hd_voodoo_exterior.inc"')
    edit('engines/scumm/gfx.cpp', '\tplaceHDPlunderMapForeground();',
         '\tplaceHDPlunderMapForeground();\n\tplaceHDVoodooExteriorForeground();')
    edit('engines/scumm/gfx.cpp', 'if (remaster.active || hdPlunderMapActive()) {',
         'if (remaster.active || hdPlunderMapActive() || hdVoodooExteriorActive()) {')
    edit('engines/scumm/input.cpp', '\tpublishHDPlunderMapInput();',
         '\tpublishHDPlunderMapInput();\n\tpublishHDVoodooExteriorInput();')
    edit('engines/scumm/string_v7.cpp',
         '\tif (!hdBookNumber(bt.text, x, y) || !hdBookPlace(x, y)) return;', '''\tif (!hdBookNumber(bt.text, x, y) || !hdBookPlace(x, y)) return;
    if (hdVoodooExteriorActive() && !hdInventoryOpen()) {
        if (ttsIsSubtitle) {
            x = HdVoodooExterior::screenX(x); y = HdVoodooExterior::screenY(y);
        } else if (HdRemaster::state().voodooExteriorInput && charset == 1 && ABS(x - _mouse.x) <= 80 && ABS(y - _mouse.y) <= 80) {
            x += HdRemaster::state().voodooPointerX - _mouse.x;
            y += HdRemaster::state().voodooPointerY - _mouse.y;
        }
    }''')
    edit('backends/graphics/sdl/sdl-graphics.cpp',
         '\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);', '''\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);
    if (!_overlayInGUI && HdRemaster::state().voodooExteriorInput && HdRemaster::state().voodooExterior) {
        setMousePosition(mouse.x, mouse.y);
        showSystemMouseCursor(false);
        int x, y;
        const auto &r = _activeArea.drawRect;
        const bool inside = HdVoodooExterior::pointer(mouse.x, mouse.y,
            r.left, r.top, r.width(), r.height(), x, y);
        _cursorLastInActiveArea = inside;
        if (inside) {
            HdRemaster::state().voodooPointerX = (mouse.x-r.left)*640/r.width();
            HdRemaster::state().voodooPointerY = (mouse.y-r.top)*480/r.height();
            mouse = Common::Point(x*getHeight()/480, y*getHeight()/480);
        }
        return inside;
    }''')
    # Coin scripts keep their original input coordinates. Draw it in the scene
    # pass so its visual hit regions receive the same registration as input.
    edit('engines/scumm/quiver_composite.inc', 'if (coin != hdCoinPass) continue;', '''if (hdVoodooExteriorActive() && !hdInventoryOpen()) {
            if (hdCoinPass) continue;
        } else if (coin != hdCoinPass) continue;''')
    edit('engines/scumm/playtest.inc', '\tCommon::String temporary = directory + "/status.tmp";', '''    status.deleteLastChar();
    status += Common::String::format(",\\\"voodooExterior\\\":%s,\\\"voodooExteriorInput\\\":%s,\\\"voodooCanWalk\\\":%s}",
        hdVoodooExteriorActive() ? "true" : "false", HdRemaster::state().voodooExteriorInput ? "true" : "false",
        _userPut > 0 && _cursor.state > 0 && HdRemaster::state().voodooExteriorInput ? "true" : "false");
\tCommon::String temporary = directory + "/status.tmp";''')

    edit('engines/scumm/actor.cpp', '\tbcr->_actorY = _pos.y - _elevation;', '\tbcr->_actorY = _pos.y - _elevation;\n    bcr->_actorY += _vm->hdVoodooExteriorActorOffset(this);')
