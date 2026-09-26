// Included after hd_color_grade.inc in gfx.cpp, inside namespace Scumm.

Common::Point ScummEngine::hdSceneJumpPosition() const {
    const int scale = MAX(1, (int)_hdScale);
    const int width = _hdComposite.w ? _hdComposite.w / scale : _screenWidth;
    const auto &presentation = HdRemaster::state();
    const bool cover = hdAspectRatio() == 169 && (width >= 864 ||
        (ConfMan.hasKey("hd_wide_background_active") && ConfMan.getBool("hd_wide_background_active")));
    const HdAspect::Rect visible = HdAspect::visibleGame(presentation.drawableWidth,
        presentation.drawableHeight, hdAspectRatio(), width, cover);
    return Common::Point(visible.x + MAX(0, (visible.w - HdSceneJump::kWidth) / 2),
        visible.y + MAX(0, (visible.h - HdSceneJump::kHeight) / 2));
}

bool ScummEngine::handleHDSceneJumpEvent(const Common::Event &event) {
    if (_game.id != GID_CMI || !ConfMan.hasKey("playtest_session")) return false;
    const bool key = event.type == Common::EVENT_KEYDOWN;
    const int code = key || event.type == Common::EVENT_KEYUP ? event.kbd.keycode : -1;
    const bool keyIndex = code >= 0 && code < Common::KEYCODE_LAST;
    // Release events belong to the panel even when the corresponding press
    // closed it or started a scene transition. Never leak a click into a room.
    if (event.type == Common::EVENT_KEYUP && keyIndex && _hdSceneJumpKeys[code]) {
        _hdSceneJumpKeys[code] = false;
        return true;
    }
    unsigned down = event.type == Common::EVENT_LBUTTONDOWN ? 1 :
        event.type == Common::EVENT_RBUTTONDOWN ? 2 : event.type == Common::EVENT_MBUTTONDOWN ? 4 : 0;
    unsigned up = event.type == Common::EVENT_LBUTTONUP ? 1 :
        event.type == Common::EVENT_RBUTTONUP ? 2 : event.type == Common::EVENT_MBUTTONUP ? 4 : 0;
    if (up && (_hdSceneJumpButtons & up)) {
        _hdSceneJumpButtons &= ~up;
        return true;
    }
    if (!_hdSceneJump.open && key && keyIndex && _hdSceneJumpKeys[code]) return true;
    const bool toggle = key && code == Common::KEYCODE_j &&
        !(event.kbd.flags & (Common::KBD_CTRL | Common::KBD_ALT | Common::KBD_META));
    if (toggle) {
        if (event.kbdRepeat) return true;
        if (!_hdSceneJump.open && (!playtestReadyForJump() || !_hdFontManager ||
            !_hdFontManager->hasFont(3) || !_hdComposite.getPixels())) return false;
        _hdSceneJumpKeys[code] = true;
        if (_hdSceneJump.open) _hdSceneJump.close();
        else {
            hdColorGradeState().panel = false;
            _hdSceneJump.show(_currentRoom, HdSceneJump::kRooms, HdSceneJump::kCount);
            _keyPressed = Common::KeyState();
            _leftBtnPressed = _rightBtnPressed = 0;
            memset(_keyDownMap, 0, sizeof(_keyDownMap));
            memset(_actionMap, 0, sizeof(_actionMap));
        }
        _fullRedraw = true;
        return true;
    }
    if (!_hdSceneJump.open) return false;
    _fullRedraw = true;
    if (event.type == Common::EVENT_MOUSEMOVE || down) {
        // Track the pointer for rendering without setting gameplay click bits.
        const int scale = MAX(1, (int)_hdScale);
        _mouse.x = event.mouse.x / scale;
        _mouse.y = event.mouse.y / scale;
    }
    if (key) {
        if (keyIndex) _hdSceneJumpKeys[code] = true;
        if (event.kbd.flags & (Common::KBD_CTRL | Common::KBD_ALT | Common::KBD_META)) return true;
        switch (code) {
        case Common::KEYCODE_ESCAPE: _hdSceneJump.close(); break;
        case Common::KEYCODE_UP: _hdSceneJump.move(-1, HdSceneJump::kCount); break;
        case Common::KEYCODE_DOWN: _hdSceneJump.move(1, HdSceneJump::kCount); break;
        case Common::KEYCODE_PAGEUP: _hdSceneJump.move(-HdSceneJump::kRows, HdSceneJump::kCount); break;
        case Common::KEYCODE_PAGEDOWN: _hdSceneJump.move(HdSceneJump::kRows, HdSceneJump::kCount); break;
        case Common::KEYCODE_RETURN: case Common::KEYCODE_KP_ENTER:
            if (!event.kbdRepeat) _hdSceneJump.choose(_hdSceneJump.selected, HdSceneJump::kRooms, HdSceneJump::kCount);
            break;
        default: break;
        }
        return true;
    }
    if (down) {
        _hdSceneJumpButtons |= down;
        if (down == 1) {
            const int scale = MAX(1, (int)_hdScale);
            const Common::Point position = hdSceneJumpPosition();
            const int x = event.mouse.x / scale - position.x;
            const int y = event.mouse.y / scale - position.y - 4 - HdSceneJump::kHeaderLines * HdSceneJump::kRowHeight;
            if (x >= 0 && x < HdSceneJump::kWidth && y >= 0 && y < HdSceneJump::kRows * HdSceneJump::kRowHeight)
                _hdSceneJump.choose(_hdSceneJump.first + y / HdSceneJump::kRowHeight, HdSceneJump::kRooms, HdSceneJump::kCount);
        }
        return true;
    }
    if (event.type == Common::EVENT_WHEELUP || event.type == Common::EVENT_WHEELDOWN) {
        _hdSceneJump.move(event.type == Common::EVENT_WHEELUP ? -1 : 1, HdSceneJump::kCount);
        return true;
    }
    // Leave application quit / resize events alone, but block game actions.
    return up || event.type == Common::EVENT_MOUSEMOVE || event.type == Common::EVENT_KEYUP ||
        event.type == Common::EVENT_CUSTOM_ENGINE_ACTION_START || event.type == Common::EVENT_CUSTOM_ENGINE_ACTION_END;
}

void ScummEngine::drawHDSceneJumpPanel() {
    if (!_hdSceneJump.open) return;
    if (!playtestReadyForJump() || _currentRoom != _hdSceneJump.sourceRoom) {
        _hdSceneJump.close();
        return;
    }
    if (!_hdFontManager || !_hdFontManager->hasFont(3) || !_hdComposite.getPixels()) return;
    Common::String lines[HdSceneJump::kLines];
    bool accent[HdSceneJump::kLines] = {};
    int count = 0;
    lines[count++] = "JUMP TO SCENE";
    lines[count++] = Common::String::format("Current room: %04d   Selected: %04d", _currentRoom,
        HdSceneJump::kRooms[_hdSceneJump.selected].number);
    lines[count++] = Common::String::format("Locations %d-%d of %d", _hdSceneJump.first + 1,
        MIN(_hdSceneJump.first + HdSceneJump::kRows, HdSceneJump::kCount), HdSceneJump::kCount);
    for (int row = 0; row < HdSceneJump::kRows; ++row) {
        const int index = _hdSceneJump.first + row;
        if (index < HdSceneJump::kCount) {
            const auto &room = HdSceneJump::kRooms[index];
            accent[count] = index == _hdSceneJump.selected;
            lines[count] = Common::String::format("%s%04d  %s%s", accent[count] ? "> " : "   ",
                room.number, room.name, room.number == _currentRoom ? "  (current)" : "");
        }
        ++count;
    }
    lines[count++] = "Up/Down or wheel: select   PgUp/PgDn: page";
    lines[count++] = "Enter or click: jump   J / Esc: close";
    lines[count++] = "Inventory and story progress are preserved.";
    lines[count++] = "Some scenes require story progress.";
    const Common::Point position = hdSceneJumpPosition();
    const int scale = MAX(1, (int)_hdScale);
    // A solid backing keeps live dialogue and the CPU/GPU scene paths from
    // showing through the menu text. Reuse Scene Look's font and gold accent.
    Common::Rect panel(position.x * scale, position.y * scale,
        (position.x + HdSceneJump::kWidth) * scale,
        (position.y + HdSceneJump::kHeight) * scale);
    panel.clip(Common::Rect(_hdComposite.w, _hdComposite.h));
    _hdComposite.fillRect(panel, _hdComposite.format.RGBToColor(28, 24, 18));
    const int rowY = position.y + 4 +
        (HdSceneJump::kHeaderLines + _hdSceneJump.selected - _hdSceneJump.first) * HdSceneJump::kRowHeight;
    Common::Rect selected((position.x + 4) * scale, rowY * scale,
        (position.x + HdSceneJump::kWidth - 4) * scale, (rowY + HdSceneJump::kRowHeight) * scale);
    selected.clip(panel);
    _hdComposite.fillRect(selected, _hdComposite.format.RGBToColor(95, 55, 35));
    drawHDOverlayText(_hdComposite, _hdFontManager, _charset, scale,
        position.x, position.y, HdSceneJump::kWidth, lines, count, accent, 45, HdSceneJump::kRowHeight, 140);
}
