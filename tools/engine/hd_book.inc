// Room 92 is the options book. Its Save/Load spread is object 1400, a full
// 640x480 native image drawn over the options spread. The HD painting stands
// in for both spreads; only what the book draws on top of them remains native.
// The options spread is the only one with the gutter bookmark (object 1388).
// Save/Load pages alternate between the spread image (1400) on odd pages and
// the room's own blank pages on even ones.
bool ScummEngine::hdBookOptionsPage() const {
    return _game.id == GID_CMI && _currentRoom == 92 && _objectStateTable &&
        _numGlobalObjects > 1388 && _objectStateTable[1388] == 1;
}

bool ScummEngine::hdBookSpreadShown() const {
    return _game.id == GID_CMI && _currentRoom == 92 && _objectStateTable &&
        _numGlobalObjects > 1400 && _objectStateTable[1400] == 1;
}

// Exact native pixels of the Save/Load spread, treated as background so slot
// frames, thumbnails and highlights still replace the HD painting. Each visit
// is validated against the live screen; a mismatch keeps the native spread.
const byte *ScummEngine::hdBookSpread() {
    VirtScreen *vs = &_virtscr[kMainVirtScreen];
    if (!hdBookSpreadShown() || _screenWidth != 640 || _screenHeight != 480 || _screenTop != 0 ||
        vs->xstart != 0 || vs->h < 480 || vs->pitch < 640) {
        _hdBookSpreadChecked = false;
        return nullptr;
    }
    if (_hdBookSpreadState == 0) {
        _hdBookSpreadState = -1;
        Common::SeekableReadStream *file = nullptr;
        if (ConfMan.hasKey("hd_aspect_ui_path")) {
            Common::FSNode node(Common::Path(ConfMan.get("hd_aspect_ui_path") +
                "/0092_saveload-alternate-anim-object_0000.png"));
            file = node.createReadStream();
        }
        if (file) {
            Image::PNGDecoder decoder;
            const Graphics::Surface *image = decoder.loadStream(*file) ? decoder.getSurface() : nullptr;
            if (image && image->w == 640 && image->h == 480 && image->format.bytesPerPixel == 1) {
                _hdBookSpread.resize(640 * 480);
                for (int y = 0; y < 480; ++y)
                    memcpy(&_hdBookSpread[y * 640], image->getBasePtr(0, y), 640);
                _hdBookSpreadState = 1;
            }
            delete file;
        }
        if (_hdBookSpreadState != 1)
            warning("HD book: Save/Load spread image unavailable; keeping the native spread");
    }
    if (_hdBookSpreadState != 1) return nullptr;
    if (!_hdBookSpreadChecked) {
        int same = 0;
        for (int y = 0; y < 480; ++y) {
            const byte *row = vs->getPixels(0, y), *spread = &_hdBookSpread[y * 640];
            for (int x = 0; x < 640; ++x) same += row[x] == spread[x];
        }
        // Slot frames, thumbnails and highlights cover a few percent at most.
        // Retry next frame otherwise (the spread may not be drawn yet).
        if (same < 640 * 480 * 9 / 10) return nullptr;
        _hdBookSpreadChecked = true;
    }
    return _hdBookSpread.data();
}

// The 16:9 painting carries its own ribbon tips; the original gutter bookmark
// ribbon (object 1388) is not drawn over it.
bool ScummEngine::hdBookHidesObject(int object) const {
    return object == 1388 && _game.id == GID_CMI && _currentRoom == 92 && _hdScale > 1 &&
        ConfMan.hasKey("playtest_session");
}

// Options spread layout (hd_book_layout.h): the book's scripts keep their
// original coordinates; queued items are drawn translated, and the pointer is
// translated back before the scripts read it.
bool ScummEngine::hdBookLaidOut() const {
    return _game.id == GID_CMI && _currentRoom == 92 && _hdScale > 1 && ConfMan.hasKey("playtest_session");
}

bool ScummEngine::hdBookLayoutActive() const {
    return hdBookLaidOut() && hdBookOptionsPage();
}

bool ScummEngine::hdBookPlace(int &x, int &y) const {
    if (_hdBookInjecting || !hdBookLaidOut()) return true;
    if (hdBookOptionsPage()) return HdBookLayout::place(x, y);
    HdBookLayout::placeSlot(x, y);
    return true;
}

void ScummEngine::hdBookScriptMouse() {
    if (!hdBookLaidOut()) {
        _hdBookCapture = HdBookLayout::kFree;
        _hdBookLoad = -1;
        return;
    }
    const byte mouseDown = 1, mouseClicked = 2; // msDown, msClicked in input.cpp
    int x = _mouse.x, y = _mouse.y;
    if (!hdBookOptionsPage()) {
        _hdBookCapture = HdBookLayout::kFree;
        HdBookLayout::slotToScript(x, y);
    } else {
        // Which spread the table of contents opens: Save Game or Load Game.
        if (_leftBtnPressed & (mouseDown | mouseClicked)) {
            const int entry = HdBookLayout::targetAt(x, y);
            if (entry == HdBookLayout::kSaveEntry || entry == HdBookLayout::kLoadEntry)
                _hdBookLoad = entry == HdBookLayout::kLoadEntry;
        }
        HdBookLayout::toScript(x, y, _hdBookCapture, (_leftBtnPressed & mouseDown) != 0);
    }
    VAR(VAR_VIRT_MOUSE_X) = x + _virtualMouse.x - _mouse.x;
    VAR(VAR_VIRT_MOUSE_Y) = y + _virtualMouse.y - _mouse.y;
    VAR(VAR_MOUSE_X) = x;
    VAR(VAR_MOUSE_Y) = y;
}

// Text Size: an extra slider made of the book's own bar, knob and label,
// queued once per frame beside the scripts' sliders.
void ScummEngine_v7::enqueueHDBookControls() {
    if (!hdBookLayoutActive() || !hasHDFontSizeMenu()) return;
    bool bookSliders = false;
    for (int i = 0; i < _blastObjectQueuePos; ++i) {
        const BlastObject &queued = _blastObjectQueue[i];
        if (queued.number == 1389 && queued.rect.top == HdBookLayout::kSizeBarY + _screenTop) return;
        bookSliders |= queued.number == 1389;
    }
    if (!bookSliders) return;
    _hdBookInjecting = true;
    enqueueObject(1389, HdBookLayout::kSliderLeft, HdBookLayout::kSizeBarY, 0, 0, 0xFF, 0xFF, 1, 0);
    enqueueObject(1390, HdBookLayout::sizeKnobX(_hdFontManager->getSizePercent()), HdBookLayout::kSizeKnobY, 0, 0, 0xFF, 0xFF, 1, 0);
    enqueueText((const byte *)HdLanguage::text(_hdLanguage, HdLanguage::kTextSize), HdBookLayout::kSliderLeft,
        HdBookLayout::kSizeLabelY, 0, 3, kStyleAlignLeft);
    // Language row: checked, unchecked, or greyed out like the original's
    // disabled options when no pack is installed; the label turns red on hover.
    for (int i = 0; i < HdBookLayout::kLanguageCount; ++i) {
        const bool offered = hdLanguageOffered(i), hover = offered && HdBookLayout::languageAt(_mouse.x, _mouse.y) == i;
        const int x = HdBookLayout::kLanguageX[i], y = HdBookLayout::kLanguageY;
        enqueueObject(1391, x, y, 0, 0, 0xFF, 0xFF, !offered ? 3 : _hdLanguage == i ? 2 : 1, 3);
        enqueueText((const byte *)HdLanguage::text(_hdLanguage, i ? HdLanguage::kSpanishName : HdLanguage::kEnglishName),
            x + HdBookLayout::kLanguageLabelDx, y + HdBookLayout::kLanguageLabelDy, !offered ? 96 : hover ? 9 : 0, 3, kStyleAlignLeft);
    }
    _hdBookInjecting = false;
}

// Pack availability is checked on the file system at most every two seconds.
bool ScummEngine::hdLanguageOffered(int language) {
    const uint32 now = _system->getMillis();
    if (_hdLanguageOffered < 0 || now - _hdLanguageCheckedAt > 2000) {
        _hdLanguageOffered = 0;
        for (int i = 0; i < HdLanguage::kCount; ++i)
            if (hdLanguageAvailable(i)) _hdLanguageOffered |= 1 << i;
        _hdLanguageCheckedAt = now;
    }
    return language >= 0 && language < HdLanguage::kCount && (_hdLanguageOffered >> language & 1);
}

// Save thumbnails (hd_save_thumbs.inc). Decoded PNGs are cached by name, so
// hover brightness changes and page turns do not decode them again.
bool ScummEngine::hdBookImage(const Common::String &name, HdBookImage &out) {
    for (uint i = 0; i < _hdBookImages.size(); ++i) {
        if (_hdBookImages[i].name != name) continue;
        out = _hdBookImages[i];
        return true;
    }
    Common::InSaveFile *file = _saveFileMan->openForLoading(name);
    if (!file) return false;
    Image::PNGDecoder decoder;
    const bool loaded = decoder.loadStream(*file) && decoder.getSurface();
    delete file;
    if (!loaded) return false;
    Graphics::Surface *rgba = decoder.getSurface()->convertTo(Graphics::PixelFormat(4, 8, 8, 8, 8, 0, 8, 16, 24),
        decoder.getPalette().data(), decoder.getPalette().size());
    out.name = name; out.w = rgba->w; out.h = rgba->h;
    out.pixels.resize(out.w * out.h);
    for (int y = 0; y < out.h; ++y)
        memcpy(&out.pixels[y * out.w], rgba->getBasePtr(0, y), out.w * 4);
    rgba->free(); delete rgba;
    if (_hdBookImages.size() >= 12) _hdBookImages.remove_at(0);
    _hdBookImages.push_back(out);
    return true;
}

// The HD picture is prepared at stamp time (scaled, with the book's dimming);
// each frame only copies it where the native stamp is still visible.
void ScummEngine::addHDBookStamp(const Common::Rect &box, int brightness, const HdBookImage *image) {
    for (uint i = 0; i < _hdBookStamps.size(); ++i)
        if (_hdBookStamps[i].box == box) { _hdBookStamps.remove_at(i); break; }
    VirtScreen *vs = &_virtscr[kMainVirtScreen];
    const int scale = _hdScale;
    if (!image || !image->w || !image->h || box.isEmpty() || box.left < 0 || box.top < 0 ||
        box.right > _screenWidth || box.bottom > MIN<int>(_screenHeight, vs->h - _screenTop))
        return;
    HdBookStamp stamp;
    stamp.box = box;
    const int w = box.width(), h = box.height(), hdW = w * scale, hdH = h * scale;
    stamp.native.resize(w * h);
    for (int y = 0; y < h; ++y)
        memcpy(&stamp.native[y * w], vs->getPixels(box.left, _screenTop + box.top + y), w);
    stamp.pixels.resize(hdW * hdH);
    const uint32 light = CLIP(brightness, 0, 255);
    for (int y = 0; y < hdH; ++y) {
        const int sy = MAX(0, ((2 * y + 1) * image->h - hdH) * 256 / (2 * hdH));
        const int y0 = MIN(image->h - 1, sy >> 8), y1 = MIN(image->h - 1, y0 + 1), fy = sy & 255;
        for (int x = 0; x < hdW; ++x) {
            const int sx = MAX(0, ((2 * x + 1) * image->w - hdW) * 256 / (2 * hdW));
            const int x0 = MIN(image->w - 1, sx >> 8), x1 = MIN(image->w - 1, x0 + 1), fx = sx & 255;
            const uint32 a = image->pixels[y0 * image->w + x0], b = image->pixels[y0 * image->w + x1];
            const uint32 c = image->pixels[y1 * image->w + x0], d = image->pixels[y1 * image->w + x1];
            uint32 color = 0xff000000u;
            for (int shift = 0; shift < 24; shift += 8) {
                const uint32 top = (a >> shift & 255) * (256 - fx) + (b >> shift & 255) * fx;
                const uint32 bottom = (c >> shift & 255) * (256 - fx) + (d >> shift & 255) * fx;
                color |= (((top * (256 - fy) + bottom * fy) >> 16) * light / 255) << shift;
            }
            stamp.pixels[y * hdW + x] = color;
        }
    }
    _hdBookStamps.push_back(stamp);
}

void ScummEngine::drawHDBookStamps() {
    if (_currentRoom != 92 || _hdScale <= 1 || !_hdComposite.getPixels()) {
        _hdBookStamps.clear();
        if (_currentRoom != 92) _hdBookImages.clear();
        return;
    }
    VirtScreen *vs = &_virtscr[kMainVirtScreen];
    const int scale = _hdScale;
    for (uint i = 0; i < _hdBookStamps.size();) {
        const HdBookStamp &stamp = _hdBookStamps[i];
        const int w = stamp.box.width(), h = stamp.box.height(), hdW = w * scale;
        int same = 0;
        for (int y = 0; y < h; ++y) {
            const byte *row = vs->getPixels(stamp.box.left, _screenTop + stamp.box.top + y);
            for (int x = 0; x < w; ++x) same += row[x] == stamp.native[y * w + x];
        }
        if (same * 5 < w * h * 3) { // Page turned or slot redrawn.
            _hdBookStamps.remove_at(i);
            continue;
        }
        // Frames, highlights and text drawn over the native stamp stay on top.
        for (int y = 0; y < h; ++y) {
            const byte *row = vs->getPixels(stamp.box.left, _screenTop + stamp.box.top + y);
            for (int x = 0; x < w; ++x) {
                if (row[x] != stamp.native[y * w + x]) continue;
                for (int dy = 0; dy < scale; ++dy) {
                    const uint32 *src = &stamp.pixels[(y * scale + dy) * hdW + x * scale];
                    memcpy(_hdComposite.getBasePtr((stamp.box.left + x) * scale, (stamp.box.top + y) * scale + dy), src, scale * 4);
                }
            }
        }
        ++i;
    }
}

// Load page with the autosave tile (hd_autosave.h). Known from the table of
// contents entry the player clicked; otherwise the original numbering stays.
bool ScummEngine::hdBookLoadShift() const {
    return hdBookLaidOut() && _hdBookLoad == 1;
}

int ScummEngine::hdBookLoadSlot(int tile) const {
    return hdBookLoadShift() && tile > 0 ? HdAutosave::loadSlot(tile) : tile;
}

int ScummEngine::hdBookStampSlot(int tile) const {
    if (!hdBookLoadShift() || tile <= 0) return tile;
    const int slot = HdAutosave::loadSlot(tile);
    return slot ? slot : HdAutosave::kStampSlot;
}

// Tile numbers show the slot they load; the autosave tile has none. The text
// is the converted message, rewritten in place.
bool ScummEngine::hdBookNumber(byte *text, int x, int y) const {
    if (!hdBookLoadShift() || hdBookOptionsPage() || !HdBookLayout::slotNumberAt(x, y))
        return true;
    int number = 0, digits = 0;
    for (; text[digits]; ++digits) {
        if (text[digits] < '0' || text[digits] > '9' || digits > 2) return true;
        number = number * 10 + text[digits] - '0';
    }
    if (!digits) return true;
    number = HdAutosave::loadSlot(number);
    if (number <= 0) return false;
    char reversed[4];
    int count = 0;
    do { reversed[count++] = (char)('0' + number % 10); number /= 10; } while (number && count < 3);
    for (int i = 0; i < count; ++i) text[i] = reversed[count - 1 - i];
    text[count] = 0;
    return true;
}

bool ScummEngine::hdBookSavegameName(int tile, Common::String &name) {
    const int slot = hdBookLoadSlot(tile);
    if (slot < 0 || !getSavegameName(slot, name)) return false;
    if (slot != 0 || !hdBookLoadShift()) return true;
    Common::String description;
    Graphics::Surface *thumbnail = nullptr;
    SaveStateMetaInfos infos = {};
    SaveStateMetaInfos *saved = &infos;
    long age = -1;
    if (querySaveMetaInfos(_targetName.c_str(), 0, _game.heversion, description, thumbnail, saved) && saved) {
        TimeDate now;
        _system->getTimeAndDate(now);
        const uint32 today = ((now.tm_mday & 0xFF) << 24) | (((now.tm_mon + 1) & 0xFF) << 16) | ((now.tm_year + 1900) & 0xFFFF);
        age = HdAutosave::minutes(today, ((now.tm_hour & 0xFF) << 8) | (now.tm_min & 0xFF)) -
            HdAutosave::minutes(saved->date, saved->time);
    }
    if (thumbnail) { thumbnail->free(); delete thumbnail; }
    char text[48];
    HdLanguage::autosaveLabel(_hdLanguage, age, text, sizeof(text));
    name = text;
    return true;
}
