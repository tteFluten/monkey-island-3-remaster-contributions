// Present only the pointer's dirty rectangles between native game ticks.
// _hdComposite remains a clean scene, so moving the mouse never needs another
// full-resolution actor/object render and cannot leave a trail behind.
void ScummEngine::presentHDCursor() {
    if (isSmushActive() || !_hdComposite.getPixels() || !_hdBackgroundSurface.getPixels()) {
        _hdPresentedCursor = Common::Rect();
        return;
    }
    const Common::Rect bounds(MIN<int>(_hdComposite.w, _system->getWidth()),
                              MIN<int>(_hdComposite.h, _system->getHeight()));
    Common::Rect old = _hdPresentedCursor;
    old.clip(bounds);
    if (!old.isEmpty())
        _system->copyRectToScreen(_hdComposite.getBasePtr(old.left, old.top), _hdComposite.pitch,
                                  old.left, old.top, old.width(), old.height());
    _hdPresentedCursor = Common::Rect();
    if (_hdCursorObject <= 0 || _cursor.state <= 0 || !_hdObjectManager) return;
    int room = _hdObjectManager->findObjectRoom(_hdCursorObject);
    int state = MAX(0, _hdCursorImage - 1);
    const Graphics::Surface *sprite = _hdObjectManager->getObjectSurface(_hdCursorObject, room, state);
    if (!sprite || sprite->format.bytesPerPixel != 4 ||
        sprite->w != _cursor.width * _hdScale || sprite->h != _cursor.height * _hdScale) {
        return;
    }
    if (hdAspectRatio() == 169) {
        // Let OpenGL place the existing HD sprite anywhere in the presentation
        // frame. Its position is independent of rejected margin game events.
        if (_hdBackendCursor != sprite) {
            CursorMan.replaceCursor(*sprite, _cursor.hotspotX * _hdScale,
                _cursor.hotspotY * _hdScale, 0, false);
            _hdBackendCursor = sprite;
        }
        return;
    }
    _hdBackendCursor = nullptr;
    byte blank[4] = {};
    CursorMan.replaceCursor(blank, 1, 1, 0, 0, 0, true);
    int left = (_mouse.x - _cursor.hotspotX) * _hdScale;
    int top = (_mouse.y - _cursor.hotspotY) * _hdScale;
    Common::Rect rect(left, top, left + sprite->w, top + sprite->h);
    rect.clip(bounds);
    if (rect.isEmpty()) {
        return;
    }
    Graphics::Surface patch;
    patch.create(rect.width(), rect.height(), _hdComposite.format);
    for (int y = 0; y < patch.h; ++y) {
        const uint32 *under = (const uint32 *)_hdComposite.getBasePtr(rect.left, rect.top + y);
        uint32 *dest = (uint32 *)patch.getBasePtr(0, y);
        for (int x = 0; x < patch.w; ++x) {
            byte a, r, g, b, dr, dg, db;
            sprite->format.colorToARGB(*(const uint32 *)sprite->getBasePtr(rect.left - left + x, rect.top - top + y), a, r, g, b);
            _hdComposite.format.colorToRGB(under[x], dr, dg, db);
            dest[x] = patch.format.ARGBToColor(255,
                (r * a + dr * (255 - a) + 127) / 255,
                (g * a + dg * (255 - a) + 127) / 255,
                (b * a + db * (255 - a) + 127) / 255);
        }
    }
    _system->copyRectToScreen(patch.getPixels(), patch.pitch, rect.left, rect.top, rect.width(), rect.height());
    patch.free();
    _hdPresentedCursor = rect;
}
