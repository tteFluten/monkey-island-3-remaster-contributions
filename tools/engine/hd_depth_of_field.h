#ifndef SCUMM_HD_DEPTH_OF_FIELD_H
#define SCUMM_HD_DEPTH_OF_FIELD_H
#include <vector>

// Camera depth of field for the flat HD room paintings. The original z-planes
// mark scenery that occludes actors; that foreground receives a soft blur while
// the rest of the painting, actors and UI stay sharp. Draw-time only: the
// stored artwork, palette and coordinates are never altered.
namespace HdDepthOfField {
inline int level(int configured) {
    return configured < 0 ? 0 : configured > 2 ? 2 : configured;
}

// Blur strength (approximate Gaussian sigma) in HD pixels: 2 or 4 native px.
inline int radius(int level, int scale) {
    return level <= 0 ? 0 : (level == 1 ? 2 : 4) * scale;
}

// Live tuning, stored as integers in the engine config. Blur is in tenths of
// a native pixel (0 = use the Low/High preset), edge softness in native
// pixels, intensity in percent. `depth` is how many z-planes a pixel must be
// in to count as foreground (1 = any; higher keeps only the nearest scenery).
struct Tuning {
    int blurTenths = 0, edge = 2, intensity = 100, depth = 1;
};
inline int clampInt(int v, int lo, int hi) {
    return v < lo ? lo : v > hi ? hi : v;
}
inline int presetTenths(int level) {
    return level <= 0 ? 0 : level == 1 ? 20 : 40;
}
inline Tuning tuning(int blurTenths, int edge, int intensity, int depth = 1) {
    Tuning t;
    t.blurTenths = blurTenths <= 0 ? 0 : clampInt(blurTenths, 5, 120);
    t.edge = clampInt(edge, 0, 12);
    t.intensity = clampInt(intensity, 0, 100);
    t.depth = clampInt(depth, 1, 7);
    return t;
}
// Effective sigma in tenths of a native pixel, before HD scaling.
inline int blurTenths(int level, const Tuning &t) {
    return level <= 0 ? 0 : t.blurTenths > 0 ? t.blurTenths : presetTenths(level);
}
inline int radiusTenths(int tenths, int scale) {
    return (tenths * scale + 5) / 10;
}
// One hotkey step: blur by 0.5 px, edge by 1 px, intensity by 10%, depth by 1.
inline Tuning step(int level, Tuning t, int blurDelta, int edgeDelta, int intensityDelta, int depthDelta = 0) {
    if (blurDelta) t.blurTenths = clampInt(blurTenths(level > 0 ? level : 1, t) + blurDelta * 5, 5, 120);
    t.edge = clampInt(t.edge + edgeDelta, 0, 12);
    t.intensity = clampInt(t.intensity + intensityDelta * 10, 0, 100);
    t.depth = clampInt(t.depth + depthDelta, 1, 7);
    return t;
}

// The blur is low frequency; keep the cache at half the HD resolution.
inline int factor(int scale) {
    return scale > 2 ? scale / 2 : 1;
}

namespace detail {
inline int clampIndex(int i, int n) {
    return i < 0 ? 0 : i >= n ? n - 1 : i;
}

// One box pass (width 2r+1) with clamped edges; flat input stays exact.
inline void box(std::vector<int> &plane, std::vector<int> &line, int w, int h, int r, bool vertical) {
    const int count = vertical ? w : h, length = vertical ? h : w;
    const int step = vertical ? w : 1, stride = vertical ? 1 : w;
    const int n = 2 * r + 1;
    line.resize(length);
    for (int c = 0; c < count; ++c) {
        int *base = &plane[c * stride];
        for (int i = 0; i < length; ++i) line[i] = base[i * step];
        int sum = 0;
        for (int j = -r; j <= r; ++j) sum += line[clampIndex(j, length)];
        for (int i = 0; i < length; ++i) {
            base[i * step] = (sum + n / 2) / n;
            sum += line[clampIndex(i + r + 1, length)] - line[clampIndex(i - r, length)];
        }
    }
}

// Fixed-point (1/256) position of an output pixel center in a grid whose
// cells each cover `cell` output pixels, clamped to the grid.
inline void locate(int x, int cell, int size, int &i0, int &i1, int &weight) {
    int f = (2 * x + 1) * 128 / cell - 128;
    if (f < 0) f = 0;
    i0 = f >> 8;
    weight = f & 255;
    if (i0 >= size - 1) {
        i0 = size - 1;
        weight = 0;
    }
    i1 = i0 + 1 < size ? i0 + 1 : i0;
}
}

// Box-downsample an RGB(A) byte image by `factor`, then approximate a Gaussian
// of sigma `radius` HD pixels with three separable box passes. Opaque output.
inline void blur(const unsigned char *src, int pitch, int bytesPerPixel, int w, int h,
                 int factor, int radius, std::vector<unsigned int> &out, int &outW, int &outH) {
    if (factor < 1) factor = 1;
    outW = (w + factor - 1) / factor;
    outH = (h + factor - 1) / factor;
    std::vector<int> planes[3];
    for (auto &p : planes) p.assign(outW * outH, 0);
    for (int oy = 0; oy < outH; ++oy)
        for (int ox = 0; ox < outW; ++ox) {
            int sum[3] = {0, 0, 0}, n = 0;
            for (int y = oy * factor; y < h && y < (oy + 1) * factor; ++y)
                for (int x = ox * factor; x < w && x < (ox + 1) * factor; ++x, ++n) {
                    const unsigned char *p = src + y * pitch + x * bytesPerPixel;
                    for (int c = 0; c < 3; ++c) sum[c] += p[c];
                }
            for (int c = 0; c < 3; ++c) planes[c][oy * outW + ox] = (sum[c] + n / 2) / n;
        }
    // Three box passes of radius r have variance ~r(r+1); sigma ~ r.
    const int r = (radius + factor / 2) / factor;
    if (r > 0) {
        std::vector<int> line;
        for (auto &p : planes)
            for (int pass = 0; pass < 3; ++pass) {
                detail::box(p, line, outW, outH, r, false);
                detail::box(p, line, outW, outH, r, true);
            }
    }
    out.resize(outW * outH);
    for (int i = 0; i < outW * outH; ++i)
        out[i] = planes[0][i] | (planes[1][i] << 8) | (planes[2][i] << 16) | 0xff000000u;
}

// Bilinear upsample of the reduced blur at HD pixel (x, y).
inline unsigned int sample(const unsigned int *small, int sw, int sh, int factor, int x, int y) {
    int x0, x1, ax, y0, y1, ay;
    detail::locate(x, factor, sw, x0, x1, ax);
    detail::locate(y, factor, sh, y0, y1, ay);
    const unsigned int p00 = small[y0 * sw + x0], p10 = small[y0 * sw + x1];
    const unsigned int p01 = small[y1 * sw + x0], p11 = small[y1 * sw + x1];
    unsigned int result = 0xff000000u;
    for (int c = 0; c < 24; c += 8) {
        const int top = ((p00 >> c) & 255) * (256 - ax) + ((p10 >> c) & 255) * ax;
        const int bottom = ((p01 >> c) & 255) * (256 - ax) + ((p11 >> c) & 255) * ax;
        result |= (unsigned int)((top * (256 - ay) + bottom * ay + 32768) >> 16) << c;
    }
    return result;
}

// Foreground coverage (0..255) per native viewport pixel. Each z-plane 1..n-1
// masks everything in front of actors at one depth, so the planes overlap and
// the number of planes covering a pixel grows as the scenery gets nearer.
// Pixels in at least `depth` planes are foreground, weighted up to 255 for the
// nearest (in every plane), then feathered by a `feather` box so edges do not
// step at native pixel size. `row(y, z)` returns a live mask row or null; bits
// use the same camera offset as HdObjectDepth::masked.
template <typename RowFn>
inline bool coverage(RowFn row, int planes, int visW, int visH, int cameraBitOffset,
                     int feather, std::vector<unsigned char> &out, int depth = 1) {
    out.assign(visW * visH, 0);
    const int total = planes - 1;
    if (total < 1) return false;
    depth = clampInt(depth, 1, total);
    std::vector<int> plane(visW * visH, 0);
    for (int y = 0; y < visH; ++y)
        for (int z = 1; z < planes; ++z) {
            const unsigned char *mask = row(y, z);
            if (!mask) continue;
            for (int x = 0; x < visW; ++x)
                plane[y * visW + x] += (mask[(x + cameraBitOffset) / 8] >>
                    (7 - ((x + cameraBitOffset) & 7))) & 1;
        }
    bool any = false;
    const int range = total - depth + 1;
    for (int &value : plane) {
        value = value < depth ? 0 : (255 * (value - depth + 1) + range / 2) / range;
        any = any || value;
    }
    if (!any) return false;
    if (feather > 0) {
        std::vector<int> line;
        detail::box(plane, line, visW, visH, feather, false);
        detail::box(plane, line, visW, visH, feather, true);
    }
    for (int i = 0; i < visW * visH; ++i) out[i] = (unsigned char)plane[i];
    return true;
}

// Bilinear coverage at HD pixel (x, y) of a native coverage map.
inline int coverageAt(const unsigned char *cover, int visW, int visH, int scale, int x, int y) {
    int x0, x1, ax, y0, y1, ay;
    detail::locate(x, scale, visW, x0, x1, ax);
    detail::locate(y, scale, visH, y0, y1, ay);
    const int top = cover[y0 * visW + x0] * (256 - ax) + cover[y0 * visW + x1] * ax;
    const int bottom = cover[y1 * visW + x0] * (256 - ax) + cover[y1 * visW + x1] * ax;
    return (top * (256 - ay) + bottom * ay + 32768) >> 16;
}

// Blend toward the blurred painting by coverage; keep the sharp pixel's alpha.
inline unsigned int mix(unsigned int sharp, unsigned int blurred, int alpha) {
    if (alpha <= 0) return sharp;
    if (alpha >= 255) return (blurred & 0xffffffu) | (sharp & 0xff000000u);
    unsigned int result = sharp & 0xff000000u;
    for (int c = 0; c < 24; c += 8) {
        const unsigned int s = (sharp >> c) & 255, b = (blurred >> c) & 255;
        result |= ((s * (255 - alpha) + b * alpha + 127) / 255) << c;
    }
    return result;
}
}
#endif
