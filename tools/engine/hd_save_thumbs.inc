// HD save thumbnails. COMI keeps a 160x120 thumbnail sampled from the native
// screen inside each save, and the book stamps it into the slot frames. The
// remaster also writes a 640x480 PNG of the presented HD scene (centre 4:3)
// next to each save, named after a checksum of that internal thumbnail, so a
// replaced or foreign save never shows a stale picture. Saves without one get a
// smooth upscale of their internal thumbnail (see hd_book.inc).

static Common::String hdThumbnailName(const Common::String &save, uint32 key) {
    return save + Common::String::format(".hd.%08x.png", key);
}

void ScummEngine::removeHDSaveThumbnails(const Common::String &save, const Common::String &keep) {
    const Common::StringArray found = _saveFileMan->listSavefiles(save + ".hd.*.png");
    for (uint i = 0; i < found.size(); ++i)
        if (found[i] != keep) _saveFileMan->removeSavefile(found[i]);
}

// A book save copies the temporary save made when the book opened, so its
// internal thumbnail, and therefore its key, is the same.
void ScummEngine::copyHDSaveThumbnail(int slot) {
    if (!ConfMan.hasKey("playtest_session")) return;
    const Common::String heap = makeSavegameName(1, true), save = makeSavegameName(slot, false);
    const Common::StringArray found = _saveFileMan->listSavefiles(heap + ".hd.*.png");
    if (found.size() != 1) { removeHDSaveThumbnails(save, ""); return; }
    const Common::String name = save + Common::String(found[0].c_str() + heap.size());
    Common::InSaveFile *in = _saveFileMan->openForLoading(found[0]);
    Common::OutSaveFile *out = in ? _saveFileMan->openForSaving(name, false) : nullptr;
    bool copied = in && out;
    byte buffer[16384];
    while (copied && !in->eos()) {
        const uint32 count = in->read(buffer, sizeof(buffer));
        copied = !in->err() && out->write(buffer, count) == count;
    }
    if (out) { out->finalize(); copied = copied && !out->err(); }
    delete in; delete out;
    if (!copied) _saveFileMan->removeSavefile(name);
    removeHDSaveThumbnails(save, copied ? name : "");
}

uint32 ScummEngine_v8::hdThumbnailKey() const {
    uint32 hash = 2166136261u;
    for (uint i = 0; i < sizeof(_savegameThumbnailV8); ++i)
        hash = (hash ^ _savegameThumbnailV8[i]) * 16777619u;
    for (int i = 0; i < 256; ++i)
        hash = (hash ^ (uint32)_savegameThumbnailV8Palette[i]) * 16777619u;
    return hash;
}

// The presented HD scene, centre 4:3, box-filtered to 640x480 RGBA.
bool ScummEngine_v8::captureHDSaveThumbnail(Graphics::Surface &out) {
    auto &remaster = HdRemaster::state();
    if (_hdScale <= 1 || _currentRoom == 92 || remaster.room != _currentRoom || isSmushActive()) return false;
    Graphics::Surface frame;
    const byte *pixels;
    int width, height, pitch;
    // Both sources are top row first: the GPU canvas is read back from its
    // framebuffer, the CPU composite is the presented frame itself.
    if (remaster.active && remaster.capture && remaster.capture(frame)) {
        pixels = (const byte *)frame.getPixels(); width = frame.w; height = frame.h; pitch = frame.pitch;
    } else if (!remaster.active && _hdComposite.getPixels() && _hdComposite.format.bytesPerPixel == 4) {
        pixels = (const byte *)_hdComposite.getPixels(); width = _hdComposite.w; height = _hdComposite.h;
        pitch = _hdComposite.pitch;
    } else {
        return false;
    }
    const int cropWidth = MIN(width, height * 4 / 3), left = (width - cropWidth) / 2;
    out.create(640, 480, Graphics::PixelFormat(4, 8, 8, 8, 8, 0, 8, 16, 24));
    for (int oy = 0; oy < 480; ++oy) {
        const int y0 = oy * height / 480, y1 = MAX(y0 + 1, (oy + 1) * height / 480);
        uint32 *dst = (uint32 *)out.getBasePtr(0, oy);
        for (int ox = 0; ox < 640; ++ox) {
            const int x0 = left + ox * cropWidth / 640, x1 = MAX(x0 + 1, left + (ox + 1) * cropWidth / 640);
            uint32 r = 0, g = 0, b = 0, n = 0;
            for (int y = y0; y < y1; ++y) {
                const byte *row = pixels + y * pitch;
                for (int x = x0; x < x1; ++x, ++n) {
                    r += row[x * 4]; g += row[x * 4 + 1]; b += row[x * 4 + 2];
                }
            }
            dst[ox] = (r / n) | (g / n) << 8 | (b / n) << 16 | 0xff000000u;
        }
    }
    frame.free();
    return true;
}

// Called right after createInternalSaveStateThumbnail(), before the save.
void ScummEngine_v8::writeHDSaveThumbnail(int slot, bool temporary) {
    if (!ConfMan.hasKey("playtest_session")) return;
    const Common::String save = makeSavegameName(slot, temporary);
    Graphics::Surface image;
    if (!captureHDSaveThumbnail(image)) {
        removeHDSaveThumbnails(save, "");
        return;
    }
    const Common::String name = hdThumbnailName(save, hdThumbnailKey());
    Common::OutSaveFile *file = _saveFileMan->openForSaving(name, false);
    bool written = file && Image::writePNG(*file, image);
    if (file) { file->finalize(); written = written && !file->err(); delete file; }
    image.free();
    if (!written) {
        _saveFileMan->removeSavefile(name);
        warning("HD save thumbnail could not be written: %s", name.c_str());
    }
    removeHDSaveThumbnails(save, written ? name : "");
}

// Called by stampScreenShot() after the native thumbnail is drawn.
void ScummEngine_v8::recordHDStamp(int slot, bool heap, int boxX, int boxY, int boxWidth, int boxHeight, int brightness, bool internal) {
    const Common::Rect box(boxX, boxY, boxX + boxWidth, boxY + boxHeight);
    if (!internal || _hdScale <= 1 || !ConfMan.hasKey("playtest_session")) {
        addHDBookStamp(box, brightness, nullptr);
        return;
    }
    const Common::String name = hdThumbnailName(makeSavegameName(heap ? 1 : slot, heap), hdThumbnailKey());
    HdBookImage image;
    if (!hdBookImage(name, image)) {
        image.w = 160; image.h = 120;
        image.pixels.resize(160 * 120);
        for (int i = 0; i < 160 * 120; ++i)
            image.pixels[i] = (uint32)_savegameThumbnailV8Palette[_savegameThumbnailV8[i]] | 0xff000000u;
    }
    addHDBookStamp(box, brightness, &image);
}
