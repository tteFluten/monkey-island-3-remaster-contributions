// Language packs (hd_language.h), text. The game's string table is rebuilt for
// the chosen language: the pack's LANGUAGE.TAB (or the game's own), then the
// pack's overrides.tab. Scripts carry "/TAG/English text" and translateText()
// looks the tag up at print time, so the next line printed uses the new table.

Common::String ScummEngine::hdLanguageDir(int language) const {
    if (language == HdLanguage::kEnglish || !ConfMan.hasKey("hd_language_dir")) return Common::String();
    return ConfMan.get("hd_language_dir") + "/" + HdLanguage::kCodes[language];
}

static Common::SeekableReadStream *hdLanguageFile(const Common::String &dir, const char *name) {
    if (dir.empty()) return nullptr;
    Common::FSNode node(Common::Path(dir + "/" + name, '/'));
    return node.exists() ? node.createReadStream() : nullptr;
}

// Any text or voice for the language is enough to offer it in the book.
bool ScummEngine::hdLanguageAvailable(int language) const {
    if (language == HdLanguage::kEnglish) return true;
    const Common::String dir = hdLanguageDir(language);
    if (dir.empty()) return false;
    static const char *const files[] = {"LANGUAGE.TAB", "overrides.tab", "VOXDISK1.BUN", "VOXDISK2.BUN", "voices"};
    for (const char *name : files)
        if (Common::FSNode(Common::Path(dir + "/" + name, '/')).exists()) return true;
    return false;
}

// Adds every "TAG text" line of a string table; later tables win.
static void hdReadStringTable(Common::SeekableReadStream *file, bool utf8,
                              Common::HashMap<Common::String, Common::String> &table, Common::StringArray &order) {
    if (!file) return;
    while (!file->eos() && !file->err()) {
        Common::String line = file->readLine();
        if (utf8 && line.size() >= 3 && (byte)line[0] == 0xEF && (byte)line[1] == 0xBB && (byte)line[2] == 0xBF)
            line.erase(0, 3);
        char tag[13];
        int start;
        if (!HdLanguage::parseLine(line.c_str(), line.size(), tag, start)) continue;
        Common::String text(line.c_str() + start);
        if (utf8) text = Common::U32String(text, Common::kUtf8).encode(Common::kWindows1252);
        if (!table.contains(tag)) order.push_back(tag);
        table[tag] = text;
    }
    delete file;
}

bool ScummEngine_v7::hdLoadStringTable(int language) {
    if (_game.id != GID_CMI) return false;
    const Common::String dir = hdLanguageDir(language);
    Common::HashMap<Common::String, Common::String> table;
    Common::StringArray order;
    Common::SeekableReadStream *base = hdLanguageFile(dir, "LANGUAGE.TAB");
    if (!base) {
        ScummFile *game = new ScummFile(this);
        openFile(*game, "language.tab");
        if (game->isOpen()) base = game; else delete game;
    }
    hdReadStringTable(base, false, table, order);
    hdReadStringTable(hdLanguageFile(dir, "overrides.tab"), true, table, order);
    if (table.empty()) return false;

    uint size = 0;
    for (uint i = 0; i < order.size(); ++i) size += table[order[i]].size() + 1;
    char *buffer = (char *)calloc(1, size + 1);
    LangIndexNode *index = (LangIndexNode *)calloc(order.size(), sizeof(LangIndexNode));
    if (!buffer || !index) { free(buffer); free(index); return false; }
    uint offset = 0;
    for (uint i = 0; i < order.size(); ++i) {
        const Common::String &text = table[order[i]];
        Common::strlcpy(index[i].tag, order[i].c_str(), sizeof(index[i].tag));
        index[i].offset = offset;
        memcpy(buffer + offset, text.c_str(), text.size() + 1);
        HdLanguage::unescape(buffer + offset);
        offset += text.size() + 1;
    }
    qsort(index, order.size(), sizeof(LangIndexNode), indexCompare);
    free(_languageBuffer);
    free(_languageIndex);
    _languageBuffer = buffer;
    _languageIndex = index;
    _languageIndexSize = order.size();
    _existLanguageFile = true;
    return true;
}

// Voices: pack bundles are reached as "<code>/voxdiskN.bun" (see
// hd_voice_select.inc); a per-line recording is voices/<TAG>.wav.
Common::String ScummEngine::hdVoiceBundles() const {
    return _hdVoiceBundles;
}

Common::SeekableReadStream *ScummEngine::hdVoiceLine(const char *soundName) const {
    const Common::String dir = hdLanguageDir(_hdLanguage);
    if (dir.empty()) return nullptr;
    Common::String tag(soundName);
    const char *dot = strchr(soundName, '.');
    if (dot) tag = Common::String(soundName, dot);
    Common::SeekableReadStream *line = hdLanguageFile(dir, ("voices/" + tag + ".wav").c_str());
    if (!line) {
        tag.toLowercase();
        line = hdLanguageFile(dir, ("voices/" + tag + ".wav").c_str());
    }
    return line;
}

// Switches text and voices at once. The line being spoken finishes as it
// started; the next line printed or spoken uses the new language.
void ScummEngine_v7::hdSetLanguage(int language) {
    if (_game.id != GID_CMI || language < 0 || language >= HdLanguage::kCount || !hdLanguageAvailable(language)) return;
    if (!hdLoadStringTable(language)) return;
    _hdLanguage = language;
    const Common::String dir = hdLanguageDir(language);
    _hdVoiceBundles.clear();
    if (!dir.empty() && (Common::FSNode(Common::Path(dir + "/VOXDISK1.BUN", '/')).exists() ||
                         Common::FSNode(Common::Path(dir + "/VOXDISK2.BUN", '/')).exists()))
        _hdVoiceBundles = Common::String(HdLanguage::kCodes[language]) + "/";
    ConfMan.set("hd_language", HdLanguage::kCodes[language]);
    ConfMan.flushToDisk();
    _hdLanguageOffered = -1;
    redrawVerbs();
    _fullRedraw = true;
    warning("HD language: %s (voice bundles: %s)", HdLanguage::kCodes[language], _hdVoiceBundles.empty() ? "English" : _hdVoiceBundles.c_str());
}

// At start-up, after the game's own string table: language packs become
// reachable as "<code>/..." and the saved choice is restored.
void ScummEngine::hdApplySavedLanguage() {
    if (_game.id != GID_CMI || !ConfMan.hasKey("hd_language_dir")) return;
    const Common::FSNode packs(Common::Path(ConfMan.get("hd_language_dir"), '/'));
    if (packs.isDirectory() && !SearchMan.hasArchive("hd-languages"))
        SearchMan.addDirectory("hd-languages", packs, 0, 2);
    const int language = HdLanguage::fromCode(ConfMan.get("hd_language").c_str());
    if (language != HdLanguage::kEnglish) {
        if (hdLanguageAvailable(language)) hdSetLanguage(language);
        else warning("HD language: %s pack not found; using English", HdLanguage::kCodes[language]);
    }
}
