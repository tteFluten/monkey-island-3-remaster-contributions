// A cached native-resolution depth mask for the full waterline surface. Scan
// upward from the image bottom so similarly colored details above the hull
// cannot become isolated water patches. Regenerate only when artwork changes.
struct HdWaterSurface {
    Common::Array<byte> depth;
    const void *pixels = nullptr;
    int room = -1, revision = -1, width = 0, height = 0, scale = 0;
    bool valid = false;

    bool prepare(const Graphics::Surface &background, int currentRoom, int currentRevision, int currentScale) {
        if (currentRoom != 11 || currentScale <= 0 ||
            background.w != 640 * currentScale || background.h != 480 * currentScale)
            return false;
        if (pixels == background.getPixels() && room == currentRoom && revision == currentRevision && scale == currentScale)
            return valid;
        pixels = background.getPixels(); room = currentRoom; revision = currentRevision; scale = currentScale;
        width = background.w / scale; height = background.h / scale;
        depth.resize(width * height); memset(depth.data(), 0, depth.size());
        unsigned covered = 0;
        for (int x = 0; x < width; ++x) {
            int shore = height;
            for (int y = height - 1; y >= 0; --y) {
                byte r, g, b;
                background.format.colorToRGB(background.getPixel(x * scale + scale / 2, y * scale + scale / 2), r, g, b);
                if (!HdWater::waterlineColor(r, g, b)) break;
                shore = y;
            }
            // Leave a two-pixel guard inside the paint boundary. Refraction
            // fades to zero here and cannot pull the hull into the water edge.
            for (int y = shore + 2; y < height; ++y) {
                depth[y * width + x] = MIN(255, y - shore - 1);
                ++covered;
            }
        }
        valid = covered >= (unsigned)(width * 20);
        return valid;
    }
};
static HdWaterSurface &hdWaterSurface() { static HdWaterSurface surface; return surface; }
