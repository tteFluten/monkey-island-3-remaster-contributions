// Local CaslonAntique dialogue atlas. Original NUT fonts remain the fallback.
#ifndef SCUMM_DIALOGUE_FONT_H
#define SCUMM_DIALOGUE_FONT_H
#include "common/rect.h"
#include "common/str.h"
#include "graphics/surface.h"
namespace Scumm {
class DialogueFont {
public:
	DialogueFont() : active(false), scale(4) {}
	~DialogueFont();
	void init(const Common::String &path);
	bool has(int slot, int chr) const;
	int width(int slot, int chr) const { return _slots[index(slot, scale)].advance[chr]; }
	int height(int slot) const { return slot >= 0 && slot < 5 && _slots[index(slot, scale)].loaded ? _slots[index(slot, scale)].height : 0; }
	void draw(int slot, int chr, int renderScale, Graphics::Surface &dest, int x, int y, const Common::Rect &clip, byte r, byte g, byte b) const;
	bool active;
	int scale;
	bool available() const;
private:
	struct Slot {
		Graphics::Surface surface;
		bool loaded = false;
		int height = 0, cellW = 0, cellH = 0;
		uint16 supported[256] = {}, advance[256] = {};
		int16 bearing[256] = {};
	};
	static int index(int slot, int scale) { return slot + (scale == 6 ? 5 : 0); }
	Slot _slots[10];
};
class DialogueFontScope {
	DialogueFont &_font;
	bool _previous;
	int _previousScale;
public:
	DialogueFontScope(DialogueFont &font, bool active, int scale) : _font(font), _previous(font.active), _previousScale(font.scale) {
		// Disabled legacy atlases must not intercept the regular HD font sheets
		// and force subtitles/response verbs down the original NUT fallback.
		font.active = active && font.available();
		font.scale = scale;
	}
	~DialogueFontScope() { _font.active = _previous; _font.scale = _previousScale; }
};
}
#endif
