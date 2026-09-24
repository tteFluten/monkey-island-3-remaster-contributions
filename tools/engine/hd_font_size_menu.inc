// The original COMI book menu is scripted (room 92), not a ScummVM dialog.
// Add one row beneath its existing options in original 640x480 coordinates.
bool ScummEngine::hasHDFontSizeMenu() const {
	return _game.id == GID_CMI && _currentRoom == 92 && _hdScale > 1 &&
		_hdBackgroundSurface.getPixels() && _hdFontManager && _hdFontManager->hasFont(3);
}

bool ScummEngine::handleHDFontSizeEvent(const Common::Event &event) {
	if (event.type == Common::EVENT_LBUTTONUP && _hdFontSizeMouseDown) {
		_hdFontSizeMouseDown = false;
		_leftBtnPressed = 0;
		return true;
	}
	if (!hasHDFontSizeMenu() || event.type != Common::EVENT_LBUTTONDOWN)
		return false;
	const int x = event.mouse.x / _hdScale, y = event.mouse.y / _hdScale;
	int delta = 0;
	if (Common::Rect(155, 424, 180, 451).contains(x, y)) delta = -5;
	if (Common::Rect(224, 424, 249, 451).contains(x, y)) delta = 5;
	if (!delta) return false;
	_hdFontSizeMouseDown = true;
	_leftBtnPressed = 0;
	const int percent = CLIP(_hdFontManager->getSizePercent() + delta, 25, 100);
	_hdFontManager->setSizePercent(percent);
	ConfMan.setInt("hd_font_size", percent);
	ConfMan.flushToDisk();
	_hdFontChars.clear();
	_fullRedraw = true;
	redrawVerbs();
	return true;
}

void ScummEngine::drawHDFontSizeMenu() {
	if (!hasHDFontSizeMenu()) return;
	const int size = _hdFontManager->getSizePercent();
	const int oldFont = _charset->getCurID();
	// Keep this control legible at every setting; game text uses the chosen size.
	_hdFontManager->setSizePercent(65);
	_charset->setCurID(3);
	const int scale = _hdScale;
	const uint32 ink = _hdComposite.format.RGBToColor(25, 12, 3);
	const uint32 paper = _hdComposite.format.RGBToColor(221, 172, 87);
	for (int x : {155, 224}) {
		_hdComposite.fillRect(Common::Rect(x * scale, 424 * scale, (x + 25) * scale, 451 * scale), ink);
		_hdComposite.fillRect(Common::Rect((x + 1) * scale, 425 * scale, (x + 24) * scale, 450 * scale), paper);
	}
	Graphics::Surface textSurface;
	textSurface.create(512, 224, Graphics::PixelFormat::createFormatRGBA32());
	auto label = [&](const Common::String &text, int left, int right, bool centered, bool disabled) {
		textSurface.fillRect(Common::Rect(0, 0, textSurface.w, textSurface.h), 0);
		int x100 = 0;
		const CharsetRendererNut *font = dynamic_cast<const CharsetRendererNut *>(_charset);
		for (uint i = 0; i < text.size(); ++i) {
			const byte c = (byte)text[i];
			const byte color = disabled ? 110 : 20;
			_hdFontManager->drawChar(3, c, textSurface, x100 * scale / 100, 0, color, color, color);
			x100 += font ? font->getCharWidth100(c) : _charset->getCharWidth(c) * 100;
		}
		// Center visible ink, including the hard shadow, rather than NUT padding.
		int minX = textSurface.w, minY = textSurface.h, maxX = -1, maxY = -1;
		for (int y = 0; y < textSurface.h; ++y) {
			for (int x = 0; x < textSurface.w; ++x) {
				uint32 pixel = *(const uint32 *)textSurface.getBasePtr(x, y);
				if ((pixel >> textSurface.format.aShift) & 255) {
					minX = MIN(minX, x); maxX = MAX(maxX, x);
					minY = MIN(minY, y); maxY = MAX(maxY, y);
				}
			}
		}
		if (maxX < minX) return;
		const int width = maxX - minX + 1, height = maxY - minY + 1;
		const int targetX = left * scale + (centered ? ((right - left) * scale - width) / 2 : 0);
		const int targetY = 424 * scale + (27 * scale - height) / 2;
		for (int y = minY; y <= maxY; ++y) {
			for (int x = minX; x <= maxX; ++x) {
				byte a, r, g, b;
				textSurface.format.colorToARGB(*(const uint32 *)textSurface.getBasePtr(x, y), a, r, g, b);
				if (a)
					*(uint32 *)_hdComposite.getBasePtr(targetX + x - minX, targetY + y - minY) = _hdComposite.format.RGBToColor(r, g, b);
			}
		}
	};
	label("Text size", 48, 155, false, false);
	label("-", 155, 180, true, size == 25);
	label(Common::String::format("%d%%", size), 180, 224, true, false);
	label("+", 224, 249, true, size == 100);
	textSurface.free();
	_charset->setCurID(oldFont);
	_hdFontManager->setSizePercent(size);
}
