#ifndef SCUMM_HD_ACTOR_LIGHTING_H
#define SCUMM_HD_ACTOR_LIGHTING_H

namespace HdActorLighting {
struct Tint {
    int channel[3] = {255, 255, 255};
    Tint enhanced(bool warmRoom = false) const {
        Tint result;
        int strong[3], peak = 0;
        for (int c = 0; c < 3; ++c) {
            if (channel[c] > peak) peak = channel[c];
            int value = (channel[c] * channel[c] + 127) / 255;
            strong[c] = value > 272 ? 272 : value;
        }
        // Half the previous effect, blended toward neutral. Let the neutral
        // endpoint fall during deep fades so true black remains black.
        const int neutral = peak < 128 ? peak * 2 : 255;
        if (warmRoom) {
            // Guybrush and Wally share one orange hue in the cannon room.
            // Keep live luminance separate: green/red native palette changes
            // still change brightness without giving the actors different hues.
            const int luminance = (54 * strong[0] + 183 * strong[1] + 19 * strong[2] + 128) / 256;
            const int brightness = (neutral + luminance + 1) / 2;
            const int orange[3] = {255, 233, 198};
            for (int c = 0; c < 3; ++c)
                result.channel[c] = (brightness * orange[c] + 127) / 255;
        } else {
            for (int c = 0; c < 3; ++c)
                result.channel[c] = (neutral + strong[c] + 1) / 2;
        }
        return result;
    }
    unsigned int apply(unsigned int rgba) const {
        unsigned int result = rgba & 0xff000000u;
        for (int c = 0; c < 3; ++c) {
            int value = ((rgba >> (c * 8)) & 255) * channel[c] / 255;
            if (value > 255) value = 255;
            result |= (unsigned int)value << (c * 8);
        }
        return result;
    }
};

// Use one observed pose's color weights until the actor changes room, costume,
// or palette mapping. Animation/occlusion must not change the inferred tint.
// Live palette values are still evaluated every frame using these same weights.
struct StableSamples {
    unsigned int weights[256] = {};
    unsigned char mapping[256] = {};
    int room = -1, costume = -1;
    bool ready = false;
    void reset() { room = costume = -1; ready = false; }
    const unsigned int *update(int nextRoom, int nextCostume,
                               const unsigned char *nextMapping,
                               const unsigned int *usage) {
        bool changed = room != nextRoom || costume != nextCostume;
        for (int i = 0; i < 256; ++i)
            if (mapping[i] != nextMapping[i]) changed = true;
        if (changed) {
            ready = false; room = nextRoom; costume = nextCostume;
            for (int i = 0; i < 256; ++i) mapping[i] = nextMapping[i];
        }
        if (!ready) {
            for (int i = 0; i < 256; ++i) {
                weights[i] = usage[i];
                if (usage[i]) ready = true;
            }
        }
        return weights;
    }
};

// Recover the native integer RGB scale from the colors this actor actually
// painted. Voting over quantization intervals avoids amplifying rounding in
// dark colors. Unused costume palette entries must never influence lighting.
inline Tint fromPalette(const unsigned char *base, const unsigned char *current,
                        const unsigned int *usage) {
    Tint tint;
    for (int c = 0; c < 3; ++c) {
        int changes[514] = {};
        bool sampled = false, allBlack = true;
        for (int i = 0; i < 256; ++i) {
            if (!usage[i]) continue;
            const int source = base[i * 3 + c], target = current[i * 3 + c];
            if (!source) continue;
            sampled = true;
            if (target) allBlack = false;
            int first = (target * 255 + source - 1) / source;
            int last = target == 255 ? 512 : ((target + 1) * 255 - 1) / source;
            if (first > 512) continue;
            if (last > 512) last = 512;
            changes[first] += usage[i];
            changes[last + 1] -= usage[i];
        }
        // A fully darkened channel must stay black even when integer rounding
        // also permits a tiny nonzero scale for the native sampled colors.
        if (sampled && allBlack) {
            tint.channel[c] = 0;
            continue;
        }
        int score = 0, bestScore = 0, bestDistance = 0;
        for (int gain = 0; gain <= 512; ++gain) {
            score += changes[gain];
            int distance = gain > 255 ? gain - 255 : 255 - gain;
            if (score > bestScore || (score == bestScore && distance < bestDistance)) {
                bestScore = score; bestDistance = distance;
                tint.channel[c] = gain;
            }
        }
    }
    return tint;
}
}
#endif
