// Engine banners (quit, pause, restart, sliders, messages) pause the game and
// redraw only once or twice. A fresh HD composite would lose book labels, blast
// text and other per-frame records the paused engine never re-emits, so keep
// the last complete HD frame and replace only the banner's box. See hd_banner.h.
void ScummEngine::captureHDBannerBase() {
    VirtScreen *vs = &_virtscr[kMainVirtScreen];
    const int w = MIN<int>(_screenWidth, vs->pitch - vs->xstart), h = MIN<int>(_screenHeight, vs->h - _screenTop);
    if (!vs->getBasePtr(0, 0) || w <= 0 || h <= 0) { _hdBannerBaseRoom = -1; return; }
    _hdBannerBase.resize(w * h);
    for (int y = 0; y < h; ++y)
        memcpy(&_hdBannerBase[y * w], vs->getPixels(0, _screenTop + y), w);
    _hdBannerBaseRoom = _currentRoom; _hdBannerBaseX = vs->xstart; _hdBannerBaseTop = _screenTop;
    _hdBannerBaseW = w; _hdBannerBaseH = h;
}

// Banner boxes and buttons are sized for the native font, and the HD glyphs
// would sit low in them. Each line is measured (ink and hard shadow) and
// centred in the box or button behind it; lines sharing a box move together.
void ScummEngine::drawHDBannerFonts(int hdW, int hdH, int visW, int visH, const byte *native, int pitch) {
    if (!_hdFontManager || !_hdFontManager->isEnabled() || _hdFontChars.empty()) { _hdFontChars.clear(); return; }
    Graphics::Surface &scratch = _hdBannerText;
    if (scratch.w != hdW || scratch.h != hdH || scratch.format != _hdComposite.format) {
        scratch.free();
        scratch.create(hdW, hdH, _hdComposite.format);
    }
    scratch.fillRect(Common::Rect(scratch.w, scratch.h), 0);
    struct Line { Common::Array<HdFontChar> chars; HdBanner::Rect ink, box; bool placed; int dx, dy; };
    Common::Array<Line> lines;
    for (Common::List<HdFontChar>::iterator fi = _hdFontChars.begin(); fi != _hdFontChars.end(); ++fi) {
        // Glyphs of one line share a row and sit close together; a wide gap
        // (Yes ... No) starts another line.
        if (lines.empty() || lines.back().chars.back().y != fi->y || ABS(fi->x - lines.back().chars.back().x) > 32)
            lines.push_back(Line());
        lines.back().chars.push_back(*fi);
    }
    _hdFontChars.clear();
    auto draw = [&](const HdFontChar &c, Graphics::Surface &dest) {
        const int hdX = (c.x * 100 + c.xFraction) * hdW / (100 * MAX(1, visW)), hdY = c.y * hdH / MAX(1, visH);
        byte r = 255, g = 255, b = 255;
        if (c.col >= 0 && c.col < 256) {
            r = _currentPalette[c.col * 3]; g = _currentPalette[c.col * 3 + 1]; b = _currentPalette[c.col * 3 + 2];
        }
        if (c.dialogue) {
            const Common::Rect clip(c.clip.left * c.dialogueScale, c.clip.top * c.dialogueScale,
                c.clip.right * c.dialogueScale, c.clip.bottom * c.dialogueScale);
            _hdFontManager->dialogue.draw(c.fontSlot, c.chr, c.dialogueScale, dest, hdX, hdY, clip, r, g, b);
        } else {
            _hdFontManager->drawChar(c.fontSlot, c.chr, dest, hdX, hdY, r, g, b);
        }
    };
    const int scale = MAX(1, hdW / MAX(1, visW));
    // Glyphs of a line lie within a few text heights of its row.
    auto window = [&](const Line &line) {
        int top = line.chars[0].y, bottom = top;
        for (const HdFontChar &c : line.chars) { top = MIN(top, c.y); bottom = MAX(bottom, c.y); }
        return Common::Rect(0, CLIP((top - 16) * scale, 0, hdH), hdW, CLIP((bottom + 48) * scale, 0, hdH));
    };
    for (Line &line : lines) {
        const Common::Rect area = window(line);
        for (const HdFontChar &c : line.chars) draw(c, scratch);
        HdBanner::Rect ink;
        ink.left = hdW; ink.top = hdH;
        for (int y = area.top; y < area.bottom; ++y) {
            const uint32 *row = (const uint32 *)scratch.getBasePtr(0, y);
            for (int x = 0; x < hdW; ++x) {
                if (!(row[x] >> scratch.format.aShift & 255)) continue;
                ink.left = MIN(ink.left, x); ink.right = MAX(ink.right, x + 1);
                ink.top = MIN(ink.top, y); ink.bottom = MAX(ink.bottom, y + 1);
            }
        }
        line.ink = ink;
        scratch.fillRect(area, 0);
        line.placed = !ink.empty() && native && HdBanner::container(native, pitch, visW, visH,
            ink.left / scale, (ink.right + scale - 1) / scale, (ink.top + ink.bottom) / 2 / scale, line.box);
        line.dx = line.dy = 0;
        if (line.placed && HdBanner::meantCentred(ink.left, ink.right, line.box.left, line.box.right, scale))
            line.dx = HdBanner::centreOffset(ink.left, ink.right, line.box.left, line.box.right, scale);
    }
    for (uint i = 0; i < lines.size(); ++i) {
        if (!lines[i].placed) continue;
        int top = lines[i].ink.top, bottom = lines[i].ink.bottom;
        for (const Line &other : lines)
            if (other.placed && other.box.left == lines[i].box.left && other.box.top == lines[i].box.top &&
                other.box.right == lines[i].box.right && other.box.bottom == lines[i].box.bottom) {
                top = MIN(top, other.ink.top); bottom = MAX(bottom, other.ink.bottom);
            }
        lines[i].dy = HdBanner::centreOffset(top, bottom, lines[i].box.top, lines[i].box.bottom, scale);
    }
    // Premultiplied glyphs over the frame, each line at its centred position.
    for (const Line &line : lines) {
        if (line.ink.empty()) continue;
        for (const HdFontChar &c : line.chars) draw(c, scratch);
        for (int y = line.ink.top; y < line.ink.bottom; ++y) {
            const int ty = y + line.dy;
            if (ty < 0 || ty >= hdH) continue;
            const uint32 *src = (const uint32 *)scratch.getBasePtr(0, y);
            uint32 *dst = (uint32 *)_hdComposite.getBasePtr(0, ty);
            for (int x = line.ink.left; x < line.ink.right; ++x) {
                const int tx = x + line.dx;
                const uint32 a = src[x] >> scratch.format.aShift & 255;
                if (!a || tx < 0 || tx >= hdW) continue;
                uint32 out = 0;
                for (int shift = 0; shift < 32; shift += 8) {
                    const uint32 s = src[x] >> shift & 255, d = dst[tx] >> shift & 255;
                    out |= MIN<uint32>(255, s + (d * (255 - a) + 127) / 255) << shift;
                }
                dst[tx] = out;
            }
        }
        scratch.fillRect(window(line), 0);
    }
}

// Returns true when this frame was presented from the retained banner frame.
bool ScummEngine::renderHDBannerFrame() {
    VirtScreen *vs = &_virtscr[kMainVirtScreen];
    if (!_messageBannerActive || isSmushActive()) {
        if (_hdBannerState) {
            _hdBannerFrame.free();
            _hdBannerText.free();
            _hdBannerState = 0;
            _fullRedraw = true;
        }
        if (!_hdInterpolating && !isSmushActive()) captureHDBannerBase();
        return false;
    }
    if (_hdBannerState == 2) return false;
    const int scale = MAX(1, (int)_hdScale);
    const int visW = _screenWidth, visH = _screenHeight, hdW = visW * scale, hdH = visH * scale;
    if (_hdBannerState == 0) {
        // _hdComposite still holds the last complete frame (the full scene on
        // the CPU path, the UI layer over the retained GPU scene otherwise).
        const bool usable = _hdComposite.getPixels() && _hdComposite.w == hdW && _hdComposite.h == hdH &&
            _hdComposite.format.bytesPerPixel == 4 && _hdBannerBaseRoom == _currentRoom &&
            _hdBannerBaseX == vs->xstart && _hdBannerBaseTop == _screenTop &&
            _hdBannerBaseW == MIN<int>(visW, vs->pitch - vs->xstart) &&
            _hdBannerBaseH == MIN<int>(visH, vs->h - _screenTop);
        if (!usable) {
            warning("HD banner: no retained frame for room %d; composing normally", _currentRoom);
            _hdBannerState = 2;
            return false;
        }
        _hdBannerFrame.copyFrom(_hdComposite);
        _hdBannerState = 1;
    }
    for (int y = 0; y < hdH; ++y)
        memcpy(_hdComposite.getBasePtr(0, y), _hdBannerFrame.getBasePtr(0, y), hdW * 4);
    const byte *native = vs->getPixels(0, _screenTop);
    const HdBanner::Rect box = HdBanner::changed(native, vs->pitch, _hdBannerBase.data(), _hdBannerBaseW,
        _hdBannerBaseW, _hdBannerBaseH);
    HdBanner::paint((HdBanner::U32 *)_hdComposite.getPixels(), _hdComposite.pitch / 4, hdW, hdH,
        native, vs->pitch, box, scale, _currentPalette);
    drawHDBannerFonts(hdW, hdH, visW, visH, native, vs->pitch);
    auto &remaster = HdRemaster::state();
    if (remaster.active) {
        ++remaster.generation; // Re-upload the UI layer over the unchanged GPU scene.
    } else {
        const int copyW = MIN<int>(hdW, _system->getWidth()), copyH = MIN<int>(hdH, _system->getHeight());
        if (copyW > 0 && copyH > 0)
            _system->copyRectToScreen(_hdComposite.getPixels(), _hdComposite.pitch, 0, 0, copyW, copyH);
    }
    presentHDCursor();
    warning("HD banner: retained frame, room %d, box (%d,%d)-(%d,%d)", _currentRoom, box.left, box.top, box.right, box.bottom);
    return true;
}
