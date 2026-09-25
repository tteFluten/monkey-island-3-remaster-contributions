// Included around a real actor draw. Snapshot the native underlay so replacing
// a sprite never clears a rectangular hole through foreground objects. Capture
// native fallback actors in every HD room too: object replacement must preserve
// the actor pixels that the original renderer placed in front of those objects.
const bool quiverCapture = !hitTestMode && _vm->_hdBackgroundSurface.getPixels();
if (!hitTestMode)
    _quiverDraws.clear();
if (quiverCapture) {
    const VirtScreen &screen = _vm->_virtscr[kMainVirtScreen];
    _quiverWidth = _vm->_screenWidth;
    _quiverHeight = _vm->_screenHeight;
    _quiverCamera = screen.xstart;
    _quiverUnder.resize(_quiverWidth * _quiverHeight);
    for (int y = 0; y < _quiverHeight; ++y)
        memcpy(&_quiverUnder[y * _quiverWidth], screen.getBasePtr(screen.xstart, y + _vm->_screenTop), _quiverWidth);
}
