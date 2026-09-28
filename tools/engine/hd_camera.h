#ifndef SCUMM_HD_CAMERA_H
#define SCUMM_HD_CAMERA_H
#include <cmath>

// Drawing state only. Never serialize or feed these positions into the walker.
namespace HdCamera {
inline double clamp(double x, double low, double high) {
    return x < low ? low : x > high ? high : x;
}
inline int anchor(double x) { return (int)std::floor(x + 0.5); }
// The 864-wide GPU canvas crops 5 1/3 native pixels from each side in
// 16:9. Use that existing gutter to keep the native strip anchor stable for
// several presentations; the shader still moves at full fractional precision.
inline int rasterAnchor(double x, bool wideGpu) {
    return wideGpu ? anchor(x / 8.0) * 8 : anchor(x);
}
struct Axis {
    double position = 0, velocity = 0, target = 0;
    void reset(double value) { position = target = value; velocity = 0; }
    bool moving() const { return std::fabs(position - target) > 0.001 || std::fabs(velocity) > 0.01; }
    void step(double destination, double seconds, double low, double high) {
        target = clamp(destination, low, high);
        position = clamp(position, low, high);
        // Exact critically damped solution for this frame's target. The 0.20s
        // smoothing time sets omega=2/time; it is not a per-frame lerp factor.
        const double omega = 10.0;
        const double error = position - target;
        const double impulse = velocity + omega * error;
        const double decay = std::exp(-omega * seconds);
        const double next = target + (error + impulse * seconds) * decay;
        velocity = (velocity - omega * impulse * seconds) * decay;
        // Do not cross the target, or accumulate velocity against a room edge.
        if ((error > 0 && next < target) || (error < 0 && next > target) ||
            next < low || next > high) {
            position = clamp(next, low, high);
            if (next >= low && next <= high) position = target;
            velocity = 0;
        } else position = next;
        if (!moving()) reset(target);
    }
};
struct Follow {
    Axis x, y;
    double verticalOffset = 0, last = 0;
    int actor = 0;
    void reset(double cx, double cy, double actorY, int followed, double now) {
        x.reset(cx); y.reset(cy); verticalOffset = cy - actorY;
        actor = followed; last = now;
    }
    void step(double ax, double ay, double now, double minX, double maxX, double minY, double maxY) {
        double dt = (now - last) / 1000.0;
        last = now;
        // Lifecycle resets handle discontinuities. A missed display deadline
        // must not produce a large catch-up sweep or integrate negative time.
        dt = clamp(dt, 0, 0.05);
        x.step(ax, dt, minX, maxX);
        y.step(ay + verticalOffset, dt, minY, maxY);
    }
    bool moving() const { return actor && (x.moving() || y.moving()); }
};

// Button events can wait through several presentations before a native tick.
// Retain the view and pointer that were actually visible when the click arrived.
struct Click {
    bool pending = false;
    int room = -1, x = 0, y = 0;
    double left = 0, top = 0;
    void record(int currentRoom, int mouseX, int mouseY, double cameraLeft, double cameraTop) {
        pending = true; room = currentRoom; x = mouseX; y = mouseY;
        left = cameraLeft; top = cameraTop;
    }
    bool consume(int currentRoom, bool clicked) {
        const bool accepted = pending && clicked && room == currentRoom;
        pending = false;
        return accepted;
    }
};

// CPU fallback for the same fractional viewport used by the GPU. Clamp the
// sample footprint to edge texels: a virtual replicated gutter prevents dark
// seams without allocating/copying a padded full-resolution surface each draw.
inline unsigned mix(unsigned a, unsigned b, unsigned weight) {
    unsigned result = 0;
    for (int c = 0; c < 32; c += 8)
        result |= (((((a >> c) & 255) * (256 - weight) + ((b >> c) & 255) * weight + 128) >> 8) << c);
    return result;
}
inline void translate(const unsigned *src, int sourcePitch, unsigned *dst, int destPitch,
                      int width, int height, double dx, double dy) {
    const int ix = (int)std::floor(dx), iy = (int)std::floor(dy);
    const unsigned fx = (unsigned)((dx - ix) * 256 + 0.5), fy = (unsigned)((dy - iy) * 256 + 0.5);
    for (int y = 0; y < height; ++y) {
        const unsigned *a = src + (int)clamp(y + iy, 0, height - 1) * sourcePitch;
        const unsigned *b = src + (int)clamp(y + iy + 1, 0, height - 1) * sourcePitch;
        for (int x = 0; x < width; ++x) {
            const int l = (int)clamp(x + ix, 0, width - 1), r = (int)clamp(x + ix + 1, 0, width - 1);
            dst[y * destPitch + x] = mix(mix(a[l], a[r], fx), mix(b[l], b[r], fx), fy);
        }
    }
}
}
#endif
