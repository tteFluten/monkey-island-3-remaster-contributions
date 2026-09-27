// Cached native-resolution coverage in full room coordinates. Reviewed regions
// handle painted water in panoramas and tall rooms; cannon/waterline retain
// their connected-surface tracing. Regenerate only when artwork changes.
struct HdWaterSurface {
    Common::Array<byte> depth;
    const void *pixels = nullptr;
    int room = -1, revision = -1, width = 0, height = 0, scale = 0;
    float reflectionIntercept = 0, reflectionSlope = 0;
    bool valid = false;

    bool prepare(const Graphics::Surface &background, int currentRoom, int currentRevision, int currentScale) {
        const bool mapped = HdWater::mappedRoom(currentRoom);
        if ((!HdWater::fullSurface(currentRoom) && !mapped) || currentScale <= 0 ||
            !background.getPixels() || background.w < currentScale || background.h < currentScale ||
            (!mapped && (background.w != 640 * currentScale || background.h != 480 * currentScale)))
            return false;
        if (pixels == background.getPixels() && room == currentRoom && revision == currentRevision && scale == currentScale)
            return valid;
        pixels = background.getPixels(); room = currentRoom; revision = currentRevision; scale = currentScale;
        width = background.w / scale; height = background.h / scale;
        depth.resize(width * height); memset(depth.data(), 0, depth.size());
        Common::Array<byte> water;
        water.resize(width * height);
        for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
            byte r, g, b;
            background.format.colorToRGB(background.getPixel(x * scale + scale / 2, y * scale + scale / 2), r, g, b);
            // The cannon view's sea starts below its authored horizon. The
            // similarly teal sky and fort must never join its water region.
            water[y * width + x] = mapped
                ? (HdWater::mapped(currentRoom, (x + 0.5) * 1000 / width, (y + 0.5) * 1000 / height, r, g, b) ? 2 : 0)
                : ((currentRoom != 10 || y >= height * 3 / 8) && HdWater::waterlineColor(r, g, b) ? 1 : 0);
        }
        Common::Array<int> pending, shoreline;
        shoreline.resize(width);
        for (int x = 0; x < width; ++x) {
            shoreline[x] = height;
            if (mapped) continue;
            // The cannon view is enclosed by a wooden gunport, including the
            // bottom edge. Seed its sea from the interior instead of the rail.
            if (currentRoom == 10 && (x < width / 3 || x >= width * 2 / 3)) continue;
            const int seed = (currentRoom == 10 ? height * 2 / 3 : height - 1) * width + x;
            if (water[seed]) { water[seed] = 2; pending.push_back(seed); }
        }
        for (uint i = 0; i < pending.size(); ++i) {
            const int pixel = pending[i], x = pixel % width, y = pixel / width;
            shoreline[x] = MIN(shoreline[x], y);
            auto visit = [&](int neighbor) {
                if (water[neighbor] == 1) { water[neighbor] = 2; pending.push_back(neighbor); }
            };
            if (x > 0) visit(pixel - 1);
            if (x + 1 < width) visit(pixel + 1);
            if (y > 0) visit(pixel - width);
            if (y + 1 < height) visit(pixel + width);
        }
        // The shoreline mask follows individual hull details, but a mirror
        // plane must not: reflecting around every pixel step shears the hull.
        // Fit one continuous sloping line through the visible water boundary.
        double count = 0, sumX = 0, sumY = 0, sumXX = 0, sumXY = 0;
        for (int x = 0; x < width; ++x) if (shoreline[x] < height &&
                (currentRoom != 10 || (x >= width / 4 && x < width * 3 / 4))) {
            const double px = x + 0.5, py = shoreline[x];
            ++count; sumX += px; sumY += py; sumXX += px * px; sumXY += px * py;
        }
        const double denominator = count * sumXX - sumX * sumX;
        reflectionSlope = denominator > 0 ? (count * sumXY - sumX * sumY) / denominator : 0;
        reflectionIntercept = count > 0 ? (sumY - reflectionSlope * sumX) / count : height;
        unsigned covered = 0;
        if (currentRoom == 10 || mapped) {
            // Unlike the open waterline, keep all four gunport edges and any
            // enclosed dry detail. Distance to dry paint softens refraction
            // before it reaches the wood, rather than filling whole columns.
            Common::Array<uint16> edge;
            edge.resize(width * height);
            covered = HdWater::surfaceDepth(water.data(), width, height, edge.data(), depth.data(), mapped ? 1 : 2);
            valid = covered >= (mapped ? 8u : (unsigned)(width * 20));
            return valid;
        }
        for (int x = 0; x < width; ++x) {
            const int shore = shoreline[x];
            // Fill the entire water column, including warm highlights and
            // dark ripples enclosed by the connected surface. Isolated teal
            // details on the ship never enter the flood fill.
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
