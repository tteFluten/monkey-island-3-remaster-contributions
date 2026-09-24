#ifndef SCUMM_HD_FRAME_PACER_H
#define SCUMM_HD_FRAME_PACER_H

namespace HdPresentation {
// Millisecond clock with fractional carry: 60 intervals total exactly 1000 ms.
// Presentation never changes SCUMM's script, actor, audio, or movie timers.
struct FramePacer {
    unsigned int next = 0, remainder = 0;
    bool started = false;
    bool due(unsigned int now) const { return !started || (int)(now - next) >= 0; }
    unsigned int delay(unsigned int now) const { return due(now) ? 0 : next - now; }
    void presented(unsigned int now) {
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
