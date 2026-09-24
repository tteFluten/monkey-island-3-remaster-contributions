"""Draw-only interpolation for HD scrolling rooms; preserve native simulation."""
from pathlib import Path


def patch(root, edit):
    header = 'engines/scumm/scumm.h'
    if '#include "scumm/hd_motion.h"' not in (root / header).read_text():
        edit(header, '#include "scumm/hd_frame_pacer.h"', '#include "scumm/hd_motion.h"\n#include "scumm/hd_frame_pacer.h"')
    edit(header, '\tCommon::List<HdFontChar> _hdFontChars;', '''\tCommon::List<HdFontChar> _hdFontChars;
    Common::List<HdFontChar> _hdMotionFonts;
    HdMotion::Clock _hdMotionClock;
    HdMotion::Track _hdMotionCamera;
    Common::Array<HdMotion::Track> _hdMotionActors;
    bool _hdInterpolating = false, _hdMotionMoving = false;
    bool _hdMotionPresented = false;
    int _hdMotionDrawCamera = 0;
    bool canPresentHDMotion();
    void captureHDMotion();
    void presentHDMotion();''')
    edit('engines/scumm/actor.h', '\tCostumeData _cost;', '''\tCostumeData _cost;
    CostumeData _hdRenderCost;
    void hdSetDrawPosition(Common::Point point) { _pos = point; }''')
    edit('engines/scumm/actor.cpp', '\tsetupActorScale();\n\n\tBaseCostumeRenderer *bcr',
         '\tif (!_vm->_hdInterpolating) _hdRenderCost = _cost;\n\tsetupActorScale();\n\n\tBaseCostumeRenderer *bcr')
    edit('engines/scumm/scumm.cpp', 'void ScummEngine::scummLoop_handleDrawing() {', """void ScummEngine::scummLoop_handleDrawing() {
    // Partial strip redraws leave stale clean-background pixels under static
    // actors in HD panoramas. Rebuild the native reference before every tick.
    if (_game.id == GID_CMI && _hdScale > 1 && _hdBackgroundSurface.getPixels() &&
        _roomWidth > _screenWidth && _currentRoom != 92)
        _fullRedraw = true;""")
    edit('engines/scumm/input.cpp', '\t_virtualMouse.x = _mouse.x + vs->xstart;',
         '\t_virtualMouse.x = _mouse.x + ((_hdMotionPresented && _hdMotionClock.room == _currentRoom) ? _hdMotionDrawCamera - _screenWidth / 2 : vs->xstart);')
    gfx = 'engines/scumm/gfx.cpp'
    if '#include "scumm/hd_motion.inc"' not in (root / gfx).read_text():
        edit(gfx, 'void ScummEngine::renderHDComposite() {', '#include "scumm/hd_motion.inc"\n\nvoid ScummEngine::renderHDComposite() {')
    edit(gfx, '\tuint32 _hdFrameStartTime = _system->getMillis();',
         '\tif (!_hdInterpolating) captureHDMotion();\n\tuint32 _hdFrameStartTime = _system->getMillis();')
    edit('engines/scumm/scumm.cpp', 'if (hdPresentation) presentHDCursor();',
         'if (hdPresentation) { presentHDMotion(); presentHDCursor(); }')
    for name in ('hd_motion.h', 'hd_motion.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
