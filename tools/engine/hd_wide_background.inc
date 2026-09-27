// Decorative extended artwork behind the unchanged 4:3 gameplay surface.
// Included in namespace OpenGL; no room coordinates or input areas change.
void OpenGLGraphicsManager::updateHDWideBackground() {
    Common::String path;
    if (ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169 &&
        ConfMan.hasKey("hd_wide_background"))
        path = ConfMan.get("hd_wide_background");
    Common::String key = path.empty() ? path : path + Common::String::format(":%d",
        ConfMan.getInt("hd_wide_background_revision"));
    const Common::String sourceKey = key;
    auto &remaster = HdRemaster::state();
    if (remaster.wideRoom != 13 || path.empty()) {
        remaster.plunderMap = remaster.plunderMapInput = false;
    }
    if (!key.empty() && !remaster.active) key += Common::String::format(":dof:%d:%d:%d:%u", remaster.dof, remaster.radius, remaster.intensity, remaster.coverageGeneration);
    if (!key.empty()) key += HdRemaster::state().active ? ":gpu" : ":cpu";
    HdColorGrade::Grade grade;
    if (!path.empty()) for (int c = 0; c < HdColorGrade::kControls; ++c) {
        const Common::String setting = Common::String("hd_wide_look_") + HdColorGrade::range(c).key;
        if (ConfMan.hasKey(setting)) grade.value[c] = HdColorGrade::clampControl(c, ConfMan.getInt(setting));
        if (!HdRemaster::state().active) key += Common::String::format(":%d", grade.value[c]);
    }
    if (key == _hdWideBackgroundKey) return;
    _hdWideBackgroundKey = key;
    delete _hdWideBackground;
    _hdWideBackground = nullptr;
    remaster.plunderMap = remaster.plunderMapInput = false;
    ConfMan.setBool("hd_wide_background_active", false, Common::ConfigManager::kTransientDomain);
    _forceRedraw = true;
    if (path.empty()) return;
#ifdef USE_PNG
    static Graphics::Surface raw;
    static Common::String rawKey;
    if (rawKey != sourceKey || !raw.getPixels()) {
        Graphics::Surface decoded;
        if (!HdBackground::cache().load(path, decoded)) return;
        if (decoded.w != 2560 || decoded.h != 1440) {
            decoded.free();
            warning("HD widescreen: invalid background %s", path.c_str()); return;
        }
        raw.free(); raw = decoded; rawKey = sourceKey;
    }
    Graphics::Surface *pixels = new Graphics::Surface();
    pixels->copyFrom(raw);
    if (!remaster.active && remaster.dof && remaster.wideCoverage.size() == size_t(remaster.viewportWidth * remaster.viewportHeight)) {
        static std::vector<uint32> blurred;
        static Common::String blurKey;
        static int bw = 0, bh = 0;
        const int radius = remaster.radius * 3 / remaster.scale;
        const Common::String nextBlur = sourceKey + Common::String::format(":%d", radius);
        if (blurKey != nextBlur) {
            HdDepthOfField::blur((const byte *)raw.getPixels(), raw.pitch, 4, raw.w, raw.h, 2, radius, blurred, bw, bh);
            blurKey = nextBlur;
        }
        for (int y = 0; y < pixels->h; ++y) {
            uint32 *row = (uint32 *)pixels->getBasePtr(0, y);
            for (int x = 0; x < pixels->w; ++x) {
                const int coverage = HdDepthOfField::coverageAt(remaster.wideCoverage.data(), remaster.viewportWidth,
                    remaster.viewportHeight, 3, x * 3 / 4, y) * remaster.intensity / 100;
                if (coverage) row[x] = HdDepthOfField::mix(row[x], HdDepthOfField::sample(blurred.data(), bw, bh, 2, x, y), coverage);
            }
        }
    }
    const bool color = !HdColorGrade::colorIdentity(grade), vignette = HdColorGrade::vignetteActive(grade);
    if ((color || vignette) && !HdRemaster::state().active) {
        HdColorGrade::Lut lut;
        if (color) HdColorGrade::build(grade, lut);
        for (int y = 0; y < pixels->h; ++y) {
            uint32 *row = (uint32 *)pixels->getBasePtr(0, y);
            for (int x = 0; x < pixels->w; ++x) {
                if (color) row[x] = HdColorGrade::apply(row[x], lut);
                if (vignette) row[x] = HdColorGrade::vignettePixel(row[x],
                    HdColorGrade::vignetteGain(grade, x, y, pixels->w, pixels->h));
            }
        }
    }
    _hdWideBackground = createSurface(pixels->format);
    if (_hdWideBackground) {
        _hdWideBackground->allocate(pixels->w, pixels->h);
        _hdWideBackground->enableLinearFiltering(true);
        _hdWideBackground->copyRectToTexture(0, 0, pixels->w, pixels->h,
            pixels->getPixels(), pixels->pitch);
        _hdWideBackground->updateGLTexture();
        ConfMan.setBool("hd_wide_background_active", true, Common::ConfigManager::kTransientDomain);
        if (remaster.wideRoom == 13) {
            Common::File stamp;
            const Common::Path stampPath(ConfMan.get("hd_path") + "/backgrounds/bg_0013.png.stamp");
            if (stamp.open(Common::FSNode(stampPath))) {
                const Common::String source = stamp.readLine();
                remaster.plunderMap = source.hasPrefix(Common::String(HdPlunderMap::kSource) + ":");
            }
            if (remaster.plunderMap) {
                // One depth field for the whole painting avoids clamped water
                // at the two boundaries of the central gameplay texture.
                const int w = 854, h = 480;
                auto &coverage = remaster.plunderWaterCoverage;
                coverage.free(); coverage.create(w, h, Graphics::PixelFormat::createFormatCLUT8());
                Common::Array<byte> water; water.resize(w * h);
                Common::Array<uint16> edge; edge.resize(w * h);
                for (int y = 0; y < h; ++y) for (int x = 0; x < w; ++x) {
                    byte r, g, b;
                    raw.format.colorToRGB(raw.getPixel(x * raw.w / w, y * raw.h / h), r, g, b);
                    water[y * w + x] = HdPlunderMap::water((x + 0.5) * 1000 / w,
                        (y + 0.5) * 1000 / h, r, g, b) ? 2 : 0;
                }
                HdWater::surfaceDepth(water.data(), w, h, edge.data(), (byte *)coverage.getPixels(), 1);
            }
        }
        warning("HD widescreen: loaded %s", path.c_str());
    }
    pixels->free();
    delete pixels;
#endif
}

void OpenGLGraphicsManager::drawHDWideBackground() {
    if (!_hdWideBackground || _overlayVisible || !_gameScreen ||
        _gameScreen->getWidth() * 3 != _gameScreen->getHeight() * 4) return;
    // Derive placement from the same center rectangle used by pointer mapping.
    // Its exact 4:3 center overlays the full image's center at every window size.
    const float height = _gameDrawRect.height();
    const float width = height * 16.0f / 9.0f;
    const float left = _gameDrawRect.left + (_gameDrawRect.width() - width) / 2;
    _targetBuffer->enableScissorTest(false);
    _hdWideBackground->updateGLTexture();
    _pipeline->drawTexture(_hdWideBackground->getGLTexture(), left,
        _gameDrawRect.top, width, height);
    _targetBuffer->enableScissorTest(true);
}
