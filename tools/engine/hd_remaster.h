#ifndef COMMON_HD_REMASTER_H
#define COMMON_HD_REMASTER_H
#include "graphics/surface.h"
#include "common/hd_color_grade.h"
#include "common/system.h"
#include "common/array.h"

// Engine/backend handoff, owned by this single-process native runtime. Surfaces
// are CPU staging buffers; the backend owns all GL objects and their lifetimes.
namespace HdRemaster {
struct Sample { double at = 0, cpu = 0, gpu = -1, interval = 0, native = 0, motion = 0, scene = 0, backend = 0; int room = 0, cameraX = 0, cameraY = 0; };
struct State {
    bool (*capture)(Graphics::Surface &) = nullptr;
    double (*highResTime)() = nullptr;
    bool available = false, active = false, ui = false, dof = false;
    bool recording = false, synchronized60 = false;
    int room = 0, viewportWidth = 640, viewportHeight = 480;
    int drawableWidth = 0, drawableHeight = 0, backgroundX = 0, backgroundY = 0;
    int maskPlanes = 0, maskOffset = 0, maskEdge = 2, maskDepth = 1;
    int radius = 0, scale = 4, intensity = 100, revision = 0;
    uint generation = 0, coverageGeneration = 0;
    uint uploadedCoverageGeneration = ~0u;
    Graphics::Surface scene, coverage, reference;
    Common::Array<byte> wideCoverage;
    bool compareReady = false;
    const Graphics::Surface *background = nullptr, *overlay = nullptr;
    HdColorGrade::Grade grade;
    double cpuNative = 0, cpuMotion = 0, cpuScene = 0, cpuBackend = 0;
    double cpuWork = 0, lastSwap = 0, lastInterval = 0;
    double summaryTime = 0, summaryCpu = 0, fps = 0, cpuMs = 0;
    uint summaryFrames = 0;
    unsigned sampleCount = 0, droppedSamples = 0, recordSerial = 0;
    Sample samples[32768];
    void presented(double now) {
        lastInterval = lastSwap ? now - lastSwap : 0;
        lastSwap = now;
        if (lastInterval > 0) {
            summaryTime += lastInterval; summaryCpu += cpuWork; ++summaryFrames;
            if (summaryTime >= 1000) {
                fps = summaryFrames * 1000.0 / summaryTime; cpuMs = summaryCpu / summaryFrames;
                summaryTime = summaryCpu = 0; summaryFrames = 0;
            }
        }
        if (recording) {
            if (sampleCount < 32768) {
                Sample &s = samples[sampleCount++];
                s.native = cpuNative; s.motion = cpuMotion; s.scene = cpuScene; s.backend = cpuBackend;
                s.at = now; s.cpu = cpuWork; s.gpu = -1; s.interval = lastInterval; s.room = room; s.cameraX = backgroundX / scale; s.cameraY = backgroundY / scale;
            } else ++droppedSamples;
        }
        cpuWork = cpuNative = cpuMotion = cpuScene = cpuBackend = 0;
    }
};
inline State &state() { static State instance; return instance; }
inline double milliseconds() { return state().highResTime ? state().highResTime() : g_system->getMillis(); }
inline unsigned opacity(unsigned source, unsigned destination) {
    return source + (destination * (255 - source) + 127) / 255;
}
inline void resize(Graphics::Surface &surface, int width, int height) {
    if (surface.w == width && surface.h == height && surface.getPixels()) return;
    surface.free(); surface.create(width, height, Graphics::PixelFormat::createFormatRGBA32());
}
}
#endif
