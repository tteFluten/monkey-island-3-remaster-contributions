#ifndef SCUMM_HD_FRAME_PACER_H
#define SCUMM_HD_FRAME_PACER_H

namespace HdPresentation {
// Millisecond clock with fractional carry: 60 intervals total exactly 1000 ms.
// Presentation never changes SCUMM's script, actor, audio, or movie timers.
// A synchronized backend renders first, then waits for its swap deadline.
// Keep fractional cadence across normal display quantization; a missed frame
// or resumed window starts a fresh interval instead of a catch-up burst.
struct SwapPacer {
    double next = 0;
    static double period() { return 1000.0 / 60.0; }
    unsigned int delay(double now) const {
        const double remaining = next - now - 4.0; // Leave GPU submission and the final edge to vsync.
        return remaining > 0 ? (unsigned int)remaining : 0;
    }
    void presented(double now) {
        next = !next || now > next + period() / 2 ? now + period() : next + period();
    }
    void reset() { next = 0; }
};
struct FramePacer {
    unsigned int next = 0, remainder = 0;
    bool started = false;
    bool due(unsigned int now) const { return !started || (int)(now - next) >= 0; }
    unsigned int delay(unsigned int now) const { return due(now) ? 0 : next - now; }
    void presented(unsigned int now) {
        // Vsynced GPU updates can bypass due(), including bootstrap frames
        // that do not swap. Keep their early attempts from accumulating a
        // future deadline that would starve the CPU-rendered options book.
        if (!due(now)) return;
        if (!started || (int)(now - next) > 100) {
            next = now; remainder = 0; started = true;
        }
        do {
            next += 16;
            remainder += 40;
            if (remainder >= 60) { ++next; remainder -= 60; }
        } while ((int)(now - next) >= 0);
    }
};
}
#endif
