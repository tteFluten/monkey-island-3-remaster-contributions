#ifndef SCUMM_HD_MOTION_H
#define SCUMM_HD_MOTION_H

namespace HdMotion {
// A one-tick presentation delay gives bounded interpolation, never prediction.
// Time and coordinates here are drawing data, not SCUMM script/actor state.
struct Track {
    int fromX = 0, fromY = 0, x = 0, y = 0, identity = -1;
    bool moving = false;
    void sample(int nextX, int nextY, int nextIdentity, bool reset) {
        int dx = nextX - x, dy = nextY - y;
        reset = reset || identity != nextIdentity || dx > 160 || dx < -160 || dy > 160 || dy < -160;
        fromX = reset ? nextX : x; fromY = reset ? nextY : y;
        x = nextX; y = nextY; identity = nextIdentity;
        moving = fromX != x || fromY != y;
    }
    static int mix(int a, int b, unsigned int fraction) {
        const int value = (b - a) * (int)fraction;
        return a + (value < 0 ? -((-value + 512) / 1024) : (value + 512) / 1024);
    }
    int atX(unsigned int fraction) const { return mix(fromX, x, fraction); }
    int atY(unsigned int fraction) const { return mix(fromY, y, fraction); }
};
struct Clock {
    unsigned int sampled = 0, interval = 83;
    int room = -1;
    bool valid = false;
    bool sample(int nextRoom, unsigned int now, bool enabled) {
        const unsigned int elapsed = now - sampled;
        bool reset = !valid || room != nextRoom || elapsed > 250 || !enabled;
        if (!reset && elapsed >= 16) interval = elapsed;
        else interval = 83;
        sampled = now; room = nextRoom; valid = enabled;
        return reset;
    }
    unsigned int fraction(unsigned int now) const {
        unsigned int elapsed = now - sampled;
        return elapsed >= interval ? 1024 : elapsed * 1024 / interval;
    }
};
}
#endif
