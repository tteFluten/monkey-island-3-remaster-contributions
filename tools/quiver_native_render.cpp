// Standalone verifier using the exact decoder compiled into the pinned engine.
// c++ -std=c++11 -O2 -I .playtest/engine/source -I tools/engine \
//   tools/quiver_native_render.cpp -o .context/quiver-native-render
#define NANOSVG_IMPLEMENTATION
#define NANOSVGRAST_IMPLEMENTATION
#include "quiver_svg.h"
#include <fstream>
#include <iterator>
#include <cstdlib>
#include <iostream>

int main(int argc, char **argv) {
    if (argc == 3 && std::string(argv[1]) == "--shapes") {
        std::ifstream input(argv[2], std::ios::binary);
        std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
        if (!QuiverSVG::documentSupported(text)) return 1;
        text.push_back(0);
        NSVGimage *svg = nsvgParse(&text[0], "px", 96);
        if (!svg) return 1;
        std::cout << "[";
        bool first = true;
        for (NSVGshape *s = svg->shapes; s; s = s->next) {
            if (!first) std::cout << ",";
            first = false;
            std::cout << "{\"id\":" << std::atoi(s->id) << ",\"bounds\":[";
            for (int i = 0; i < 4; ++i) { if (i) std::cout << ","; std::cout << s->bounds[i]; }
            std::cout << "],\"fill_type\":" << int(s->fill.type)
                      << ",\"fill_color\":" << s->fill.color
                      << ",\"stroke_type\":" << int(s->stroke.type)
                      << ",\"stroke_color\":" << s->stroke.color
                      << ",\"stroke_width\":" << s->strokeWidth
                      << ",\"opacity\":" << s->opacity
                      << ",\"fill_rule\":" << int(s->fillRule)
                      << ",\"visible\":" << ((s->flags & NSVG_FLAGS_VISIBLE) ? "true" : "false")
                      << ",\"paths\":[";
            bool firstPath = true;
            for (NSVGpath *p = s->paths; p; p = p->next) {
                if (!firstPath) std::cout << ",";
                firstPath = false;
                std::cout << "{\"closed\":" << (p->closed ? "true" : "false") << ",\"points\":[";
                for (int i = 0; i < p->npts; ++i) {
                    if (i) std::cout << ",";
                    std::cout << "[" << p->pts[i * 2] << "," << p->pts[i * 2 + 1] << "]";
                }
                std::cout << "]}";
            }
            std::cout << "]}";
        }
        std::cout << "]\n";
        nsvgDelete(svg);
        return 0;
    }
    if (argc != 5) {
        std::cerr << "Usage: quiver-native-render INPUT.svg OUTPUT.rgba WIDTH HEIGHT\n";
        return 2;
    }
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) return 2;
    std::string svg((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    std::vector<unsigned char> rgba;
    if (!QuiverSVG::render(svg, std::atoi(argv[3]), std::atoi(argv[4]), rgba)) return 1;
    std::ofstream output(argv[2], std::ios::binary);
    output.write(reinterpret_cast<const char *>(rgba.data()), rgba.size());
    return output ? 0 : 2;
}
