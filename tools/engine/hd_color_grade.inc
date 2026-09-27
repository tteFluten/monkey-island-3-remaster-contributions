// Included in gfx.cpp after hd_depth_of_field.inc. Global Scene Look defaults,
// individual room overrides, and the editing panel. Settings are kept in
// the authoring file named by hd_color_grades_path, separate from game saves.
namespace {
struct HdColorGradeState {
    bool loaded = false;
    Common::String path, error;
    HdSceneLook::Settings settings;
    Common::String source;
    bool writable = true, legacy = false, editGlobal = false;
    // Curves for the grade currently applied.
    int lutRoom = -1;
    HdColorGrade::Grade lutGrade;
    HdColorGrade::Lut lut;
    // Look panel: open state, selected row, before/after comparison.
    bool panel = false, bypass = false, mouseDown = false;
    bool waterPage = false, filmPage = false, shadowPage = false;
    bool waterBypass = false, shadowBypass = false;
    int row = 0;
    uint32 savedAt = 0;
    Common::Array<byte> vignette;
    int maskWidth = 0, maskHeight = 0;
    double maskCanvasWidth = 0;
    HdColorGrade::Grade maskGrade;
};
HdColorGradeState &hdColorGradeState() {
    static HdColorGradeState *state = new HdColorGradeState();
    return *state;
}

// Color first, followed by existing scene depth controls and the vignette.
enum { kLookColor = 0, kLookFocus = HdColorGrade::kVignetteOn,
    kLookBlur, kLookEdge, kLookIntensity, kLookDepth, kLookVignette,
    kLookRows = kLookVignette + 4 };
const int kLookWidth = 300, kLookTop = 8, kLookLineHeight = 16, kLookExtraLines = 9;
static_assert(HdSceneLook::kShadowX - HdSceneLook::kWaterOpacity <= kLookRows, "Water controls must fit panel buffers");
int hdLookRows() {
    const auto &st = hdColorGradeState();
    return st.filmPage ? HdFilm::kControls : st.shadowPage ? HdSceneLook::kControls - HdSceneLook::kShadowX
        : st.waterPage ? (HdWater::fullSurface(HdRemaster::state().room) ? HdSceneLook::kShadowX : HdSceneLook::kWaterReflection)
            - HdSceneLook::kWaterOpacity : kLookRows;
}
int hdLookLine(int row) { return row + 2 + ((hdColorGradeState().waterPage || hdColorGradeState().filmPage || hdColorGradeState().shadowPage) ? 0 : (row >= kLookFocus ? 1 : 0) + (row >= kLookVignette ? 1 : 0)); }

void hdCycleLookPage(int room) {
    auto &st = hdColorGradeState();
    if (st.filmPage) { st.filmPage = false; st.shadowPage = true; }
    else if (st.shadowPage) { st.shadowPage = false; st.waterPage = HdWater::room(room); }
    else if (st.waterPage) st.waterPage = false;
    else st.filmPage = true;
    st.row = 0;
}

Common::String hdReadLookFile(const Common::String &path) {
    Common::String text;
    FILE *file = fopen(path.c_str(), "rb");
    if (!file) return text;
    char buffer[4096]; size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), file)) > 0) text += Common::String(buffer, count);
    fclose(file); return text;
}

void hdLoadColorGrades(HdColorGradeState &st) {
    st.loaded = true;
    // Old INI focus preferences supply global defaults until the first save.
    const char *keys[] = {"hd_depth_of_field", "hd_dof_blur", "hd_dof_edge", "hd_dof_intensity", "hd_dof_depth"};
    for (int c = HdSceneLook::kFocus; c < HdSceneLook::kWaterOpacity; ++c)
        if (ConfMan.hasKey(keys[c - HdSceneLook::kFocus]))
            st.settings.global.set(c, ConfMan.getInt(keys[c - HdSceneLook::kFocus]));
    st.path = ConfMan.hasKey("hd_color_grades_path") ? ConfMan.get("hd_color_grades_path") : "";
    if (st.path.empty()) return;
    st.source = hdReadLookFile(st.path);
    if (st.source.empty()) {
        Common::FSNode node((Common::Path(st.path)));
        if (node.exists()) { st.error = "Could not read look settings"; st.writable = false; }
        return;
    }
    Common::JSONValue *root = Common::JSON::parse(st.source.c_str());
    const int version = root && root->isObject() && root->hasChild("schemaVersion") && root->child("schemaVersion")->isIntegerNumber()
        ? (int)root->child("schemaVersion")->asIntegerNumber() : 1;
    if (!root || !root->isObject() || (version != 1 && version != 2) ||
        !root->hasChild("rooms") || !root->child("rooms")->isObject() ||
        (root->hasChild("global") && !root->child("global")->isObject())) {
        st.error = "Invalid look settings; file kept"; st.writable = false; delete root; return;
    }
    st.legacy = version == 1;
    auto readLayer = [](Common::JSONValue *object, HdSceneLook::Layer &layer) {
        for (int c = 0; c < HdSceneLook::kControls; ++c) {
            const char *key = HdSceneLook::range(c).key;
            if (object->hasChild(key) && object->child(key)->isIntegerNumber())
                layer.set(c, (int)object->child(key)->asIntegerNumber());
        }
    };
    if (root->hasChild("global")) readLayer(root->child("global"), st.settings.global);
    const Common::JSONObject &rooms = root->child("rooms")->asObject();
    for (auto it = rooms.begin(); it != rooms.end(); ++it) {
        char *end = nullptr;
        const long room = strtol(it->_key.c_str(), &end, 10);
        if (!end || *end || room <= 0 || room >= 256 || !HdSceneLook::Settings::roomValid(room) || !it->_value->isObject()) continue;
        auto &layer = st.settings.rooms[room];
        // v1 room grades were complete snapshots, including omitted neutral
        // controls. Preserve that appearance when global defaults are added.
        if (st.legacy) for (int c = 0; c < HdColorGrade::kControls; ++c)
            layer.set(c, HdColorGrade::range(c).neutral);
        readLayer(it->_value, layer);
    }
    delete root;
}

bool hdSaveColorGrades(HdColorGradeState &st) {
    if (!st.writable) return false;
    if (st.path.empty()) { st.error = "No look settings path configured"; return false; }
    if (hdReadLookFile(st.path) != st.source) {
        st.error = "File changed; restart to reload"; return false;
    }
    // Keep the original v1 file before its first migration, without replacing
    // an earlier backup or writing anything merely by opening the panel.
    if (st.legacy) {
        const Common::String backup = st.path + ".v1.bak";
        Common::FSNode node((Common::Path(backup)));
        if (!node.exists()) {
            FILE *file = fopen(backup.c_str(), "wb");
            if (!file) { st.error = "Could not back up look settings"; return false; }
            const bool copied = fwrite(st.source.c_str(), 1, st.source.size(), file) == st.source.size();
            const bool closed = fclose(file) == 0;
            if (!copied || !closed) { remove(backup.c_str()); st.error = "Could not back up look settings"; return false; }
        }
    }
    auto layerText = [](const HdSceneLook::Layer &layer, bool all) {
        Common::String text("{"); bool first = true;
        for (int c = 0; c < HdSceneLook::kControls; ++c) if (all || layer.has(c)) {
            text += Common::String::format("%s\"%s\": %d", first ? "" : ", ", HdSceneLook::range(c).key, layer.value[c]);
            first = false;
        }
        return text + "}";
    };
    Common::String text = "{\n  \"schemaVersion\": 2,\n  \"global\": " + layerText(st.settings.global, true) + ",\n  \"rooms\": {";
    bool first = true;
    for (int room = 1; room < 256; ++room) if (st.settings.rooms[room].mask) {
        text += Common::String::format("%s\n    \"%d\": ", first ? "" : ",", room) + layerText(st.settings.rooms[room], false);
        first = false;
    }
    text += first ? "}\n}\n" : "\n  }\n}\n";
    const Common::String temporary = st.path + ".tmp";
    FILE *file = fopen(temporary.c_str(), "wb");
    if (!file) { st.error = "Could not write look settings"; return false; }
    const bool complete = fwrite(text.c_str(), 1, text.size(), file) == text.size();
    const bool closed = fclose(file) == 0;
    const bool written = complete && closed && rename(temporary.c_str(), st.path.c_str()) == 0;
    if (!written) { remove(temporary.c_str()); st.error = "Could not save look settings"; return false; }
    st.source = text; st.legacy = false; st.error.clear(); st.savedAt = g_system->getMillis(); return true;
}

int hdSceneLookValue(int room, int control) {
    auto &st = hdColorGradeState();
    if (!st.loaded) hdLoadColorGrades(st);
    return st.settings.get(room, control);
}
int hdSceneLookEditRoom(int room) {
    auto &st = hdColorGradeState();
    if (!st.loaded) hdLoadColorGrades(st);
    return st.editGlobal || !HdSceneLook::Settings::roomValid(room) ? 0 : room;
}
void hdSaveSceneFocus(int room, int level, const HdDepthOfField::Tuning &tuning, unsigned int changed, bool reset) {
    auto &st = hdColorGradeState();
    if (!st.loaded) hdLoadColorGrades(st);
    const int values[] = {level, tuning.blurTenths, tuning.edge, tuning.intensity, tuning.depth};
    for (int c = HdSceneLook::kFocus; c < HdSceneLook::kWaterOpacity; ++c) if (changed & (1u << c)) {
        if (reset) st.settings.reset(room, c);
        else st.settings.set(room, c, values[c - HdSceneLook::kFocus]);
    }
    hdSaveColorGrades(st);
}
int hdLookControl(int row) {
    if (hdColorGradeState().waterPage) return HdSceneLook::kWaterOpacity + row;
    if (hdColorGradeState().shadowPage) return HdSceneLook::kShadowX + row;
    return row < kLookFocus ? row : row < kLookVignette ? HdSceneLook::kFocus + row - kLookFocus
        : HdColorGrade::kVignetteOn + row - kLookVignette;
}
}

Common::Point ScummEngine::hdLookPosition() const {
    const int scale = MAX(1, (int)_hdScale);
    const int width = _hdComposite.w ? _hdComposite.w / scale : _screenWidth;
    const auto &presentation = HdRemaster::state();
    const bool cover = hdAspectRatio() == 169 && (width >= 864 ||
        (ConfMan.hasKey("hd_wide_background_active") && ConfMan.getBool("hd_wide_background_active")));
    const HdAspect::Rect visible = HdAspect::visibleGame(presentation.drawableWidth,
        presentation.drawableHeight, hdAspectRatio(), width, cover);
    return Common::Point(MAX(visible.x + 8, visible.x + visible.w - kLookWidth - 8), visible.y + kLookTop);
}

// Grade the composed scene: runs after costumes and native overlays, before
// HD dialogue text, verbs, inventory and the cursor, which keep their colors.
void ScummEngine::renderHDColorGrade() {
    HdColorGradeState &st = hdColorGradeState();
    if (_game.id != GID_CMI) return;
    if (!st.loaded) hdLoadColorGrades(st);
    const int room = _currentRoom;
    if (!HdWater::room(room)) st.waterBypass = false;
    const HdColorGrade::Grade grade = HdSceneLook::Settings::roomValid(room) && !st.bypass
        ? st.settings.grade(room) : HdColorGrade::Grade();
    // The decorative widescreen extension receives the same scene treatment.
    for (int c = 0; c < HdColorGrade::kControls; ++c)
        ConfMan.setInt(Common::String("hd_wide_look_") + HdColorGrade::range(c).key,
            grade.value[c], Common::ConfigManager::kTransientDomain);
    auto &remaster = HdRemaster::state();
    remaster.waterOpacity = st.waterBypass ? 0 : st.settings.get(room, HdSceneLook::kWaterOpacity);
    remaster.waterWaves = st.settings.get(room, HdSceneLook::kWaterWaves);
    remaster.waterSpeed = st.settings.get(room, HdSceneLook::kWaterSpeed);
    remaster.waterDistortion = st.settings.get(room, HdSceneLook::kWaterDistortion);
    remaster.waterHighlights = st.settings.get(room, HdSceneLook::kWaterHighlights);
    remaster.waterReflection = st.settings.get(room, HdSceneLook::kWaterReflection);
    remaster.waterRed = st.settings.get(room, HdSceneLook::kWaterRed);
    remaster.waterGreen = st.settings.get(room, HdSceneLook::kWaterGreen);
    remaster.waterBlue = st.settings.get(room, HdSceneLook::kWaterBlue);
    remaster.waterLight = st.settings.get(room, HdSceneLook::kWaterLight);
    remaster.waterLightDirection = st.settings.get(room, HdSceneLook::kWaterLightDirection);
    remaster.waterGloss = st.settings.get(room, HdSceneLook::kWaterGloss);
    remaster.waterScale = st.settings.get(room, HdSceneLook::kWaterScale);
    if (remaster.active) {
        remaster.grade = grade;
        // Exchange reusable buffers: scene stays intact; following UI draws
        // use a transparent premultiplied surface and bypass all scene effects.
        Graphics::Surface previous = remaster.scene;
        remaster.scene = _hdComposite; _hdComposite = previous;
        HdRemaster::resize(_hdComposite, remaster.scene.w, remaster.scene.h);
        memset(_hdComposite.getPixels(), 0, _hdComposite.pitch * _hdComposite.h);
        remaster.ui = true; remaster.overlay = &_hdComposite;
        ++remaster.generation;
        return;
    }
    if (room < 1 || room > 255 || st.bypass || !_hdComposite.getPixels()) return;
    const bool color = !HdColorGrade::colorIdentity(grade);
    const bool vignette = HdColorGrade::vignetteActive(grade) && !hdInventoryOpen() && room != 92;
    if (!color && !vignette) return;
    if (st.lutRoom != room || memcmp(grade.value, st.lutGrade.value, sizeof(grade.value))) {
        HdColorGrade::build(grade, st.lut);
        st.lutRoom = room;
        st.lutGrade = grade;
    }
    if (vignette) {
        const bool wide = hdAspectRatio() == 169 && (_screenWidth > 640 ||
            (ConfMan.hasKey("hd_wide_background_active") && ConfMan.getBool("hd_wide_background_active")));
        const double canvasWidth = wide ? _hdComposite.h * 16.0 / 9.0 : _hdComposite.w;
        if (st.maskWidth != _hdComposite.w || st.maskHeight != _hdComposite.h || st.maskCanvasWidth != canvasWidth ||
            memcmp(grade.value + HdColorGrade::kVignetteOn, st.maskGrade.value + HdColorGrade::kVignetteOn, 4 * sizeof(int))) {
            st.maskWidth = _hdComposite.w; st.maskHeight = _hdComposite.h;
            st.maskCanvasWidth = canvasWidth; st.maskGrade = grade;
            st.vignette.resize(st.maskWidth * st.maskHeight);
            const double offset = (canvasWidth - st.maskWidth) / 2;
            for (int y = 0; y < st.maskHeight; ++y)
                for (int x = 0; x < st.maskWidth; ++x)
                    st.vignette[y * st.maskWidth + x] = HdColorGrade::vignetteGain(grade, x + offset, y, canvasWidth, st.maskHeight);
        }
    }
    const uint32 start = _system->getMillis();
    for (int y = 0; y < _hdComposite.h; ++y) {
        uint32 *row = (uint32 *)_hdComposite.getBasePtr(0, y);
        for (int x = 0; x < _hdComposite.w; ++x) {
            if (color) row[x] = HdColorGrade::apply(row[x], st.lut);
            if (vignette) row[x] = HdColorGrade::vignettePixel(row[x], st.vignette[y * _hdComposite.w + x]);
        }
    }
    if (_hdFrameCount % 120 == 0)
        hdPrintf("COLOR-GRADE room=%d took=%ums", room, _system->getMillis() - start);
}

bool ScummEngine::handleHDLookEvent(const Common::Event &event) {
    HdColorGradeState &st = hdColorGradeState();
    if (st.mouseDown && event.type == Common::EVENT_LBUTTONUP) {
        st.mouseDown = false; _leftBtnPressed = 0; return true;
    }
    if (_game.id != GID_CMI || !ConfMan.hasKey("playtest_session") || isSmushActive() ||
        _currentRoom == 92 || hdInventoryOpen()) {
        st.panel = false;
        return false;
    }
    if (!HdWater::room(_currentRoom) && st.waterPage) { st.waterPage = false; st.row = 0; st.waterBypass = false; }
    if (!st.loaded) hdLoadColorGrades(st);
    const bool key = event.type == Common::EVENT_KEYDOWN;
    if (key && (event.kbd.flags & (Common::KBD_CTRL | Common::KBD_ALT | Common::KBD_META))) return false;
    if (key && HdWater::room(_currentRoom) && event.kbd.keycode == Common::KEYCODE_w) {
        st.waterPage = !st.panel || !st.waterPage; st.filmPage = st.shadowPage = false;
        st.panel = true; st.row = 0; _fullRedraw = true;
        return true;
    }
    if (key && (event.kbd.keycode == Common::KEYCODE_u || event.kbd.keycode == Common::KEYCODE_BACKQUOTE)) {
        st.panel = !st.panel;
        _fullRedraw = true;
        return true;
    }
    if (!st.panel) return false;
    const int rows = hdLookRows();
    const int steps = key && (event.kbd.flags & Common::KBD_SHIFT) ? 5 : 1;
    int delta = 0;
    bool reset = false;
    _fullRedraw = true;
    if (event.type == Common::EVENT_LBUTTONDOWN) {
        st.mouseDown = true; _leftBtnPressed = 0;
        const int scale = MAX(1, (int)_hdScale);
        const Common::Point position = hdLookPosition();
        const int x = event.mouse.x / scale - position.x, y = event.mouse.y / scale - position.y;
        if (x < 0 || x >= kLookWidth || y < 0 || y >= (rows + kLookExtraLines) * kLookLineHeight) {
            st.panel = false; return true;
        }
        if (y < 4 + kLookLineHeight) { if (!st.filmPage) st.editGlobal = !st.editGlobal; st.savedAt = 0; return true; }
        if (y < 4 + 2 * kLookLineHeight) {
            hdCycleLookPage(_currentRoom); return true;
        }
        int row = -1;
        for (int r = 0; r < rows; ++r)
            if (y >= 4 + hdLookLine(r) * kLookLineHeight && y < 4 + (hdLookLine(r) + 1) * kLookLineHeight) row = r;
        if (row < 0) return true;
        st.row = row;
        if (x >= 244 && x < 266) delta = -1;
        else if (x >= 270 && x < 294) delta = 1;
        else return true;
    } else if (event.type == Common::EVENT_RBUTTONDOWN || event.type == Common::EVENT_RBUTTONUP) {
        _rightBtnPressed = 0; return true;
    } else if (!key) return false;
    else switch (event.kbd.keycode) {
    case Common::KEYCODE_TAB: hdCycleLookPage(_currentRoom); return true;
    case Common::KEYCODE_r:
        if (st.filmPage) { HdFilm::reset(); st.savedAt = _system->getMillis(); return true; }
        if (st.shadowPage) {
            const int room = hdSceneLookEditRoom(_currentRoom);
            for (int c = HdSceneLook::kShadowX; c < HdSceneLook::kControls; ++c)
                st.settings.reset(room, c);
            st.shadowBypass = false;
            hdSaveColorGrades(st);
        } else if (!st.editGlobal && HdSceneLook::Settings::roomValid(_currentRoom)) {
            if (st.waterPage) {
                for (int c = HdSceneLook::kWaterOpacity; c < HdSceneLook::kShadowX; ++c)
                    st.settings.reset(_currentRoom, c);
            } else st.settings.rooms[_currentRoom].mask = 0;
            hdSaveColorGrades(st);
        }
        return true;
    case Common::KEYCODE_g: if (!st.filmPage) st.editGlobal = !st.editGlobal; st.savedAt = 0; return true;
    case Common::KEYCODE_UP: st.row = (st.row + rows - 1) % rows; return true;
    case Common::KEYCODE_DOWN: st.row = (st.row + 1) % rows; return true;
    case Common::KEYCODE_LEFT: delta = -steps; break;
    case Common::KEYCODE_RIGHT: delta = steps; break;
    case Common::KEYCODE_BACKSPACE: case Common::KEYCODE_DELETE: reset = true; break;
    case Common::KEYCODE_b:
        if (st.filmPage) { HdFilm::state().bypass = !HdFilm::state().bypass; ++HdFilm::state().revision; }
        else if (st.waterPage) st.waterBypass = !st.waterBypass;
        else if (st.shadowPage) st.shadowBypass = !st.shadowBypass;
        else st.bypass = !st.bypass;
        return true;
    case Common::KEYCODE_ESCAPE: st.panel = false; return true;
    case Common::KEYCODE_o: case Common::KEYCODE_F5: case Common::KEYCODE_i:
        st.panel = false; return false;
    default: return true;
    }
    if (st.filmPage) {
        const auto &r = HdFilm::range(st.row);
        HdFilm::set(st.row, reset ? r.neutral : HdFilm::get(st.row) + delta * r.step);
        st.savedAt = _system->getMillis();
        return true;
    }
    const int room = hdSceneLookEditRoom(_currentRoom), control = hdLookControl(st.row);
    if (st.shadowPage) st.shadowBypass = false;
    if (reset) {
        st.settings.reset(room, control); // Room reset means inheritance, including explicit Off.
    } else if (control < HdSceneLook::kFocus || control >= HdSceneLook::kWaterOpacity) {
        st.settings.set(room, control, st.settings.get(room, control) + delta * HdSceneLook::range(control).step);
    } else {
        auto &dof = hdDepthOfFieldState();
        int level = st.settings.get(room, HdSceneLook::kFocus);
        if (control == HdSceneLook::kFocus) {
            level = HdDepthOfField::clampInt(level + delta, 0, 2);
            st.settings.set(room, control, level);
            if (level) dof.lastLevel = level;
        } else {
            if (!level) { level = dof.lastLevel; st.settings.set(room, HdSceneLook::kFocus, level); }
            const auto tuning = hdDepthOfFieldTuning(room);
            const auto next = HdDepthOfField::step(level, tuning,
                control == HdSceneLook::kBlur ? delta : 0, control == HdSceneLook::kEdge ? delta : 0,
                control == HdSceneLook::kIntensity ? delta : 0, control == HdSceneLook::kDepth ? delta : 0);
            const int values[] = {next.blurTenths, next.edge, next.intensity, next.depth};
            st.settings.set(room, control, values[control - HdSceneLook::kBlur]);
        }
    }
    hdSaveColorGrades(st);
    return true;
}

void ScummEngine::drawHDLookPanel() {
    HdColorGradeState &st = hdColorGradeState();
    if (_currentRoom == 92 || isSmushActive() || hdInventoryOpen()) st.panel = false;
    if (!st.panel || _game.id != GID_CMI || !_hdFontManager || !_hdFontManager->hasFont(3) || !_hdComposite.getPixels())
        return;
    const int room = _currentRoom;
    if (!HdWater::room(room) && st.waterPage) { st.waterPage = false; st.row = 0; st.waterBypass = false; }
    const int rows = hdLookRows();
    if (!st.loaded) hdLoadColorGrades(st);
    const int editingRoom = st.filmPage ? 0 : hdSceneLookEditRoom(room);
    const HdColorGrade::Grade grade = st.settings.grade(editingRoom);
    const int level = st.settings.get(editingRoom, HdSceneLook::kFocus);
    const HdDepthOfField::Tuning tuning = hdDepthOfFieldTuning(editingRoom);
    const int tenths = HdDepthOfField::blurTenths(level ? level : 1, tuning);
    const int planes = MAX(0, _gdi->_numZBuffer - 1);
    static const char *const levels[] = {"Off", "Low", "High"};
    Common::String values[kLookRows];
    values[kLookFocus] = levels[level];
    values[kLookBlur] = Common::String::format("%d.%d px", tenths / 10, tenths % 10);
    values[kLookEdge] = Common::String::format("%d px", tuning.edge);
    values[kLookIntensity] = Common::String::format("%d%%", tuning.intensity);
    values[kLookDepth] = planes ? Common::String::format("%d of %d", MIN(tuning.depth, planes), planes) : Common::String("no z-planes");
    for (int c = 0; c < HdColorGrade::kVignetteOn; ++c)
        values[c] = c == HdColorGrade::kGamma
            ? Common::String::format("%d.%02d", grade.value[c] / 100, grade.value[c] % 100)
            : Common::String::format("%+d", grade.value[c]);
    values[kLookVignette] = grade.value[HdColorGrade::kVignetteOn] ? "On" : "Off";
    for (int c = 1; c < 4; ++c)
        values[kLookVignette + c] = Common::String::format("%d%%", grade.value[HdColorGrade::kVignetteOn + c]);
    if (st.waterPage) for (int row = 0; row < rows; ++row) {
        const int control = hdLookControl(row), value = st.settings.get(editingRoom, control);
        values[row] = control == HdSceneLook::kWaterLightDirection
            ? Common::String::format("%+d deg", value) : Common::String::format("%d%%", value);
    }
    if (st.shadowPage) for (int row = 0; row < rows; ++row) {
        const int control = hdLookControl(row), value = st.settings.get(editingRoom, control);
        values[row] = control <= HdSceneLook::kShadowY ? Common::String::format("%+d px", value)
            : control < HdSceneLook::kShadowRed ? Common::String::format("%d%%", value)
            : Common::String::format("%d", value);
    }
    if (st.filmPage) for (int row = 0; row < rows; ++row)
        values[row] = row == HdFilm::kEnabled ? Common::String(HdFilm::get(row) ? "On" : "Off")
            : Common::String::format("%d%%", HdFilm::get(row));
    static const char *const depthNames[] = {"Depth of field", "Blur radius", "Edge softness", "Blur strength", "Scene depth"};
    Common::String lines[kLookRows + kLookExtraLines];
    bool accent[kLookRows + kLookExtraLines] = {};
    int count = 0;
    const char *title = st.filmPage ? "FILM LOOK" : st.waterPage ? "WATER SHADER" : st.shadowPage ? "CHARACTER SHADOWS" : "SCENE LOOK";
    lines[count++] = editingRoom ? Common::String::format("%s   Room %d (* override)", title, room)
        : Common::String::format("%s   Global defaults", title);
    for (int row = 0; row < rows; ++row) {
        if (row == 0) lines[count++] = st.filmPage ? "Film texture   Tab: Shadows"
            : st.shadowPage ? (HdWater::room(room) ? "Shadows   Tab: Water" : "Shadows   Tab: Scene Look")
            : st.waterPage ? "Water shader   Tab: Scene Look" : "Color correction   Tab: Film";
        if (!st.waterPage && !st.filmPage && !st.shadowPage && row == kLookFocus) lines[count++] = "Scene depth";
        if (!st.waterPage && !st.filmPage && !st.shadowPage && row == kLookVignette) lines[count++] = "Vignette";
        const char *name = st.filmPage ? HdFilm::range(row).name : (st.waterPage || st.shadowPage) ? HdSceneLook::range(hdLookControl(row)).name : row < kLookFocus ? HdColorGrade::range(row).name
            : row < kLookVignette ? depthNames[row - kLookFocus]
            : HdColorGrade::range(HdColorGrade::kVignetteOn + row - kLookVignette).name;
        if (editingRoom && st.settings.rooms[editingRoom].has(hdLookControl(row))) values[row] += " *";
        accent[count] = row == st.row;
        lines[count++] = Common::String::format("%s%s\t%s", row == st.row ? "> " : "   ", name, values[row].c_str());
    }
    if (st.shadowPage) {
        lines[count++] = "X: right +   Y: down +";
        lines[count++] = "Ovalness: 5 flat / 100 round";
    }
    lines[count++] = "Click - / +   Arrows adjust   Shift x5";
    lines[count++] = st.filmPage ? "Backspace default   R reset film"
        : st.shadowPage ? (editingRoom ? "Backspace / R: inherit shadows" : "Backspace default   R reset shadows")
        : editingRoom ? (st.waterPage ? "Backspace inherit   R inherit water" : "Backspace inherit   R inherit all") : "Backspace restore default";
    lines[count++] = st.filmPage ? "Global: all rooms, UI and movies" : "G or click title: Global / Room";
    lines[count++] = (st.filmPage ? HdFilm::state().bypass : st.waterPage ? st.waterBypass : st.shadowPage ? st.shadowBypass : st.bypass) ? "B compare (bypassed)   U / Esc close" : "B compare   U / Esc close";
    if (!st.filmPage && !st.error.empty())
        lines[count++] = st.error;
    else if (st.savedAt && _system->getMillis() - st.savedAt < 2500)
        lines[count++] = editingRoom ? "Room settings saved" : "Global defaults saved";
    else if (!st.filmPage && !editingRoom && HdSceneLook::Settings::roomValid(room) && st.settings.rooms[room].mask)
        lines[count++] = "This room also has overrides";
    const int scale = MAX(1, (int)_hdScale);
    const Common::Point position = hdLookPosition();
    const int left = position.x, top = position.y;
    drawHDOverlayText(_hdComposite, _hdFontManager, _charset, scale, left, top, kLookWidth,
        lines, count, accent, 45, kLookLineHeight, 140);
    const int oldSize = _hdFontManager->getSizePercent();
    _hdFontManager->setSizePercent(45);
    for (int row = 0; row < rows; ++row) {
        const int y = top + 4 + hdLookLine(row) * kLookLineHeight;
        for (int button = 0; button < 2; ++button) {
            const int x = left + 244 + button * 26;
            _hdComposite.fillRect(Common::Rect(x * scale, y * scale, (x + 22) * scale, (y + 14) * scale),
                _hdComposite.format.RGBToColor(row == st.row ? 95 : 50, 55, 35));
            _hdFontManager->drawChar(3, button ? '+' : '-', _hdComposite,
                (x + 7) * scale, y * scale, 255, 220, 160);
        }
    }
    _hdFontManager->setSizePercent(oldSize);
}
