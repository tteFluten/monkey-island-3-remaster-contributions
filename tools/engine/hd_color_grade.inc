// Included in gfx.cpp after hd_depth_of_field.inc. Per-room color grades and
// the playtest Look panel (focus + color). Grades are authoring data kept in
// the tracked file named by hd_color_grades_path; nothing else is modified.
namespace {
struct HdColorGradeState {
    bool loaded = false;
    Common::String path, error;
    HdColorGrade::Grade grades[256];
    bool present[256] = {};
    // Curves for the grade currently applied.
    int lutRoom = -1;
    HdColorGrade::Grade lutGrade;
    HdColorGrade::Lut lut;
    // Look panel: open state, selected row, before/after comparison.
    bool panel = false, bypass = false, mouseDown = false;
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
const int kLookWidth = 300, kLookTop = 8, kLookLineHeight = 16;
int hdLookLine(int row) { return row + 2 + (row >= kLookFocus ? 1 : 0) + (row >= kLookVignette ? 1 : 0); }

void hdLoadColorGrades(HdColorGradeState &st) {
    st.loaded = true;
    st.path = ConfMan.hasKey("hd_color_grades_path") ? ConfMan.get("hd_color_grades_path") : "";
    if (st.path.empty()) return;
    FILE *file = fopen(st.path.c_str(), "rb");
    if (!file) return;
    Common::String text;
    char buffer[4096];
    size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), file)) > 0) text += Common::String(buffer, count);
    fclose(file);
    Common::JSONValue *root = Common::JSON::parse(text.c_str());
    if (root && root->isObject() && root->hasChild("rooms") && root->child("rooms")->isObject()) {
        const Common::JSONObject &rooms = root->child("rooms")->asObject();
        for (Common::JSONObject::const_iterator it = rooms.begin(); it != rooms.end(); ++it) {
            const int room = atoi(it->_key.c_str());
            if (room < 1 || room > 255 || !it->_value->isObject()) continue;
            HdColorGrade::Grade grade;
            for (int c = 0; c < HdColorGrade::kControls; ++c) {
                const char *key = HdColorGrade::range(c).key;
                if (it->_value->hasChild(key) && it->_value->child(key)->isIntegerNumber())
                    grade.value[c] = HdColorGrade::clampControl(c, (int)it->_value->child(key)->asIntegerNumber());
            }
            st.grades[room] = grade;
            st.present[room] = !HdColorGrade::identity(grade);
        }
    } else {
        st.error = "Could not read color grades";
    }
    delete root;
}

// Rooms in numeric order, neutral rooms omitted, written atomically.
bool hdSaveColorGrades(HdColorGradeState &st) {
    if (st.path.empty()) { st.error = "No hd_color_grades_path configured"; return false; }
    const Common::String temporary = st.path + ".tmp";
    FILE *file = fopen(temporary.c_str(), "wb");
    if (!file) { st.error = "Could not write " + st.path; return false; }
    fprintf(file, "{\n  \"schemaVersion\": 1,\n  \"rooms\": {");
    bool first = true;
    for (int room = 1; room < 256; ++room) {
        if (!st.present[room]) continue;
        fprintf(file, "%s\n    \"%d\": {", first ? "" : ",", room);
        for (int c = 0; c < HdColorGrade::kControls; ++c)
            fprintf(file, "%s\"%s\": %d", c ? ", " : "", HdColorGrade::range(c).key, st.grades[room].value[c]);
        fprintf(file, "}");
        first = false;
    }
    fprintf(file, first ? "}\n}\n" : "\n  }\n}\n");
    const bool written = fclose(file) == 0 && rename(temporary.c_str(), st.path.c_str()) == 0;
    st.error = written ? "" : "Could not write " + st.path;
    st.savedAt = g_system->getMillis();
    return written;
}
}

// Grade the composed scene: runs after costumes and native overlays, before
// HD dialogue text, verbs, inventory and the cursor, which keep their colors.
void ScummEngine::renderHDColorGrade() {
    HdColorGradeState &st = hdColorGradeState();
    if (_game.id != GID_CMI) return;
    if (!st.loaded) hdLoadColorGrades(st);
    const int room = _currentRoom;
    const HdColorGrade::Grade grade = room >= 1 && room <= 255 && !st.bypass
        ? st.grades[room] : HdColorGrade::Grade();
    // The decorative widescreen extension receives the same scene treatment.
    for (int c = 0; c < HdColorGrade::kControls; ++c)
        ConfMan.setInt(Common::String("hd_wide_look_") + HdColorGrade::range(c).key,
            grade.value[c], Common::ConfigManager::kTransientDomain);
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
            (room == 9 && ConfMan.hasKey("hd_wide_background_active") && ConfMan.getBool("hd_wide_background_active")));
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
        _currentRoom == 87 || _currentRoom == 92 || hdInventoryOpen()) {
        st.panel = false;
        return false;
    }
    if (!st.loaded) hdLoadColorGrades(st);
    const bool key = event.type == Common::EVENT_KEYDOWN;
    if (key && (event.kbd.flags & (Common::KBD_CTRL | Common::KBD_ALT | Common::KBD_META))) return false;
    if (key && (event.kbd.keycode == Common::KEYCODE_u || event.kbd.keycode == Common::KEYCODE_BACKQUOTE)) {
        st.panel = !st.panel;
        _fullRedraw = true;
        return true;
    }
    if (!st.panel) return false;
    const int steps = key && (event.kbd.flags & Common::KBD_SHIFT) ? 5 : 1;
    int delta = 0;
    bool reset = false;
    _fullRedraw = true;
    if (event.type == Common::EVENT_LBUTTONDOWN) {
        st.mouseDown = true; _leftBtnPressed = 0;
        const int scale = MAX(1, (int)_hdScale);
        const int left = MAX(8, (int)_hdComposite.w / scale - kLookWidth - 8);
        const int x = event.mouse.x / scale - left, y = event.mouse.y / scale - kLookTop;
        if (x < 0 || x >= kLookWidth || y < 0 || y >= (kLookRows + 8) * kLookLineHeight) {
            st.panel = false; return true;
        }
        int row = -1;
        for (int r = 0; r < kLookRows; ++r)
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
    case Common::KEYCODE_UP: st.row = (st.row + kLookRows - 1) % kLookRows; return true;
    case Common::KEYCODE_DOWN: st.row = (st.row + 1) % kLookRows; return true;
    case Common::KEYCODE_LEFT: delta = -steps; break;
    case Common::KEYCODE_RIGHT: delta = steps; break;
    case Common::KEYCODE_BACKSPACE: case Common::KEYCODE_DELETE: reset = true; break;
    case Common::KEYCODE_b: st.bypass = !st.bypass; return true;
    case Common::KEYCODE_ESCAPE: st.panel = false; return true;
    case Common::KEYCODE_o: case Common::KEYCODE_F5: case Common::KEYCODE_i:
        st.panel = false; return false;
    default: return true;
    }
    if (st.row < kLookFocus || st.row >= kLookVignette) {
        const int room = _currentRoom;
        if (room < 1 || room > 255) return true;
        const int control = st.row < kLookFocus ? st.row : HdColorGrade::kVignetteOn + st.row - kLookVignette;
        HdColorGrade::Grade &grade = st.grades[room];
        if (reset) grade.value[control] = HdColorGrade::range(control).neutral;
        else grade = HdColorGrade::adjust(grade, control, delta);
        st.present[room] = !HdColorGrade::identity(grade);
        hdSaveColorGrades(st);
        return true;
    }
    HdDepthOfFieldState &dof = hdDepthOfFieldState();
    int level = hdDepthOfFieldLevel();
    HdDepthOfField::Tuning tuning = hdDepthOfFieldTuning();
    const HdDepthOfField::Tuning neutral;
    if (st.row == kLookFocus) {
        level = reset ? 0 : HdDepthOfField::clampInt(level + (delta > 0 ? 1 : -1), 0, 2);
        if (level) dof.lastLevel = level;
    } else {
        // Adjusting a focus setting turns focus on, like the hotkeys.
        if (!level) level = dof.lastLevel;
        const int blur = st.row == kLookBlur ? delta : 0, edge = st.row == kLookEdge ? delta : 0;
        const int intensity = st.row == kLookIntensity ? delta : 0, depth = st.row == kLookDepth ? delta : 0;
        if (!reset) tuning = HdDepthOfField::step(level, tuning, blur, edge, intensity, depth);
        else if (st.row == kLookBlur) tuning.blurTenths = neutral.blurTenths;
        else if (st.row == kLookEdge) tuning.edge = neutral.edge;
        else if (st.row == kLookIntensity) tuning.intensity = neutral.intensity;
        else tuning.depth = neutral.depth;
    }
    hdStoreDepthOfField(level, tuning);
    return true;
}

void ScummEngine::drawHDLookPanel() {
    HdColorGradeState &st = hdColorGradeState();
    if (_currentRoom == 92 || _currentRoom == 87 || isSmushActive() || hdInventoryOpen()) st.panel = false;
    if (!st.panel || _game.id != GID_CMI || !_hdFontManager || !_hdFontManager->hasFont(3) || !_hdComposite.getPixels())
        return;
    const int room = _currentRoom;
    const HdColorGrade::Grade grade = room >= 1 && room <= 255 ? st.grades[room] : HdColorGrade::Grade();
    const int level = hdDepthOfFieldLevel();
    const HdDepthOfField::Tuning tuning = hdDepthOfFieldTuning();
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
    static const char *const depthNames[] = {"Depth of field", "Blur radius", "Edge softness", "Blur strength", "Scene depth"};
    Common::String lines[kLookRows + 8];
    bool accent[kLookRows + 8] = {};
    int count = 0;
    lines[count++] = Common::String::format("SCENE LOOK   room %d%s", room, st.bypass ? "   (bypassed)" : "");
    for (int row = 0; row < kLookRows; ++row) {
        if (row == 0) lines[count++] = "Color correction";
        if (row == kLookFocus) lines[count++] = "Scene depth";
        if (row == kLookVignette) lines[count++] = "Vignette";
        const char *name = row < kLookFocus ? HdColorGrade::range(row).name
            : row < kLookVignette ? depthNames[row - kLookFocus]
            : HdColorGrade::range(HdColorGrade::kVignetteOn + row - kLookVignette).name;
        accent[count] = row == st.row;
        lines[count++] = Common::String::format("%s%s\t%s", row == st.row ? "> " : "   ", name, values[row].c_str());
    }
    lines[count++] = "Click - / +   or Up Down / Left Right";
    lines[count++] = "Shift x5   Backspace reset   U / Esc close";
    lines[count++] = "B compare color and vignette";
    if (!st.error.empty())
        lines[count++] = st.error;
    else if (st.savedAt && _system->getMillis() - st.savedAt < 2500)
        lines[count++] = "Saved for this scene";
    const int scale = MAX(1, (int)_hdScale);
    const int left = MAX(8, (int)_hdComposite.w / scale - kLookWidth - 8);
    drawHDOverlayText(_hdComposite, _hdFontManager, _charset, scale, left, kLookTop, kLookWidth,
        lines, count, accent, 45, kLookLineHeight, 140);
    const int oldSize = _hdFontManager->getSizePercent();
    _hdFontManager->setSizePercent(45);
    for (int row = 0; row < kLookRows; ++row) {
        const int y = kLookTop + 4 + hdLookLine(row) * kLookLineHeight;
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
