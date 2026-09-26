"""Keep Topaz and Quiver packs selectable without changing either pack's files."""
def patch(root, edit):
    # These rejected Topaz stand-up frames have transparent lower legs/feet
    # (alpha stops ~235 HD pixels above the image bottom). Leave them out of
    # the available-frame index so the exact-pose path keeps the complete
    # original actor instead; eager and asynchronous prefetch skip them too.
    # Retain the archived PNGs and do not block other packs' replacement art.
    edit('engines/scumm/hd_costume_manager.cpp', '\t\t\tkey.frame = frame;', '''\t\t\tkey.frame = frame;
            if (_exactFrames && lflfOwner == 1 && akosNumber == 3 &&
                (frame == 15 || frame == 16) && name.hasSuffixIgnoreCase(".png") &&
                (hdPath.hasSuffix("/topaz-cannon") || hdPath.hasSuffix("/topaz-crisp")))
                continue; // Rejected cutoff poses: use the native full-body frame.''')
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
