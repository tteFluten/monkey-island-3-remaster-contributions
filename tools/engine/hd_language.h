#ifndef SCUMM_HD_LANGUAGE_H
#define SCUMM_HD_LANGUAGE_H
// Language packs. English is the game's own data. Another language lives in
// <hd_language_dir>/<code>/ and may provide, each optional:
//   LANGUAGE.TAB       the game's string table for that language ("TAG<tab>text"
//                      lines, Windows-1252), e.g. from an official edition;
//   overrides.tab      the same line format in UTF-8, applied on top (per line);
//   VOXDISK1.BUN, VOXDISK2.BUN   voice bundles for that language;
//   voices/<TAG>.wav   one voice line (overrides the bundles).
// Lines a pack does not provide fall back to English. The remaster's own book
// strings are translated here.
// (No stdio: ScummVM engines may not use snprintf.)

namespace HdLanguage {

enum Code { kEnglish = 0, kSpanish = 1, kCount = 2 };
static const char *const kCodes[kCount] = {"en", "es"};

inline int fromCode(const char *code) {
    for (int i = 0; i < kCount; ++i) {
        const char *a = code, *b = kCodes[i];
        while (*a && *a == *b) { ++a; ++b; }
        if (!*a && !*b) return i;
    }
    return kEnglish;
}

// One string-table line: tag (up to 8 characters, upper-cased, as the engine
// reads LANGUAGE.TAB) and the text after one separating space or tab.
inline bool parseLine(const char *line, int length, char *tag, int &textStart) {
    int i = 0;
    while (i < length && i < 8 && line[i] != ' ' && line[i] != '\t') {
        const char c = line[i];
        tag[i] = (c >= 'a' && c <= 'z') ? (char)(c - 'a' + 'A') : c;
        ++i;
    }
    tag[i] = 0;
    if (!i || i >= length || (line[i] != ' ' && line[i] != '\t')) return false;
    textStart = i + 1;
    return true;
}

// "\n" written as two characters becomes a newline, as in the engine's loader.
inline void unescape(char *text) {
    char *dst = text;
    for (const char *src = text; *src;) {
        if (src[0] == '\\' && src[1] == 'n') { *dst++ = '\n'; src += 2; }
        else *dst++ = *src++;
    }
    *dst = 0;
}

// Remaster strings, Windows-1252 like the game's fonts.
enum Text { kTextSize, kEnglishName, kSpanishName, kTextCount };
static const char *const kTexts[kCount][kTextCount] = {
    {"Text Size", "English", "Espa\xF1ol"},
    {"Tama\xF1o del texto", "English", "Espa\xF1ol"},
};
inline const char *text(int language, Text id) {
    return kTexts[language >= 0 && language < kCount ? language : kEnglish][id];
}

// "Autosave (12 min ago)" / "Autoguardado (hace 12 min)"; just the name when
// the clock went backwards.
inline void autosaveLabel(int language, long age, char *out, int size) {
    const bool es = language == kSpanish;
    const char *name = es ? "Autoguardado" : "Autosave", *before = "", *after = "", *fixed = "";
    long count = -1;
    if (age < 0) {}
    else if (age < 1) fixed = es ? " (ahora mismo)" : " (just now)";
    else if (age < 60) { count = age; before = es ? " (hace " : " ("; after = es ? " min)" : " min ago)"; }
    else if (age < 120) fixed = es ? " (hace 1 hora)" : " (1 hour ago)";
    else if (age < 1440) { count = age / 60; before = es ? " (hace " : " ("; after = es ? " horas)" : " hours ago)"; }
    else if (age < 2880) fixed = es ? " (ayer)" : " (yesterday)";
    else { count = age / 1440; before = es ? " (hace " : " ("; after = es ? " d\xED" "as)" : " days ago)"; }
    int n = 0;
    auto put = [&](const char *s) { while (*s && n < size - 1) out[n++] = *s++; };
    put(name);
    if (count >= 0) {
        char digits[24];
        int d = 0;
        do { digits[d++] = (char)('0' + count % 10); count /= 10; } while (count && d < 23);
        put(before);
        while (d && n < size - 1) out[n++] = digits[--d];
        put(after);
    }
    put(fixed);
    if (size > 0) out[n] = 0;
}

} // namespace HdLanguage

#endif
