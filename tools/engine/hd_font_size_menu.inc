// The original COMI book menu is scripted (room 92), not a ScummVM dialog.
// Its options spread gains a Text Size slider (see hd_book.inc).
bool ScummEngine::hasHDFontSizeMenu() const {
	return _game.id == GID_CMI && _currentRoom == 92 && _hdScale > 1 && hdBookOptionsPage() &&
		_hdBackgroundSurface.getPixels() && _hdFontManager && _hdFontManager->hasFont(3);
}

void ScummEngine::setHDFontSizeFromBook(int x) {
	const int percent = HdBookLayout::sizeAt(x);
	if (percent == _hdFontManager->getSizePercent()) return;
	_hdFontManager->setSizePercent(percent);
	ConfMan.setInt("hd_font_size", percent);
	_hdFontChars.clear();
	_fullRedraw = true;
	redrawVerbs();
}

bool ScummEngine::handleHDFontSizeEvent(const Common::Event &event) {
	if (_hdLanguageMouseDown && event.type == Common::EVENT_LBUTTONUP) {
		_hdLanguageMouseDown = false;
		_leftBtnPressed = 0;
		return true;
	}
	if (_hdFontSizeMouseDown) {
		const bool release = event.type == Common::EVENT_LBUTTONUP;
		if (!release && event.type != Common::EVENT_MOUSEMOVE) return false;
		if (hasHDFontSizeMenu()) setHDFontSizeFromBook(event.mouse.x / _hdScale);
		if (!release && hasHDFontSizeMenu()) return false; // Moves still update the pointer.
		_hdFontSizeMouseDown = false;
		ConfMan.flushToDisk();
		if (release) _leftBtnPressed = 0;
		return release;
	}
	if (!hasHDFontSizeMenu() || event.type != Common::EVENT_LBUTTONDOWN)
		return false;
	const int x = event.mouse.x / _hdScale, y = event.mouse.y / _hdScale;
	const int language = HdBookLayout::languageAt(x, y);
	if (language >= 0) {
		_hdLanguageMouseDown = true;
		_leftBtnPressed = 0;
		if (language != _hdLanguage && hdLanguageOffered(language)) hdSetLanguage(language);
		return true;
	}
	if (!HdBookLayout::kSizeHit.contains(x, y)) return false;
	_hdFontSizeMouseDown = true;
	_leftBtnPressed = 0;
	setHDFontSizeFromBook(x);
	return true;
}

void ScummEngine::drawHDFontSizeMenu() {
	// Drawn as book items: ScummEngine_v7::enqueueHDBookControls().
}
