"""Room-13 artwork registration and full-painting input, without script edits."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'common/hd_plunder_map.h').write_bytes((here / 'hd_plunder_map.h').read_bytes())
    (root / 'engines/scumm/hd_plunder_map.inc').write_bytes((here / 'hd_plunder_map.inc').read_bytes())
    edit('engines/scumm/scumm.h', '\tvoid playtestTick();', '''\tvoid playtestTick();
    bool hdPlunderMapActive();
    bool hdPlunderMapOverlaySuppressed(int costume);
    void publishHDPlunderMapInput();
    void placeHDPlunderMapForeground();''')
    edit('engines/scumm/actor.cpp', 'void Actor::drawActorCostume(bool hitTestMode) {', '''void Actor::drawActorCostume(bool hitTestMode) {
    // Suppress the obsolete map overlay before it can paint either native
    // buffer. Compositor removal is too late for room-entry/uncaptured draws.
    if (!hitTestMode && _vm->hdPlunderMapOverlaySuppressed(_costume)) {
        _quiverDraws.clear();
        _hdNumLimbs = 0;
        _needRedraw = false;
        return;
    }''')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "scumm/hd_book.inc"',
         '#include "scumm/hd_book.inc"\n#include "scumm/hd_plunder_map.inc"')
    edit(gfx, '\trenderHDColorGrade();', '\tplaceHDPlunderMapForeground();\n\trenderHDColorGrade();')
    edit(gfx, 'if (remaster.active) {\n        static Graphics::Surface rgbaBackground;',
         'if (remaster.active || hdPlunderMapActive()) {\n        static Graphics::Surface rgbaBackground;')
    edit('engines/scumm/string_v7.cpp', '#include "common/config-manager.h"',
         '#include "common/config-manager.h"\n#include "common/hd_remaster.h"')
    edit('engines/scumm/string_v7.cpp',
         '\tif (!hdBookNumber(bt.text, x, y) || !hdBookPlace(x, y)) return;', '''\tif (!hdBookNumber(bt.text, x, y) || !hdBookPlace(x, y)) return;
    if (hdPlunderMapActive() && HdRemaster::state().plunderMapInput && !ttsIsSubtitle) {
        const int object = findObject(_virtualMouse.x, _virtualMouse.y);
        // Map captions may carry translation/formatting escapes or be "?"
        // until discovered. Their pointer-relative anchor is stable; do not
        // compare the display string with the resource's internal object name.
        if (object && charset == 1 && ABS(x - _mouse.x) <= 80 && ABS(y - _mouse.y) <= 80) {
            x += HdRemaster::state().plunderPointerX - _mouse.x;
            y += HdRemaster::state().plunderPointerY - _mouse.y;
        }
    }''')
    edit('engines/scumm/input.cpp', 'void ScummEngine::parseEvents() {',
         'void ScummEngine::parseEvents() {\n\tpublishHDPlunderMapInput();')
    sdl = 'backends/graphics/sdl/sdl-graphics.cpp'
    edit(sdl, '#include "common/config-manager.h"',
         '#include "common/config-manager.h"\n#include "common/hd_remaster.h"')
    # Use the normal widescreen cover framing. Input below inverts the actual
    # draw rectangle, so cropped edges need no separate hotspot adjustment.
    edit(sdl, '\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);', '''\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);
    if (!_overlayInGUI && HdRemaster::state().plunderMapInput && HdRemaster::state().plunderMap) {
        // Retain physical cursor placement; only script input is translated.
        setMousePosition(mouse.x, mouse.y);
        showSystemMouseCursor(false);
        int x, y;
        const auto &r = _activeArea.drawRect;
        const bool inside = HdPlunderMap::pointer(mouse.x, mouse.y,
            r.left, r.top, r.width(), r.height(), x, y);
        _cursorLastInActiveArea = inside;
        if (inside) {
            HdRemaster::state().plunderPointerX = (mouse.x - r.left) * 640 / r.width();
            HdRemaster::state().plunderPointerY = (mouse.y - r.top) * 480 / r.height();
            mouse = Common::Point(x * getHeight() / 480, y * getHeight() / 480);
        }
        return inside;
    }''')
    # Native checks inspect the actual engine pick, including object class and
    # parent-state restrictions; they do not bypass the game's dispatch.
    edit('engines/scumm/playtest.inc', '\tCommon::String temporary = directory + "/status.tmp";', '''    status.deleteLastChar();
    status += Common::String::format(",\\\"plunderMap\\\":%s,\\\"plunderMapInput\\\":%s,\\\"hoverObject\\\":%d}",
        hdPlunderMapActive() ? "true" : "false", HdRemaster::state().plunderMapInput ? "true" : "false",
        findObject(_virtualMouse.x, _virtualMouse.y));
\tCommon::String temporary = directory + "/status.tmp";''')
