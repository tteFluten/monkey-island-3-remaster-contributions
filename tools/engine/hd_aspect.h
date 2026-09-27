// Shared presentation geometry. Room resources and script coordinates never change.
#ifndef HD_ASPECT_H
#define HD_ASPECT_H
namespace HdAspect {
inline int preference(int value) { return value == 169 ? 169 : 43; }
inline int viewport(int aspect, int width, int height) {
    return aspect == 169 && width >= 864 && height == 480 ? 864 : 640;
}
// Script-authored inspection captions use the original screen center (320).
// Only screen-anchored text calls this; actor/world positions are already mapped.
inline int centeredTextX(int x, bool centered, int viewportWidth) {
    return centered && x == 320 && viewportWidth > 640 ? viewportWidth / 2 : x;
}
struct Rect { int x, y, w, h; };
inline Rect frame(int width, int height, int aspect, bool cover = false) {
    const int numerator = aspect == 169 ? 16 : 4;
    const int denominator = aspect == 169 ? 9 : 3;
    int w = width, h = width * denominator / numerator;
    if ((!cover && h > height) || (cover && h < height)) { h = height; w = (height * numerator + (cover ? denominator - 1 : 0)) / denominator; }
    return {(width - w) / 2, (height - h) / 2, w, h};
}
inline Rect game(int width, int height, int aspect, int viewportWidth, bool cover = false, bool movie = false) {
    // Keep the selected movie frame intact, with cinematic bars on displays
    // of a different shape. Source cropping preserves the picture's proportions.
    if (movie) return frame(width, height, aspect);
    const Rect outer = frame(width, height, aspect, cover);
    const int w = outer.h * viewportWidth / 480;
    return {outer.x + (outer.w - w) / 2, outer.y, w, outer.h};
}
// Visible native coordinates after the same uniform crop used for drawing
// and pointer mapping. Round inward so overlay controls stay fully on-screen.
inline Rect visibleGame(int width, int height, int aspect, int viewportWidth, bool cover = false) {
    if (width <= 0 || height <= 0) return {0, 0, viewportWidth, 480};
    const Rect drawn = game(width, height, aspect, viewportWidth, cover);
    if (drawn.w <= 0 || drawn.h <= 0) return {0, 0, viewportWidth, 480};
    const int left = drawn.x < 0 ? (-drawn.x * viewportWidth + drawn.w - 1) / drawn.w : 0;
    const int top = drawn.y < 0 ? (-drawn.y * 480 + drawn.h - 1) / drawn.h : 0;
    const int right = drawn.x + drawn.w > width ? (width - drawn.x) * viewportWidth / drawn.w : viewportWidth;
    const int bottom = drawn.y + drawn.h > height ? (height - drawn.y) * 480 / drawn.h : 480;
    return {left, top, right - left, bottom - top};
}
inline int camera(int x, int roomWidth, int viewportWidth, int scriptMin, int scriptMax) {
    const int low = viewportWidth / 2, high = roomWidth - low;
    // A script may lock the camera outside the wider viewport's safe range.
    // Move that lock to the nearest valid center rather than reading past art.
    int a = scriptMin < low ? low : (scriptMin > high ? high : scriptMin);
    int b = scriptMax < low ? low : (scriptMax > high ? high : scriptMax);
    if (a > b) { int swap = a; a = b; b = swap; }
    return x < a ? a : (x > b ? b : x);
}
struct Buttons {
    unsigned pressed = 0;
    int x = 0, y = 0;
    bool accept(bool inside, unsigned down, unsigned up, int &mouseX, int &mouseY) {
        if (up && !(pressed & up)) inside = false;
        if (!inside && up && (pressed & up)) {
            mouseX = x; mouseY = y; inside = true;
        }
        if (inside) { x = mouseX; y = mouseY; pressed |= down; }
        pressed &= ~up;
        return inside;
    }
};
}
#endif
