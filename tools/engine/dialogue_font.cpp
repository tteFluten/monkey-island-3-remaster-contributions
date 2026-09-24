#include "scumm/dialogue_font.h"
#include "common/fs.h"
#include "common/stream.h"
#include "common/textconsole.h"
#include "image/png.h"
namespace Scumm {
DialogueFont::~DialogueFont() {
	for (int i = 0; i < 10; ++i) _slots[i].surface.free();
}
void DialogueFont::init(const Common::String &path) {
	for (int i = 0; i < 10; ++i) {
		Slot &slot = _slots[i];
		slot.loaded = false;
		slot.surface.free();
		Common::String base = path + Common::String::format("/dialogue-font/%dx/FONT%d", i < 5 ? 4 : 6, i % 5);
		Common::FSNode metrics(Common::Path(base + ".dat"));
		Common::SeekableReadStream *stream = metrics.createReadStream();
		if (!stream) continue;
		bool valid = stream->size() == 1548 && stream->readUint32BE() == MKTAG('D','L','G','1');
		int scale = stream->readUint16LE();
		slot.height = stream->readUint16LE();
		slot.cellW = stream->readUint16LE();
		slot.cellH = stream->readUint16LE();
		valid = valid && scale == (i < 5 ? 4 : 6) && slot.height >= 4 && slot.height <= 64 &&
			slot.cellW > 0 && slot.cellW <= 384 && slot.cellH == slot.height * scale;
		for (int c = 0; c < 256; ++c) {
			slot.supported[c] = stream->readUint16LE();
			slot.advance[c] = stream->readUint16LE();
			slot.bearing[c] = stream->readSint16LE();
			valid = valid && slot.supported[c] <= 1 && (!slot.supported[c] ||
				(slot.advance[c] > 0 && slot.advance[c] <= 128 && ABS(slot.bearing[c]) <= 256));
		}
		valid = valid && !stream->err();
		delete stream;
		if (!valid) { warning("Invalid dialogue font metrics: %s", base.c_str()); continue; }
		Common::FSNode image(Common::Path(base + ".png"));
		stream = image.createReadStream();
		if (!stream) continue;
		Image::PNGDecoder png;
		valid = png.loadStream(*stream);
		delete stream;
		const Graphics::Surface *surface = valid ? png.getSurface() : nullptr;
		if (!surface || surface->format.bytesPerPixel != 4 || !surface->format.aBits() ||
			surface->w != slot.cellW * 16 || surface->h != slot.cellH * 16) continue;
		slot.surface.copyFrom(*surface);
		slot.loaded = true;
		debug(1, "CaslonAntique dialogue font %d ready (%d pixel line)", i, slot.height);
	}
}
bool DialogueFont::available() const {
	for (int i = 0; i < 10; ++i) if (_slots[i].loaded) return true;
	return false;
}
bool DialogueFont::has(int slot, int chr) const {
	return slot >= 0 && slot < 5 && chr >= 0 && chr < 256 && (scale == 4 || scale == 6) && _slots[index(slot, scale)].loaded && _slots[index(slot, scale)].supported[chr];
}
void DialogueFont::draw(int slot, int chr, int renderScale, Graphics::Surface &dest, int x, int y, const Common::Rect &clip, byte r, byte g, byte b) const {
	if (slot < 0 || slot >= 5 || chr < 0 || chr >= 256 || (renderScale != 4 && renderScale != 6) || dest.format.bytesPerPixel != 4) return;
	const Slot &s = _slots[index(slot, renderScale)];
	if (!s.loaded || !s.supported[chr]) return;
	x += s.bearing[chr];
	int srcX = (chr % 16) * s.cellW, srcY = (chr / 16) * s.cellH;
	for (int sy = MAX(0, MAX<int>(clip.top, 0) - y); sy < s.cellH && y + sy < MIN<int>(clip.bottom, dest.h); ++sy) {
		for (int sx = MAX(0, MAX<int>(clip.left, 0) - x); sx < s.cellW && x + sx < MIN<int>(clip.right, dest.w); ++sx) {
			byte a, fr, fg, fb;
			s.surface.format.colorToARGB(*(const uint32 *)s.surface.getBasePtr(srcX + sx, srcY + sy), a, fr, fg, fb);
			if (!a) continue;
			uint32 *out = (uint32 *)dest.getBasePtr(x + sx, y + sy);
			byte da, dr, dg, db;
			dest.format.colorToARGB(*out, da, dr, dg, db);
			// White coverage takes the speaker color; black outline stays black.
			// Preserve both the antialiased fill/outline boundary and outer alpha.
			*out = dest.format.ARGBToColor(255,
				((fr * r / 255) * a + dr * (255 - a) + 127) / 255,
				((fg * g / 255) * a + dg * (255 - a) + 127) / 255,
				((fb * b / 255) * a + db * (255 - a) + 127) / 255);
		}
	}
}
}
