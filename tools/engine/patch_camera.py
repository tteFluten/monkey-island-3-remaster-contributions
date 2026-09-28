"""Soft follow and fractional world presentation; applied after renderer patches."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'engines/scumm/hd_camera.h').write_bytes((here / 'hd_camera.h').read_bytes())
    header = 'engines/scumm/scumm.h'
    edit(header, '#include "scumm/hd_motion.h"', '#include "scumm/hd_motion.h"\n#include "scumm/hd_camera.h"')
    edit(header, '    int _hdMotionDrawCamera = 0, _hdMotionDrawTop = 0;', '''    double _hdMotionDrawCamera = 0, _hdMotionDrawTop = 0;
    HdCamera::Follow _hdFollow;
    HdCamera::Click _hdCameraClick;
    double _hdInputCameraLeft = 0, _hdInputCameraTop = 0;
    int _hdInputMouseX = 0, _hdInputMouseY = 0;
    bool _hdCameraDirty = true;
    int _hdCameraActorX = 0, _hdCameraActorY = 0;
    double _hdCameraFractionX = 0, _hdCameraFractionY = 0;
    Common::Array<unsigned> _hdCameraPixels;
    Common::Array<byte> _hdCameraStageFront, _hdCameraStageBack, _hdCameraStageMasks;
    Common::Array<byte> _hdCameraStageClean, _hdCameraStageValidPixels;
    Common::Array<uint32> _hdCameraStageUsage;
    Common::Point _hdCameraStageAnchor;
    bool _hdCameraStageValid = false;
    void resetHDCamera() {
        _hdMotionClock.valid = false;
        _hdFollow = HdCamera::Follow();
        _hdCameraClick.pending = _hdMotionPresented = false;
        _hdCameraDirty = true;
        _hdCameraStageValid = false;
        _hdCameraFractionX = _hdCameraFractionY = 0;
    }''')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, 'if (_hdMotionClock.valid && _hdMotionMoving && canPresentHDMotion()) return;',
         'if (_hdMotionClock.valid && (_hdMotionMoving || _hdFollow.actor) && canPresentHDMotion()) return;')
    edit(gfx, '\tuint32 _hdFrameStartTime = _system->getMillis();', '''    if (!_hdInterpolating) {
        _hdMotionPresented = false;
        _hdCameraFractionX = _hdCameraFractionY = 0;
    }
\tuint32 _hdFrameStartTime = _system->getMillis();''')
    edit(gfx, '    remaster.backgroundX = srcBgX; remaster.backgroundY = srcBgY;', '''    remaster.backgroundX = srcBgX; remaster.backgroundY = srcBgY;
    remaster.cameraFractionX = _hdCameraFractionX;
    remaster.cameraFractionY = _hdCameraFractionY;
    remaster.cameraFollow = _hdFollow.actor != 0;
    remaster.cameraTargetX = _hdFollow.x.target - _screenWidth / 2;
    remaster.cameraTargetY = _hdFollow.y.target - _screenHeight / 2;
    remaster.cameraVelocityX = _hdFollow.x.velocity;
    remaster.cameraVelocityY = _hdFollow.y.velocity;''')
    # GPU performs this resampling together with effects. CPU fallback samples
    # the world before grading/vignette/text, using the same edge extension.
    edit(gfx, '\trenderHDColorGrade();', '''    if (!remaster.active && (_hdCameraFractionX || _hdCameraFractionY)) {
        _hdCameraPixels.resize(_hdComposite.w * _hdComposite.h);
        HdCamera::translate((const unsigned *)_hdComposite.getPixels(), _hdComposite.pitch / 4,
            _hdCameraPixels.data(), _hdComposite.w, _hdComposite.w, _hdComposite.h,
            _hdCameraFractionX * scale, _hdCameraFractionY * scale);
        for (int y = 0; y < _hdComposite.h; ++y)
            memcpy(_hdComposite.getBasePtr(0, y), _hdCameraPixels.data() + y * _hdComposite.w, _hdComposite.w * 4);
    }
\trenderHDColorGrade();''')
    input_file = 'engines/scumm/input.cpp'
    edit(input_file, '_hdMotionDrawCamera - _screenWidth / 2 : vs->xstart',
         'HdCamera::anchor(_hdMotionDrawCamera - _screenWidth / 2) : vs->xstart')
    edit(input_file, '? _hdMotionDrawTop : _screenTop', '? HdCamera::anchor(_hdMotionDrawTop) : _screenTop')

    edit(input_file, '\t\tif (_renderMode == Common::kRenderHercA || _renderMode == Common::kRenderHercG) {', '''        if (_game.id == GID_CMI && (event.type == Common::EVENT_LBUTTONDOWN || event.type == Common::EVENT_RBUTTONDOWN)) {
            _hdCameraClick.pending = false;
            if (_hdMotionPresented && _hdMotionClock.room == _currentRoom && canPresentHDMotion())
                _hdCameraClick.record(_currentRoom, _mouse.x, _mouse.y,
                    _hdMotionDrawCamera - _screenWidth / 2, _hdMotionDrawTop);
        }
\t\tif (_renderMode == Common::kRenderHercA || _renderMode == Common::kRenderHercG) {''')
    edit(input_file, '\tif (_virtualMouse.y < 0)', '''    _hdInputCameraLeft = (_hdMotionPresented && _hdMotionClock.room == _currentRoom)
        ? _hdMotionDrawCamera - _screenWidth / 2 : vs->xstart;
    _hdInputCameraTop = (_hdMotionPresented && _hdMotionClock.room == _currentRoom)
        ? _hdMotionDrawTop : _screenTop;
    _hdInputMouseX = _mouse.x; _hdInputMouseY = _mouse.y;
    if (_hdCameraClick.consume(_currentRoom, (_leftBtnPressed | _rightBtnPressed) & msClicked)) {
        _hdInputCameraLeft = _hdCameraClick.left; _hdInputCameraTop = _hdCameraClick.top;
        _hdInputMouseX = _hdCameraClick.x; _hdInputMouseY = _hdCameraClick.y;
        _virtualMouse.x = _hdInputMouseX + HdCamera::anchor(_hdInputCameraLeft);
        _virtualMouse.y = _hdInputMouseY - vs->topline + HdCamera::anchor(_hdInputCameraTop);
    }
\tif (_virtualMouse.y < 0)''')

    edit('engines/scumm/camera.cpp', '_hdMotionClock.valid = false; // Scripted cuts snap;',
         'resetHDCamera(); // Scripted cuts snap;')
    for filename, signature in (
        ('scumm.cpp', 'void ScummEngine::pauseEngineIntern(bool pause) {'),
        ('saveload.cpp', 'bool ScummEngine::loadState(int slot, bool compat, Common::String &filename) {'),
    ):
        edit('engines/scumm/' + filename, signature, signature + '\n    resetHDCamera();')
    edit('engines/scumm/room.cpp', '\t_currentRoom = room;', '\t_currentRoom = room;\n    resetHDCamera();')
    signature = 'void SmushPlayer::play(const char *filename, int32 speed, int32 offset, int32 startFrame) {'
    edit('engines/scumm/smush/smush_player.cpp', signature, signature + '\n    _vm->resetHDCamera();')
