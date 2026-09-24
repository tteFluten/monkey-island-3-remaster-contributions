// Static SVG costume decoder. NanoSVG is already bundled with the pinned engine.
// Kept independent of ScummVM surfaces so the exact decoder can be tested alone.
#ifndef SCUMM_QUIVER_SVG_H
#define SCUMM_QUIVER_SVG_H
#include <cmath>
#include <cctype>
#include <string>
#include <vector>
#include "graphics/nanosvg/nanosvg.h"
#include "graphics/nanosvg/nanosvgrast.h"

namespace QuiverSVG {
inline bool documentSupported(const std::string &xml) {
    if (xml.empty() || xml.size() > 8 * 1024 * 1024 || xml.find('\0') != std::string::npos) return false;
    const std::string allowed = "|svg|g|defs|path|rect|circle|ellipse|polygon|polyline|line|linearGradient|radialGradient|stop|title|desc|";
    std::vector<std::string> stack;
    bool root = false, ended = false;
    size_t i = 0;
    while (i < xml.size()) {
        if (xml[i] != '<') {
            if (stack.empty() && !std::isspace((unsigned char)xml[i])) return false;
            ++i; continue;
        }
        if (xml.compare(i, 4, "<!--") == 0) {
            size_t end = xml.find("-->", i + 4);
            if (end == std::string::npos) return false;
            i = end + 3; continue;
        }
        if (xml.compare(i, 5, "<?xml") == 0 && !root) {
            size_t end = xml.find("?>", i + 5);
            if (end == std::string::npos) return false;
            i = end + 2; continue;
        }
        ++i;
        bool closing = i < xml.size() && xml[i] == '/';
        if (closing) ++i;
        size_t start = i;
        while (i < xml.size() && std::isalnum((unsigned char)xml[i])) ++i;
        std::string tag = xml.substr(start, i - start);
        if (tag.empty() || allowed.find("|" + tag + "|") == std::string::npos) return false;
        if (!root) { if (tag != "svg" || closing) return false; root = true; }
        else if (ended || (!closing && tag == "svg")) return false;
        bool selfClosing = false;
        while (i < xml.size()) {
            while (i < xml.size() && std::isspace((unsigned char)xml[i])) ++i;
            if (i == xml.size()) return false;
            if (xml[i] == '>') { ++i; break; }
            if (xml[i] == '/' && i + 1 < xml.size() && xml[i + 1] == '>') {
                if (closing) return false;
                selfClosing = true; i += 2; break;
            }
            if (closing) return false;
            start = i;
            while (i < xml.size() && (std::isalnum((unsigned char)xml[i]) || xml[i] == ':' || xml[i] == '-' || xml[i] == '_')) ++i;
            std::string attr = xml.substr(start, i - start);
            if (attr.empty()) return false;
            while (i < xml.size() && std::isspace((unsigned char)xml[i])) ++i;
            if (i == xml.size() || xml[i++] != '=') return false;
            while (i < xml.size() && std::isspace((unsigned char)xml[i])) ++i;
            if (i == xml.size() || (xml[i] != '\'' && xml[i] != '"')) return false;
            char quote = xml[i++]; start = i;
            while (i < xml.size() && xml[i] != quote) ++i;
            if (i == xml.size()) return false;
            std::string value = xml.substr(start, i++ - start);
            for (size_t k = 0; k < attr.size(); ++k) attr[k] = std::tolower((unsigned char)attr[k]);
            if (attr.compare(0, 2, "on") == 0 || attr == "class" || attr == "clip-path" || attr == "mask" || attr == "filter") return false;
            if (attr == "href" || attr == "xlink:href" || attr == "src") {
                if (value.empty() || value[0] != '#') return false;
            }
            // NanoSVG does not access external resources. Reject unsupported
            // declarations instead of silently rendering incomplete artwork.
            for (size_t k = 0; k < value.size(); ++k) value[k] = std::tolower((unsigned char)value[k]);
            if (attr == "style" && (value.find("clip-path") != std::string::npos ||
                value.find("mask") != std::string::npos || value.find("filter") != std::string::npos)) return false;
            if (value.find("@import") != std::string::npos || value.find("javascript:") != std::string::npos ||
                value.find("&") != std::string::npos || value.find("<") != std::string::npos) return false;
            size_t url = value.find("url(");
            if (url != std::string::npos) {
                size_t k = value.find_first_not_of(" \t\r\n\"'", url + 4);
                if (k == std::string::npos || value[k] != '#') return false;
            }
        }
        if (i == xml.size() && xml[i - 1] != '>') return false;
        if (closing) {
            if (stack.empty() || stack.back() != tag) return false;
            stack.pop_back();
        } else if (!selfClosing) stack.push_back(tag);
        if (stack.size() > 64) return false;
        if (stack.empty()) ended = true;
    }
    return root && ended && stack.empty();
}

inline bool render(const std::string &xml, int width, int height, std::vector<unsigned char> &rgba) {
    rgba.clear();
    if (width <= 0 || height <= 0 || width > 8192 || height > 8192 ||
        (long long)width * height > 16777216 || !documentSupported(xml)) return false;
    std::vector<char> source(xml.begin(), xml.end()); source.push_back(0);
    NSVGimage *svg = nsvgParse(source.data(), "px", 96);
    if (!svg) return false;
    bool valid = svg->shapes && std::isfinite(svg->width) && std::isfinite(svg->height) && svg->width > 0 && svg->height > 0;
    float scale = valid ? width / svg->width : 0;
    if (valid && std::fabs(svg->height * scale - height) > .5f) valid = false;
    for (NSVGshape *s = svg->shapes; valid && s; s = s->next) {
        for (int i = 0; i < 4; ++i) if (!std::isfinite(s->bounds[i])) valid = false;
        for (NSVGpath *p = s->paths; valid && p; p = p->next)
            for (int i = 0; i < p->npts * 2; ++i)
                if (!std::isfinite(p->pts[i]) || std::fabs(p->pts[i]) > 10000000) valid = false;
    }
    NSVGrasterizer *rasterizer = valid ? nsvgCreateRasterizer() : nullptr;
    if (rasterizer) {
        rgba.resize((size_t)width * height * 4, 0);
        nsvgRasterize(rasterizer, svg, 0, 0, scale, rgba.data(), width, height, width * 4);
        nsvgDeleteRasterizer(rasterizer);
    }
    nsvgDelete(svg);
    return rasterizer != nullptr;
}
}
#endif
