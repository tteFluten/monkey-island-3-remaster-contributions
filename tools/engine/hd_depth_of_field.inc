// Included in gfx.cpp. Camera depth of field over the original z-plane
// foreground: draw-time only, the room artwork is never modified.
namespace {
struct HdDepthOfFieldState {
    // Reduced, blurred copy of the current room painting, keyed by its source.
    const void *pixels = nullptr;
    int room = -1, width = 0, height = 0, radius = 0, scale = 0;
    std::vector<uint32> blur;
    int blurW = 0, blurH = 0, factor = 1;
    // Feathered native foreground coverage for the frame being composed.
    std::vector<byte> coverage, masks, maskScratch;
    int maskWidth = 0, maskHeight = 0, maskOffset = -1, maskEdge = -1, maskDepth = -1;
    bool maskAny = false;
    uint cpuCoverageGeneration = ~0u;
    std::vector<bool> rows;
    int visW = 0, visH = 0, intensity = 100;
    bool active = false;
    // Live-tuning readout and the level restored by the on/off hotkey.
    uint32 hudUntil = 0;
    int lastLevel = 2;
};
// Engine-lifetime state; allocated once to avoid a global destructor.
HdDepthOfFieldState &hdDepthOfFieldState() {
    static HdDepthOfFieldState *state = new HdDepthOfFieldState();
    return *state;
}
Graphics::Surface *hdDepthOfFieldCheckbox[2] = {nullptr, nullptr};
// Options-book row on the free right page, below the table of contents, in
// original 640x480 coordinates. The left page is full of original options.
const int kHdDepthOfFieldRowY = 330, kHdDepthOfFieldBoxX = 420, kHdDepthOfFieldStep = 58;

// Implemented by the shared Scene Look configuration below this include.
int hdSceneLookValue(int room, int control);
int hdSceneLookEditRoom(int room);
void hdSaveSceneFocus(int room, int level, const HdDepthOfField::Tuning &tuning, unsigned int changed, bool reset = false);

HdDepthOfField::Tuning hdDepthOfFieldTuning(int room) {
    return HdDepthOfField::tuning(hdSceneLookValue(room, HdSceneLook::kBlur),
        hdSceneLookValue(room, HdSceneLook::kEdge), hdSceneLookValue(room, HdSceneLook::kIntensity),
        hdSceneLookValue(room, HdSceneLook::kDepth));
}
}

int ScummEngine::hdDepthOfFieldLevel() const {
    return hdSceneLookValue(_currentRoom, HdSceneLook::kFocus);
}

// Step 1b: runs right after the background copy, before native foreground,
// objects, costumes and UI, which therefore all stay sharp on top.
void ScummEngine::renderHDDepthOfField(int backgroundX, int visW, int visH) {
    HdDepthOfFieldState &dof = hdDepthOfFieldState();
    dof.active = false;
    const int level = hdDepthOfFieldLevel();
    const Graphics::Surface &bg = _hdBackgroundSurface;
    if (_game.id != GID_CMI || !level || _currentRoom == 87 || _currentRoom == 92 ||
        _gdi->_numZBuffer <= 1 || !bg.getPixels() || _hdCurrentRoom != _currentRoom ||
        (bg.format.bytesPerPixel != 3 && bg.format.bytesPerPixel != 4))
        return;
    const int scale = MAX(1, (int)_hdScale);
    const HdDepthOfField::Tuning tuning = hdDepthOfFieldTuning(_currentRoom);
    const int radius = HdDepthOfField::radiusTenths(HdDepthOfField::blurTenths(level, tuning), scale);
    if (!tuning.intensity) return;
    // The live mask buffer includes object z-planes and follows the (possibly
    // interpolated) camera, exactly like actor and contact-shadow clipping.
    const int bitOffset = _virtscr[kMainVirtScreen].xstart & 7;
    // Compare packed live z-planes before expanding/feathering. Objects can
    // change a mask without changing room or camera, so geometry alone is not a key.
    const int stride = (visW + bitOffset + 7) / 8, planes = _gdi->_numZBuffer;
    dof.maskScratch.resize(stride * visH * (planes - 1));
    for (int z = 1; z < planes; ++z) {
        const byte *first = getMaskBuffer(0, _screenTop, z);
        for (int y = 0; y < visH; ++y)
            memcpy(dof.maskScratch.data() + ((z - 1) * visH + y) * stride,
                   first + y * _gdi->_numStrips, stride);
    }
    const bool changed = dof.maskWidth != visW || dof.maskHeight != visH || dof.maskOffset != bitOffset ||
        dof.maskEdge != tuning.edge || dof.maskDepth != tuning.depth || dof.masks != dof.maskScratch;
    auto &remaster = HdRemaster::state();
    if (changed) {
        dof.maskWidth = visW; dof.maskHeight = visH; dof.maskOffset = bitOffset;
        dof.maskEdge = tuning.edge; dof.maskDepth = tuning.depth;
        dof.masks.swap(dof.maskScratch);
        ++remaster.coverageGeneration;
    }
    remaster.dof = true; remaster.radius = radius; remaster.intensity = tuning.intensity;
    if (remaster.active) {
        remaster.maskPlanes = planes - 1; remaster.maskOffset = bitOffset;
        remaster.maskEdge = tuning.edge; remaster.maskDepth = MIN(tuning.depth, planes - 1);
        HdRemaster::resize(remaster.coverage, stride, visH * (planes - 1));
        if (remaster.uploadedCoverageGeneration != remaster.coverageGeneration) {
            uint32 *pixels = (uint32 *)remaster.coverage.getPixels();
            for (uint i = 0; i < dof.masks.size(); ++i) pixels[i] = dof.masks[i] | 0xff000000u;
            remaster.uploadedCoverageGeneration = remaster.coverageGeneration;
        }
        return;
    }
    if (dof.cpuCoverageGeneration != remaster.coverageGeneration) {
        dof.cpuCoverageGeneration = remaster.coverageGeneration;
        dof.maskAny = HdDepthOfField::coverage([&](int y, int z) -> const byte * {
            return dof.masks.data() + ((z - 1) * visH + y) * stride;
        }, planes, visW, visH, bitOffset, tuning.edge, dof.coverage, tuning.depth);
        remaster.wideCoverage.resize(dof.coverage.size());
        memcpy(remaster.wideCoverage.data(), dof.coverage.data(), dof.coverage.size());
    }
    if (!dof.maskAny) return;
    if (dof.pixels != bg.getPixels() || dof.room != _hdCurrentRoom || dof.width != bg.w ||
        dof.height != bg.h || dof.radius != radius || dof.scale != scale) {
        const uint32 start = _system->getMillis();
        dof.factor = HdDepthOfField::factor(scale);
        HdDepthOfField::blur((const byte *)bg.getPixels(), bg.pitch, bg.format.bytesPerPixel, bg.w, bg.h,
            dof.factor, radius, dof.blur, dof.blurW, dof.blurH);
        dof.pixels = bg.getPixels();
        dof.room = _hdCurrentRoom;
        dof.width = bg.w;
        dof.height = bg.h;
        dof.radius = radius;
        dof.scale = scale;
        hdPrintf("DEPTH-OF-FIELD room=%d level=%d radius=%d planes=%d blur=%dx%d factor=%d built=%ums",
            dof.room, level, radius, _gdi->_numZBuffer, dof.blurW, dof.blurH, dof.factor, _system->getMillis() - start);
    }
    dof.visW = visW;
    dof.visH = visH;
    dof.intensity = tuning.intensity;
    dof.rows.assign(visH, false);
    for (int y = 0; y < visH; ++y)
        for (int x = 0; x < visW && !dof.rows[y]; ++x)
            dof.rows[y] = dof.coverage[y * visW + x] != 0;
    dof.active = true;
    const int height = MIN((int)_hdComposite.h, (int)bg.h);
    for (int y = 0; y < height; ++y) {
        // Bilinear coverage reads native rows ny-1..ny+1 at most.
        const int ny = y / scale;
        if (!dof.rows[MIN(ny, visH - 1)] && !dof.rows[MAX(0, ny - 1)] && !dof.rows[MIN(ny + 1, visH - 1)])
            continue;
        uint32 *dst = (uint32 *)_hdComposite.getBasePtr(0, y);
        for (int x = 0; x < _hdComposite.w; ++x) {
            const int alpha = HdDepthOfField::coverageAt(dof.coverage.data(), visW, visH, scale, x, y) *
                dof.intensity / 100;
            if (!alpha) continue;
            dst[x] = HdDepthOfField::mix(dst[x], HdDepthOfField::sample(dof.blur.data(), dof.blurW, dof.blurH,
                dof.factor, MIN(x + backgroundX, (int)bg.w - 1), y + HdRemaster::state().backgroundY), alpha);
        }
    }
    if (_hdFrameCount % 120 == 0)
        hdPrintf("DEPTH-OF-FIELD frame=%d room=%d level=%d", _hdFrameCount, _currentRoom, level);
}

// Costume passes restore the room painting under transparent sprite pixels;
// keep that restoration consistent with the blurred foreground.
uint32 ScummEngine::hdDepthOfFieldBackground(int x, int y, int backgroundX, uint32 sharp) const {
    const HdDepthOfFieldState &dof = hdDepthOfFieldState();
    if (!dof.active || x < 0 || y < 0 || y >= dof.height || backgroundX < 0 || backgroundX >= dof.width)
        return sharp;
    const int alpha = HdDepthOfField::coverageAt(dof.coverage.data(), dof.visW, dof.visH, dof.scale, x, y) *
        dof.intensity / 100;
    if (!alpha) return sharp;
    return HdDepthOfField::mix(sharp, HdDepthOfField::sample(dof.blur.data(), dof.blurW, dof.blurH,
        dof.factor, backgroundX, y + HdRemaster::state().backgroundY), alpha);
}

bool ScummEngine::handleHDDepthOfFieldEvent(const Common::Event &event) {
    if (_hdDepthOfFieldMouseDown && event.type == Common::EVENT_LBUTTONUP) {
        _hdDepthOfFieldMouseDown = false; _leftBtnPressed = 0; return true;
    }
    // Playtest tuning hotkeys during gameplay; unused by the original game.
    //   [ ] blur   shift+[ ] intensity   ; ' edge softness   shift+; ' depth
    //   \ on/off   shift+\ reset
    if (event.type == Common::EVENT_KEYDOWN && ConfMan.hasKey("playtest_session") && _game.id == GID_CMI &&
        _currentRoom != 92 && _currentRoom != 87 && !isSmushActive() &&
        !(event.kbd.flags & (Common::KBD_CTRL | Common::KBD_ALT | Common::KBD_META))) {
        const bool shift = (event.kbd.flags & Common::KBD_SHIFT) != 0;
        int blur = 0, edge = 0, intensity = 0, depth = 0;
        bool toggle = false, reset = false;
        switch (event.kbd.keycode) {
        case Common::KEYCODE_LEFTBRACKET: (shift ? intensity : blur) = -1; break;
        case Common::KEYCODE_RIGHTBRACKET: (shift ? intensity : blur) = 1; break;
        case Common::KEYCODE_SEMICOLON: (shift ? depth : edge) = -1; break;
        case Common::KEYCODE_QUOTE: (shift ? depth : edge) = 1; break;
        case Common::KEYCODE_BACKSLASH: (shift ? reset : toggle) = true; break;
        default: return false;
        }
        HdDepthOfFieldState &dof = hdDepthOfFieldState();
        const int room = hdSceneLookEditRoom(_currentRoom);
        int level = hdSceneLookValue(room, HdSceneLook::kFocus);
        HdDepthOfField::Tuning tuning = hdDepthOfFieldTuning(room);
        unsigned int changed = 0;
        if (reset) {
            for (int c = HdSceneLook::kFocus; c < HdSceneLook::kControls; ++c) changed |= 1u << c;
        } else if (toggle) {
            if (level) dof.lastLevel = level;
            level = level ? 0 : dof.lastLevel;
            changed = 1u << HdSceneLook::kFocus;
        } else {
            if (!level) { level = dof.lastLevel; changed |= 1u << HdSceneLook::kFocus; }
            tuning = HdDepthOfField::step(level, tuning, blur, edge, intensity, depth);
            changed |= 1u << (blur ? HdSceneLook::kBlur : edge ? HdSceneLook::kEdge : intensity ? HdSceneLook::kIntensity : HdSceneLook::kDepth);
        }
        hdSaveSceneFocus(room, level, tuning, changed, reset);
        dof.hudUntil = _system->getMillis() + 4000;
        return true;
    }
    if (!hasHDFontSizeMenu() || !ConfMan.hasKey("playtest_session")) return false;
    if (event.type != Common::EVENT_LBUTTONDOWN) return false;
    const int x = event.mouse.x / _hdScale, y = event.mouse.y / _hdScale;
    int level = -1;
    for (int i = 0; i < 3; ++i)
        if (Common::Rect(kHdDepthOfFieldBoxX + kHdDepthOfFieldStep * i, kHdDepthOfFieldRowY,
                kHdDepthOfFieldBoxX + kHdDepthOfFieldStep * (i + 1) - 4, kHdDepthOfFieldRowY + 24).contains(x, y))
            level = i;
    if (level < 0) return false;
    _hdDepthOfFieldMouseDown = true; _leftBtnPressed = 0;
    // The options book is game-wide. Room overrides remain independent.
    HdDepthOfField::Tuning tuning = hdDepthOfFieldTuning(0);
    tuning.blurTenths = 0;
    hdSaveSceneFocus(0, level, tuning, (1u << HdSceneLook::kFocus) | (1u << HdSceneLook::kBlur));
    _fullRedraw = true;
    return true;
}

// Playtest overlay text: a darkened box with one line per entry, in the game's
// NUT font. `highlight` (optional) marks lines drawn in the accent color; a
// tab moves to column `tab`. Coordinates and sizes are in original 640x480 pixels.
static void drawHDOverlayText(Graphics::Surface &dest, HdFontManager *fonts, CharsetRenderer *charset, int scale,
                              int left, int top, int width, const Common::String *lines, int count,
                              const bool *highlight = nullptr, int sizePercent = 55, int lineHeight = 19, int tab = 0) {
    left *= scale; top *= scale;
    width = MIN((int)dest.w - left, width * scale);
    const int height = (count * lineHeight + 6) * scale;
    for (int y = top; y < top + height && y < dest.h; ++y) {
        uint32 *row = (uint32 *)dest.getBasePtr(0, y);
        for (int x = MAX(0, left); x < left + width; ++x) {
            byte a, r, g, b;
            dest.format.colorToARGB(row[x], a, r, g, b);
            row[x] = dest.format.ARGBToColor(255, r * 2 / 5, g * 2 / 5, b * 2 / 5);
        }
    }
    const int previous = fonts->getSizePercent();
    fonts->setSizePercent(sizePercent);
    const int oldFont = charset->getCurID();
    charset->setCurID(3);
    const CharsetRendererNut *font = dynamic_cast<const CharsetRendererNut *>(charset);
    for (int i = 0; i < count; ++i) {
        const bool accent = highlight && highlight[i];
        int x100 = (left + 8 * scale) * 100;
        for (uint c = 0; c < lines[i].size(); ++c) {
            const byte chr = (byte)lines[i][c];
            if (chr == '\t') {
                x100 = MAX(x100, (left + (8 + tab) * scale) * 100);
                continue;
            }
            fonts->drawChar(3, chr, dest, x100 / 100, top + (4 + lineHeight * i) * scale,
                255, accent ? 200 : 238, accent ? 90 : 200);
            x100 += (font ? font->getCharWidth100(chr) : charset->getCharWidth(chr) * 100) * scale;
        }
    }
    charset->setCurID(oldFont);
    fonts->setSizePercent(previous);
}

// Readout for a few seconds after each tuning hotkey, over the game view.
static void drawHDDepthOfFieldHud(Graphics::Surface &dest, HdFontManager *fonts, CharsetRenderer *charset, int scale,
                                  int level, const HdDepthOfField::Tuning &tuning, int planes, int editRoom) {
    const int tenths = HdDepthOfField::blurTenths(level ? level : 1, tuning);
    // The game font has no pipe or braces; spell out the shifted keys.
    const Common::String lines[3] = {
        level ? Common::String::format("Focus  blur %d.%d px   edge %d px   intensity %d%%   depth %d of %d",
                    tenths / 10, tenths % 10, tuning.edge, tuning.intensity,
                    MIN(tuning.depth, MAX(1, planes - 1)), MAX(0, planes - 1))
              : Common::String("Focus  off"),
        "[ ] blur     shift [ ] intensity     ; ' edge     shift ; ' depth",
        editRoom ? Common::String::format("Room %d   \\ on/off   shift \\ inherit   U look", editRoom)
                 : Common::String("Global   \\ on/off   shift \\ reset   U look")};
    drawHDOverlayText(dest, fonts, charset, scale, 8, 8, 440, lines, 3);
}

void ScummEngine::drawHDDepthOfFieldMenu() {
    if (_game.id == GID_CMI && _currentRoom != 92 && _hdFontManager && _hdFontManager->hasFont(3) &&
        hdDepthOfFieldState().hudUntil > _system->getMillis())
        drawHDDepthOfFieldHud(_hdComposite, _hdFontManager, _charset, MAX(1, (int)_hdScale),
            hdSceneLookValue(hdSceneLookEditRoom(_currentRoom), HdSceneLook::kFocus),
            hdDepthOfFieldTuning(hdSceneLookEditRoom(_currentRoom)), _gdi->_numZBuffer, hdSceneLookEditRoom(_currentRoom));
    if (!hasHDFontSizeMenu() || !ConfMan.hasKey("playtest_session")) return;
    const int previous = _hdFontManager->getSizePercent();
    _hdFontManager->setSizePercent(65);
    const int scale = _hdScale;
    const int oldFont = _charset->getCurID();
    _charset->setCurID(3);
    const CharsetRendererNut *font = dynamic_cast<const CharsetRendererNut *>(_charset);
    auto label = [&](const char *text, int x) {
        int x100 = x * 100;
        for (const char *c = text; *c; ++c) {
            _hdFontManager->drawChar(3, *c, _hdComposite, x100 / 100, kHdDepthOfFieldRowY * scale, 25, 12, 3);
            x100 += (font ? font->getCharWidth100(*c) : _charset->getCharWidth(*c) * 100) * scale;
        }
    };
    static const char *const names[] = {"Off", "Low", "High"};
    label("Focus", (kHdDepthOfFieldBoxX - 50) * scale);
    for (int i = 0; i < 3; ++i)
        label(names[i], (kHdDepthOfFieldBoxX + kHdDepthOfFieldStep * i + 24) * scale);
    // Reuse the original game's checkbox sprites, preserving the parchment.
    const int selected = hdDepthOfFieldLevel();
    for (int i = 0; i < 3; ++i) {
        const int state = selected == i ? 1 : 0;
        if (!hdDepthOfFieldCheckbox[state]) {
            Common::FSNode node(Common::Path(ConfMan.get("hd_aspect_ui_path") +
                    Common::String::format("/0092_saveload-checkbox_%04d.png", state)));
            Common::SeekableReadStream *file = node.createReadStream();
            if (!file) continue;
            Image::PNGDecoder decoder;
            const bool loaded = decoder.loadStream(*file);
            delete file;
            if (!loaded || !decoder.getSurface()) continue;
            hdDepthOfFieldCheckbox[state] = decoder.getSurface()->convertTo(Graphics::PixelFormat::createFormatRGBA32(),
                    decoder.getPalette().data(), decoder.getPalette().size());
        }
        const Graphics::Surface *sprite = hdDepthOfFieldCheckbox[state];
        for (int y = 0; y < sprite->h; ++y) for (int x = 0; x < sprite->w; ++x) {
            byte a, r, g, b;
            sprite->format.colorToARGB(*(const uint32 *)sprite->getBasePtr(x, y), a, r, g, b);
            if (!a || (r == 0 && g == 255 && b == 0)) continue;
            const int left = kHdDepthOfFieldBoxX + kHdDepthOfFieldStep * i + x, top = kHdDepthOfFieldRowY + y;
            _hdComposite.fillRect(Common::Rect(left * scale, top * scale, (left + 1) * scale, (top + 1) * scale),
                _hdComposite.format.RGBToColor(r, g, b));
        }
    }
    _charset->setCurID(oldFont);
    _hdFontManager->setSizePercent(previous);
}
