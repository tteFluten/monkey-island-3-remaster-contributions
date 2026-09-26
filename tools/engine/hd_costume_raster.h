#ifndef SCUMM_HD_COSTUME_RASTER_H
#define SCUMM_HD_COSTUME_RASTER_H
#include <cstdint>
#include <list>
#include <vector>
#include "hd_costume_edge.h"
#include "hd_actor_lighting.h"

namespace HdCostumeRaster {
// Drawing-only cache: native animation still selects every original cel.
// Cache scaled, edge-corrected, lit pixels until geometry or lighting changes.
class Cache {
    struct Entry {
        const void *source;
        int costume, cel, sw, sh, pitch, w, h;
        bool mirror; int matte;
        HdActorLighting::Tint tint;
        std::vector<unsigned int> pixels;
    };
    std::list<Entry> entries;
    size_t bytes = 0;
    int room = -1, revision = -1;
public:
    void scope(int nextRoom, int nextRevision) {
        if (room == nextRoom && revision == nextRevision) return;
        room = nextRoom; revision = nextRevision; entries.clear(); bytes = 0;
    }
    const unsigned int *get(const unsigned int *source, int pitch, int sw, int sh,
                            int w, int h, int costume, int cel, bool mirror, int matte,
                            const HdActorLighting::Tint &tint) {
        const size_t size = size_t(w) * h * sizeof(unsigned int), budget = 64 * 1024 * 1024;
        if (!w || !h || size > budget) return nullptr;
        for (auto it = entries.begin(); it != entries.end(); ++it) {
            const Entry &e = *it;
            if (e.source == source && e.costume == costume && e.cel == cel && e.sw == sw && e.sh == sh &&
                e.pitch == pitch && e.w == w && e.h == h && e.mirror == mirror && e.matte == matte &&
                e.tint.channel[0] == tint.channel[0] && e.tint.channel[1] == tint.channel[1] && e.tint.channel[2] == tint.channel[2]) {
                entries.splice(entries.begin(), entries, it);
                return entries.front().pixels.data();
            }
        }
        while (!entries.empty() && bytes + size > budget) {
            bytes -= entries.back().pixels.size() * sizeof(unsigned int); entries.pop_back();
        }
        entries.emplace_front(); Entry &e = entries.front();
        e.source = source; e.costume = costume; e.cel = cel; e.sw = sw; e.sh = sh; e.pitch = pitch;
        e.w = w; e.h = h; e.mirror = mirror; e.matte = matte; e.tint = tint;
        e.pixels.resize(size_t(w) * h); bytes += size;
        for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
            int sx = x * sw / w; if (mirror) sx = sw - 1 - sx;
            const int sy = y * sh / h;
            const unsigned int raw = source[sy * pitch + sx];
            e.pixels[y * w + x] = (raw >> 24 || (matte == 3 && sy == sh - 1)) ? tint.apply(matte == 2 ? HdObjectDepth::edgeColor(source, pitch, sw, sh, sx, sy) : HdCostumeEdge::sample(source, pitch, sw, sh, sx, sy, matte)) : 0;
        }
        return e.pixels.data();
    }
};
}
#endif
