// Decorative extended artwork behind the unchanged 4:3 gameplay surface.
// Included in namespace OpenGL; no room coordinates or input areas change.
void OpenGLGraphicsManager::updateHDWideBackground() {
    Common::String path;
    if (ConfMan.hasKey("playtest_session") && ConfMan.getInt("hd_aspect_ratio") == 169 &&
        ConfMan.hasKey("hd_wide_background"))
        path = ConfMan.get("hd_wide_background");
    Common::String key = path.empty() ? path : path + Common::String::format(":%d",
        ConfMan.getInt("hd_wide_background_revision"));
    HdColorGrade::Grade grade;
    if (!path.empty()) for (int c = 0; c < HdColorGrade::kControls; ++c) {
        const Common::String setting = Common::String("hd_wide_look_") + HdColorGrade::range(c).key;
        if (ConfMan.hasKey(setting)) grade.value[c] = HdColorGrade::clampControl(c, ConfMan.getInt(setting));
        key += Common::String::format(":%d", grade.value[c]);
    }
    if (key == _hdWideBackgroundKey) return;
    _hdWideBackgroundKey = key;
    delete _hdWideBackground;
    _hdWideBackground = nullptr;
    ConfMan.setBool("hd_wide_background_active", false, Common::ConfigManager::kTransientDomain);
    _forceRedraw = true;
    if (path.empty()) return;
#ifdef USE_PNG
    Common::FSNode node((Common::Path(path)));
    Common::SeekableReadStream *file = node.createReadStream();
    if (!file) return; // Ordinary artwork retains the existing side bars.
    Image::PNGDecoder decoder;
    const bool loaded = decoder.loadStream(*file);
    delete file;
    const Graphics::Surface *source = decoder.getSurface();
    if (!loaded || !source || source->w != 2560 || source->h != 1440) {
        warning("HD widescreen: invalid background %s", path.c_str());
        return;
    }
    Graphics::Surface *pixels = source->convertTo(Graphics::PixelFormat::createFormatRGBA32(),
        decoder.getPalette().data(), decoder.getPalette().size());
    if (!pixels) return;
    const bool color = !HdColorGrade::colorIdentity(grade), vignette = HdColorGrade::vignetteActive(grade);
    if (color || vignette) {
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
