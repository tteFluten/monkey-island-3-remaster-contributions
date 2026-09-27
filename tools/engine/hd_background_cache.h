#ifndef HD_BACKGROUND_CACHE_H
#define HD_BACKGROUND_CACHE_H

#include "common/fs.h"
#include "graphics/surface.h"
#include "image/png.h"
#include <SDL_thread.h>
#include <SDL_atomic.h>
#include <list>
#include <deque>

namespace HdBackground {
// Shared by the room loader and widescreen renderer. Only PNG decoding runs
// on the worker; queue/cache ownership and all GPU work stay on the main thread.
class Cache {
    struct Entry {
        Common::String path;
        Graphics::Surface pixels;
        ~Entry() { pixels.free(); }
    };
    struct Job {
        Common::String path;
        Graphics::Surface pixels;
        unsigned generation = 0, plan = 0;
        bool ok = false;
        SDL_atomic_t done;
    } job;
    std::list<Entry> entries;
    std::deque<Common::String> queue;
    SDL_Thread *thread = nullptr;
    size_t bytes = 0;
    const size_t budget = 256 * 1024 * 1024;
    unsigned generation = 1, plan = 0;
    int room = -1;

    static bool decode(const Common::String &path, Graphics::Surface &pixels) {
#ifdef USE_PNG
        Common::FSNode node((Common::Path(path)));
        Common::SeekableReadStream *file = node.createReadStream();
        if (!file) return false;
        Image::PNGDecoder decoder;
        const bool loaded = decoder.loadStream(*file);
        delete file;
        if (!loaded || !decoder.getSurface()) return false;
        Graphics::Surface *rgba = decoder.getSurface()->convertTo(Graphics::PixelFormat::createFormatRGBA32(),
            decoder.getPalette().data(), decoder.getPalette().size());
        if (!rgba) return false;
        pixels.free(); pixels = *rgba; delete rgba;
        return true;
#else
        return false;
#endif
    }
    static int run(void *data) {
        Job &pending = *static_cast<Job *>(data);
        pending.ok = decode(pending.path, pending.pixels);
        SDL_AtomicSet(&pending.done, 1);
        return 0;
    }
    bool contains(const Common::String &path) const {
        for (const auto &entry : entries) if (entry.path == path) return true;
        return false;
    }
    bool copy(const Common::String &path, Graphics::Surface &out) {
        for (auto it = entries.begin(); it != entries.end(); ++it) if (it->path == path) {
            out.free(); out.copyFrom(it->pixels);
            entries.splice(entries.begin(), entries, it);
            return true;
        }
        return false;
    }
    void insert(const Common::String &path, Graphics::Surface &pixels, bool demanded = false) {
        const size_t size = size_t(pixels.pitch) * pixels.h;
        if (size > budget || contains(path)) { pixels.free(); return; }
        // Speculation may use spare memory, but must not evict rooms that
        // already loaded successfully. Demand loads alone drive LRU eviction.
        if (!demanded && bytes + size > budget) { pixels.free(); return; }
        while (!entries.empty() && bytes + size > budget) {
            bytes -= size_t(entries.back().pixels.pitch) * entries.back().pixels.h;
            entries.pop_back();
        }
        entries.emplace_front();
        entries.front().path = path;
        entries.front().pixels = pixels;
        pixels = Graphics::Surface();
        bytes += size;
    }
    void collect() {
        if (!thread || !SDL_AtomicGet(&job.done)) return;
        SDL_WaitThread(thread, nullptr); thread = nullptr;
        // A room change or live asset reload must not admit a late result.
        if (job.ok && job.generation == generation && job.plan == plan)
            insert(job.path, job.pixels);
        job.pixels.free();
    }
public:
    ~Cache() { shutdown(); }
    void invalidate() {
        ++generation; ++plan; room = -1;
        queue.clear(); entries.clear(); bytes = 0;
        // Never join a busy decode when changing the asset path/revision.
    }
    void shutdown() {
        if (thread) SDL_WaitThread(thread, nullptr);
        thread = nullptr; job.pixels.free(); invalidate();
    }
    void beginRoom(int nextRoom) {
        if (room == nextRoom) return;
        room = nextRoom; ++plan; queue.clear();
    }
    void request(const Common::String &path) {
        if (path.empty() || contains(path)) return;
        if (thread && job.path == path && job.generation == generation) return;
        for (const auto &queued : queue) if (queued == path) return;
        queue.push_back(path);
    }
    void step() {
        collect();
        if (thread) return;
        while (!queue.empty()) {
            const Common::String path = queue.front(); queue.pop_front();
            if (contains(path)) continue;
            job.path = path; job.generation = generation; job.plan = plan; job.ok = false;
            SDL_AtomicSet(&job.done, 0);
            thread = SDL_CreateThread(run, "hd-background-prefetch", &job);
            return; // Thread failure retains the normal demand-load fallback.
        }
    }
    bool load(const Common::String &path, Graphics::Surface &out) {
        if (copy(path, out)) return true;
        // The actual destination is required before its first composition.
        // Reuse its in-flight decode instead of decoding the PNG twice. Never
        // wait for a speculative decode of an unrelated room.
        if (thread && job.path == path && job.generation == generation) {
            SDL_WaitThread(thread, nullptr); thread = nullptr;
            if (!job.ok) { job.pixels.free(); return false; }
            out.free(); out.copyFrom(job.pixels);
            insert(path, job.pixels, true);
            return true;
        }
        collect();
        if (copy(path, out)) return true;
        Graphics::Surface pixels;
        if (!decode(path, pixels)) return false;
        out.free(); out.copyFrom(pixels);
        insert(path, pixels, true);
        return true;
    }
};

inline Cache &cache() { static Cache instance; return instance; }
}
#endif
