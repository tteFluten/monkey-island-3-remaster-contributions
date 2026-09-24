bool HdCostumeManager::loadSVG(const Common::String &path, int width, int height, Graphics::Surface &surf) {
    Common::FSNode file(Common::Path(path, Common::Path::kNativeSeparator));
    Common::SeekableReadStream *stream = file.createReadStream();
    if (!stream) return false;
    int64 size = stream->size();
    if (size <= 0 || size > 8 * 1024 * 1024) { delete stream; return false; }
    std::string text((size_t)size, '\0');
    bool complete = stream->read(&text[0], size) == size;
    delete stream;
    std::vector<unsigned char> pixels;
    if (!complete || !QuiverSVG::render(text, width, height, pixels)) {
        warning("SVG costume rejected: %s", path.c_str());
        return false;
    }
    Graphics::PixelFormat format(4, 8, 8, 8, 8, 0, 8, 16, 24);
    surf.create(width, height, format);
    for (int y = 0; y < height; ++y) {
        uint32 *row = (uint32 *)surf.getBasePtr(0, y);
        const unsigned char *src = pixels.data() + y * width * 4;
        for (int x = 0; x < width; ++x, src += 4)
            row[x] = format.ARGBToColor(src[3], src[0], src[1], src[2]);
    }
    warning("SVG costume rasterized: %s at %dx%d", path.c_str(), width, height);
    return true;
}
