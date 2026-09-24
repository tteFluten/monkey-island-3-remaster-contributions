"""Keep Topaz and Quiver packs selectable without changing either pack's files."""
def patch(root, edit):
    # Keep the Quiver initializer intact so its own patch remains idempotent.
    initializer = '\t_hdQuiverManager->init(hdPath + "/quiver-cannon", true);'
    if 'if (ConfMan.hasKey("playtest_character_pack"))' not in (root / 'engines/scumm/scumm.cpp').read_text():
        edit('engines/scumm/scumm.cpp', initializer, initializer + '''
	if (ConfMan.hasKey("playtest_character_pack")) {
		Common::String pack = ConfMan.get("playtest_character_pack");
		if (pack != "quiver") {
			delete _hdQuiverManager;
			_hdQuiverManager = new HdCostumeManager(this);
			if (pack == "topaz")
				_hdQuiverManager->init(hdPath + "/topaz-cannon", true);
		}
		warning("Playtest character pack: %s", pack.c_str());
	}''')
    original = '\t\t\tif (pack == "topaz")\n\t\t\t\t_hdQuiverManager->init(hdPath + "/topaz-cannon", true);'
    edit('engines/scumm/scumm.cpp', original, original + '\n\t\t\telse if (pack == "topaz-crisp")\n\t\t\t\t_hdQuiverManager->init(hdPath + "/topaz-crisp", true);')
    edit('engines/scumm/hd_costume_manager.cpp', '\t_hdPath = hdPath;', '''
	if (!exactFrames && ConfMan.hasKey("playtest_character_pack") &&
		ConfMan.get("playtest_character_pack") == "original") {
		_enabled = false;
		return false;
	}
	_hdPath = hdPath;''')
