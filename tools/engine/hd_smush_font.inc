// Included in SmushFont. Capture high-resolution glyphs during the native
// text layout pass; the player composites them after decoding the HD frame.
public:
	bool beginHD(int slot, Common::Array<HdMovieGlyph> &glyphs) {
		if (_vm->_game.id != GID_CMI || _vm->_useCJKMode || _direction < 0 ||
			!_vm->_hdFontManager || !_vm->_hdFontManager->hasFont(slot)) return false;
		_hdSlot = slot;
		_hdPreviousSize = _vm->_hdFontManager->getSizePercent();
		_vm->_hdFontManager->setSizePercent(HdMovieText::sizePercent(_hdPreviousSize));
		_hdGlyphs = &glyphs;
		return true;
	}
	void endHD() {
		if (_hdGlyphs) _vm->_hdFontManager->setSizePercent(_hdPreviousSize);
		_hdGlyphs = nullptr; _hdFraction = 0;
	}
	bool usesFractionalWidths() const override { return _hdGlyphs != nullptr; }
	int getCharWidth100(uint16 chr) const override {
		return NutRenderer::getCharWidth(chr & 0xff) *
			(_hdGlyphs ? _vm->_hdFontManager->getSizePercent() : 100);
	}
	void setHDXFraction(int fraction) override { _hdFraction = fraction; }

private:
	int _hdSlot = -1, _hdFraction = 0;
	int _hdPreviousSize = 65;
	Common::Array<HdMovieGlyph> *_hdGlyphs = nullptr;
	int hdMetric(int value) const {
		return _hdGlyphs ? _vm->_hdFontManager->scaleMetric(value) : value;
	}
	byte hdColor(byte chr, int col) const {
		// Mirror NutRenderer's SMUSH palette mapping. Black outline pixels must
		// not supply the fill tint; the sharp sheet supplies outline and shadow.
		const auto &glyph = _chars[chr];
		for (int i = 0; i < glyph.width * glyph.height; ++i) {
			byte value = glyph.src[i];
			if (value == glyph.transparency) continue;
			byte mapped = HdVideoSupport::textColor(value, col);
			if (mapped != 0) return mapped;
		}
		return 0;
	}
