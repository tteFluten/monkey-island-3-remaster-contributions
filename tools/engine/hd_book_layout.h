#ifndef SCUMM_HD_BOOK_LAYOUT_H
#define SCUMM_HD_BOOK_LAYOUT_H
// Options spread of the COMI book (room 92), in original 640x480 coordinates.
// The book scripts still place and hit-test every control at its original
// position; items are drawn translated, and the pointer is translated back
// before the scripts read it. Left page: sound, text, toggles. Right page: the
// table of contents, centred on the 16:9 page.

namespace HdBookLayout {

struct Box {
    int left, top, right, bottom; // right/bottom exclusive
    bool contains(int x, int y) const { return x >= left && x < right && y >= top && y < bottom; }
};

struct Move {
    Box source;
    int dx, dy;
    Box target() const { return {source.left + dx, source.top + dy, source.right + dx, source.bottom + dy}; }
};

// Each source box holds one control: its label, widget and script hotspot.
static const Move kMoves[] = {
    {{40, 76, 300, 132}, 0, -13},    // Effects Volume
    {{40, 132, 300, 188}, 0, -13},   // Voice Volume
    {{40, 188, 300, 244}, 0, -13},   // Music Volume
    {{40, 294, 300, 348}, 0, -55},   // Text Speed
    {{40, 244, 150, 270}, 0, 112},   // [x] Voice ...
    {{40, 270, 150, 294}, 112, 88},  // ... beside [x] Text
    {{40, 348, 300, 374}, 0, 36},    // [x] Show object line
    {{360, 90, 600, 150}, 24, 24},   // TABLE of CONTENTS
    {{360, 150, 600, 192}, 24, 32},  // Save Game
    {{360, 192, 600, 232}, 24, 40},  // Load Game
    {{360, 232, 600, 272}, 24, 48},  // Return to Game
    {{360, 272, 600, 312}, 24, 56},  // Quit
};
static const int kMoveCount = sizeof(kMoves) / sizeof(kMoves[0]);
static const int kSaveEntry = 8, kLoadEntry = 9; // kMoves indices

// "Enable 3D acceleration": always disabled in the original; not shown.
static const Box kHidden = {40, 374, 300, 400};

// Text Size slider, drawn with the book's own slider bar, knob and label font
// between Text Speed and the toggles.
static const int kSizeLabelY = 296, kSizeBarY = 329, kSizeKnobY = 321;
static const int kSliderLeft = 48, kSliderWidth = 200, kKnobWidth = 16;
static const Box kSizeHit = {40, 316, 256, 350};
static const int kSizeMin = 25, kSizeMax = 100, kSizeStep = 5;

// Language row under the table of contents: a book checkbox and label per
// language, like the Voice and Text toggles.
static const int kLanguageY = 380, kLanguageCount = 2;
static const int kLanguageX[kLanguageCount] = {404, 508};
static const int kLanguageLabelDx = 35, kLanguageLabelDy = 2, kLanguageWidth = 100, kCheckbox = 24;
inline int languageAt(int x, int y) {
    if (y < kLanguageY - 2 || y >= kLanguageY + kCheckbox + 2) return -1;
    for (int i = 0; i < kLanguageCount; ++i)
        if (x >= kLanguageX[i] - 2 && x < kLanguageX[i] + kLanguageWidth) return i;
    return -1;
}

// Where the pointer goes for the scripts outside every control: no hotspot.
static const int kNeutralX = 320, kNeutralY = 476;
static const int kFree = -2;

inline int sourceAt(int x, int y) {
    for (int i = 0; i < kMoveCount; ++i)
        if (kMoves[i].source.contains(x, y)) return i;
    return -1;
}

inline int targetAt(int x, int y) {
    for (int i = 0; i < kMoveCount; ++i)
        if (kMoves[i].target().contains(x, y)) return i;
    return -1;
}

// Script-queued text anchor or object origin. False: do not draw it.
inline bool place(int &x, int &y) {
    if (kHidden.contains(x, y)) return false;
    const int i = sourceAt(x, y);
    if (i >= 0) { x += kMoves[i].dx; y += kMoves[i].dy; }
    return true;
}

// Pointer as the book scripts expect it. A press keeps its control until the
// release, so dragging a slider may leave its row without jumping elsewhere.
inline void toScript(int &x, int &y, int &capture, bool held) {
    if (!held) capture = kFree;
    else if (capture == kFree) capture = targetAt(x, y);
    const int i = held ? capture : targetAt(x, y);
    if (i < 0) { x = kNeutralX; y = kNeutralY; return; }
    x -= kMoves[i].dx; y -= kMoves[i].dy;
}

// Save/Load spread: each column of slots (number, frame, thumbnail, name,
// hotspot) centred on its 16:9 page. Pages differ slightly (the original
// places each page's slots by hand), so whole columns move. The page-turning
// edges, native x < 48 and x >= 592, and the captions keep their places.
static const Move kSlotMoves[] = {
    {{63, 40, 316, 448}, -15, 0},  // slots 1-3 of each page
    {{324, 40, 549, 448}, 43, 0},  // slots 4-6
};

// Slot numbers sit left of their frames; names are centred under them.
inline bool slotNumberAt(int x, int y) {
    return y >= 40 && y < 448 && ((x >= 63 && x < 98) || (x >= 324 && x < 402));
}
static const int kSlotMoveCount = sizeof(kSlotMoves) / sizeof(kSlotMoves[0]);

inline void placeSlot(int &x, int &y) {
    for (int i = 0; i < kSlotMoveCount; ++i)
        if (kSlotMoves[i].source.contains(x, y)) { x += kSlotMoves[i].dx; y += kSlotMoves[i].dy; return; }
}

// Outside the moved columns the pointer is unchanged: page corners and any
// control the layout does not move behave as in the original.
inline void slotToScript(int &x, int &y) {
    for (int i = 0; i < kSlotMoveCount; ++i)
        if (kSlotMoves[i].target().contains(x, y)) { x -= kSlotMoves[i].dx; y -= kSlotMoves[i].dy; return; }
}

inline int sizeKnobX(int percent) {
    if (percent < kSizeMin) percent = kSizeMin;
    if (percent > kSizeMax) percent = kSizeMax;
    return kSliderLeft + (percent - kSizeMin) * (kSliderWidth - kKnobWidth) / (kSizeMax - kSizeMin);
}

// Knob centred under the pointer, snapped to the nearest step.
inline int sizeAt(int x) {
    const int travel = kSliderWidth - kKnobWidth, span = kSizeMax - kSizeMin;
    int offset = x - kKnobWidth / 2 - kSliderLeft;
    if (offset < 0) offset = 0;
    if (offset > travel) offset = travel;
    const int steps = (offset * span + travel * kSizeStep / 2) / (travel * kSizeStep);
    return kSizeMin + steps * kSizeStep;
}

} // namespace HdBookLayout

#endif
