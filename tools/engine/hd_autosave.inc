// Autosave at every chapter change (hd_autosave.h): once the chapter card has
// given way to a playable room that has been on screen for two seconds, so the
// save and its HD thumbnail show the new chapter. ScummVM's periodic autosave
// restarts its 5-minute timer from it.
void ScummEngine_v8::hdChapterAutosave() {
    if (!ConfMan.hasKey("playtest_session")) return;
    if (HdAutosave::chapterCard(_currentRoom)) {
        _hdChapterPending = true;
        _hdChapterRoom = -1;
        return;
    }
    if (!_hdChapterPending || _saveLoadFlag || _currentRoom <= 3 || _currentRoom == 92 || isSmushActive()) return;
    if (_hdChapterRoom != _currentRoom) {
        _hdChapterRoom = _currentRoom;
        _hdChapterSince = _system->getMillis();
        return;
    }
    if (_system->getMillis() - _hdChapterSince < 2000 || HdRemaster::state().room != _currentRoom ||
        !canSaveAutosaveCurrently())
        return;
    _hdChapterPending = false;
    saveAutosaveIfEnabled();
}
