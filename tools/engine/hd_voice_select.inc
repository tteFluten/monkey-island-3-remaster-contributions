// Language packs (hd_language.h), voice selection: the pack's own recording of
// the line, then the pack's voice bundles, then the English bundles, so a pack
// may cover only some lines. Pack bundles are opened as "<code>/voxdiskN.bun"
// through the language search path, so they have their own directory cache.
bool ImuseDigiSndMgr::openHDVoice(SoundDesc *sound, const char *soundName, int &disk, bool headerOutside) {
    if (_vm->_game.id != GID_CMI || (_vm->_game.features & GF_DEMO) || !soundName[0])
        return openVoiceBundle(sound, disk);
    Common::SeekableReadStream *line = _vm->hdVoiceLine(soundName);
    if (line) {
        Common::Array<byte> sync;
        readVoiceSync(soundName, disk, headerOutside, sync);
        sound->bundle = new BundleMgr(_vm, _cacheBundleDir);
        if (sound->bundle->openVoiceLine(line, sync)) {
            warning("HD voice: %s from the language pack's voices", soundName);
            return true;
        }
        delete sound->bundle;
        sound->bundle = nullptr;
    }
    const Common::String prefix = _vm->hdVoiceBundles();
    if (!prefix.empty()) {
        int languageDisk = disk;
        if (openVoiceBundle(sound, languageDisk, prefix)) {
            byte *probe = nullptr;
            const bool found = sound->bundle->readFile(soundName, 0x2000, &probe, headerOutside) > 0 && probe;
            free(probe);
            if (found) {
                sound->bundle->seekFile(0, SEEK_SET);
                disk = languageDisk;
                return true;
            }
        }
        delete sound->bundle;
        sound->bundle = nullptr;
    }
    return openVoiceBundle(sound, disk);
}

// The English line's SYNC blocks (lip sync), reused for the pack's recording.
void ImuseDigiSndMgr::readVoiceSync(const char *soundName, int disk, bool headerOutside, Common::Array<byte> &sync) {
    const int disks[] = {disk == -1 ? (int)_vm->VAR(_vm->VAR_CURRENTDISK) : disk, 1, 2};
    for (int i = 0; i < 3; ++i) {
        BundleMgr bundle(_vm, _cacheBundleDir);
        bool compressed = false;
        if (!bundle.open(Common::String::format("voxdisk%d.bun", disks[i]).c_str(), compressed)) continue;
        byte *head = nullptr;
        const int32 size = bundle.readFile(soundName, 0x2000, &head, headerOutside);
        if (size > 16 && head && READ_BE_UINT32(head) == MKTAG('i', 'M', 'U', 'S') && READ_BE_UINT32(head + 8) == MKTAG('M', 'A', 'P', ' ')) {
            const byte *end = head + MIN<int32>(size, 16 + READ_BE_UINT32(head + 12));
            for (const byte *block = head + 16; block + 8 <= end;) {
                const uint32 length = READ_BE_UINT32(block + 4) + 8;
                if (block + length > end) break;
                if (READ_BE_UINT32(block) == MKTAG('S', 'Y', 'N', 'C'))
                    for (uint32 b = 0; b < length; ++b) sync.push_back(block[b]);
                block += length;
            }
            free(head);
            return;
        }
        free(head);
    }
}
