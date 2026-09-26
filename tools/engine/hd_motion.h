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

// Room 10's aiming barrel (costume 35) changes drawing cels without moving
// its actor. Track that visual pose separately from simulation coordinates.
struct CannonPose {
    int cel = -1, left = 0, top = 0, width = 0, height = 0;
    int sourceWidth = 0, sourceHeight = 0;
    bool mirror = false;
};
struct CannonAim {
    CannonPose from, to;
    int actor = -1, revision = -1;
    bool moving = false;
    void sample(const CannonPose &next, int nextActor, int nextRevision, bool reset) {
        const int step = next.cel - to.cel;
        reset = reset || actor != nextActor || revision != nextRevision ||
            to.cel < 0 || next.cel < 0 || next.cel > 15 ||
            next.mirror != to.mirror || step > 4 || step < -4;
        from = reset ? next : to;
        to = next; actor = nextActor; revision = nextRevision;
        moving = !reset && (from.cel != to.cel || from.left != to.left ||
            from.top != to.top || from.width != to.width || from.height != to.height);
    }
    // Interpolate premultiplied color, then return straight RGBA for the
    // normal compositor. Transparent padding must not create dark fringes.
    static unsigned int blend(unsigned int a, unsigned int b, unsigned int fraction) {
        if (!fraction) return a;
        if (fraction >= 1024) return b;
        const unsigned int wa = (a >> 24) * (1024 - fraction), wb = (b >> 24) * fraction;
        const unsigned int weight = wa + wb;
        if (!weight) return 0;
        unsigned int result = ((weight + 512) / 1024) << 24;
        for (int shift = 0; shift < 24; shift += 8)
            result |= ((((a >> shift) & 255) * wa + ((b >> shift) & 255) * wb + weight / 2) / weight) << shift;
        return result;
    }
};
}
#endif
