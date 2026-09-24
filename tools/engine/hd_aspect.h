// Shared presentation geometry. Room resources and script coordinates never change.
#ifndef HD_ASPECT_H
#define HD_ASPECT_H
namespace HdAspect {
inline int preference(int value) { return value == 169 ? 169 : 43; }
inline int viewport(int aspect, int width, int height) {
    return aspect == 169 && width >= 864 && height == 480 ? 864 : 640;
}
struct Rect { int x, y, w, h; };
inline Rect frame(int width, int height, int aspect) {
    const int numerator = aspect == 169 ? 16 : 4;
    const int denominator = aspect == 169 ? 9 : 3;
    int w = width, h = width * denominator / numerator;
    if (h > height) { h = height; w = height * numerator / denominator; }
    return {(width - w) / 2, (height - h) / 2, w, h};
}
inline Rect game(int width, int height, int aspect, int viewportWidth) {
    const Rect outer = frame(width, height, aspect);
    const int w = outer.h * viewportWidth / 480;
    return {outer.x + (outer.w - w) / 2, outer.y, w, outer.h};
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
