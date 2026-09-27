"""Language packs (hd_language.h): string table, voices and the book's row."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_language.h', 'hd_language.inc', 'hd_voice_line.inc', 'hd_voice_select.inc'):
        (root / 'engines/scumm' / name).write_bytes((here / name).read_bytes())
    edit('engines/scumm/scumm.h', '\tvirtual void loadLanguageBundle();', '''\tvirtual void loadLanguageBundle();
\t// Language packs (hd_language.inc).
\tint _hdLanguage = 0, _hdLanguageOffered = -1;
\tuint32 _hdLanguageCheckedAt = 0;
\tbool _hdLanguageMouseDown = false;
\tCommon::String _hdVoiceBundles;
\tCommon::String hdLanguageDir(int language) const;
\tbool hdLanguageAvailable(int language) const;
\tbool hdLanguageOffered(int language);
\tvirtual void hdSetLanguage(int language) {}
\tvoid hdApplySavedLanguage();''')
    edit('engines/scumm/scumm.h', '\tCommon::Error saveGameState(int slot, const Common::String &desc, bool isAutosave = false) override;',
         '\tCommon::Error saveGameState(int slot, const Common::String &desc, bool isAutosave = false) override;\n'
         '\t// Language-pack voices for iMUSE (hd_language.inc).\n'
         '\tCommon::String hdVoiceBundles() const;\n\tCommon::SeekableReadStream *hdVoiceLine(const char *soundName) const;')
    edit('engines/scumm/scumm_v7.h', '\tvoid loadLanguageBundle() override;',
         '\tvoid loadLanguageBundle() override;\n\tbool hdLoadStringTable(int language);\n\tvoid hdSetLanguage(int language) override;')
    string = 'engines/scumm/string.cpp'
    edit(string, '#include "scumm/verbs.h"', '#include "scumm/verbs.h"\n#include "scumm/hd_language.h"\n#include "common/fs.h"\n#include "common/hashmap.h"')
    edit(string, '\treturn strcmp(i1->tag, i2->tag);\n}\n', '\treturn strcmp(i1->tag, i2->tag);\n}\n\n#include "scumm/hd_language.inc"\n')
    edit('engines/scumm/scumm.cpp', '\tloadLanguageBundle();\n', '\tloadLanguageBundle();\n\thdApplySavedLanguage();\n')
    edit('engines/scumm/gfx.cpp', '#include "scumm/hd_autosave.h"', '#include "scumm/hd_autosave.h"\n#include "scumm/hd_language.h"')
    # Voices: pack bundles under their own names (more directory-cache slots),
    # per-line recordings served as synthetic iMUS files, English fallback.
    digi = 'engines/scumm/imuse_digi/'
    edit(digi + 'dimuse_bndmgr.h', '\t} _bundleDirCache[4];', '\t} _bundleDirCache[8]; // English and language-pack bundles')
    edit(digi + 'dimuse_bndmgr.h', '#include "common/file.h"', '#include "common/file.h"\n#include "common/array.h"')
    edit(digi + 'dimuse_bndmgr.h', '\tbool isExtCompBun(byte gameId);\n};',
         '\tbool isExtCompBun(byte gameId);\n\tbool openVoiceLine(Common::SeekableReadStream *wav, const Common::Array<byte> &sync);\n'
         'private:\n\tCommon::Array<byte> _voiceLine; // hd_voice_line.inc\n};')
    bndmgr = digi + 'dimuse_bndmgr.cpp'
    edit(bndmgr, '\n\tif (!_file->isOpen()) {\n\t\terror("BundleMgr::readFile() File is not open");\n\t\treturn 0;\n\t}\n', '''
\tif (!_voiceLine.empty()) {
\t\tconst int32 count = MIN<int32>(size, MAX<int32>(0, (int32)_voiceLine.size() - _curDecompressedFilePos));
\t\t*comp_final = (byte *)malloc(MAX<int32>(count, 1));
\t\tmemcpy(*comp_final, _voiceLine.data() + _curDecompressedFilePos, count);
\t\t_curDecompressedFilePos += count;
\t\treturn count;
\t}
\tif (!_file->isOpen()) {
\t\terror("BundleMgr::readFile() File is not open");
\t\treturn 0;
\t}
''')
    edit(bndmgr, '\tint result = 0;\n\n\t// Issue #19: external WAV track', '''\tint result = 0;

\tif (!_voiceLine.empty()) {
\t\tresult = CLIP<int32>(mode == SEEK_END ? (int32)_voiceLine.size() + offset : offset, 0, _voiceLine.size());
\t\t_curDecompressedFilePos = result;
\t\treturn result;
\t}

\t// Issue #19: external WAV track''')
    text = (root / bndmgr).read_text()
    if '#include "scumm/hd_voice_line.inc"' not in text:
        index = text.rindex('} // End of namespace Scumm')
        (root / bndmgr).write_text(text[:index] + '#include "scumm/hd_voice_line.inc"\n\n' + text[index:])
    edit(digi + 'dimuse_sndmgr.h', '\tbool openVoiceBundle(SoundDesc *sound, int &disk);', '''\tbool openVoiceBundle(SoundDesc *sound, int &disk, const Common::String &prefix = Common::String());
\tbool openHDVoice(SoundDesc *sound, const char *soundName, int &disk, bool headerOutside);
\tvoid readVoiceSync(const char *soundName, int disk, bool headerOutside, Common::Array<byte> &sync);''')
    sndmgr = digi + 'dimuse_sndmgr.cpp'
    edit(sndmgr, 'bool ImuseDigiSndMgr::openVoiceBundle(SoundDesc *sound, int &disk) {',
         'bool ImuseDigiSndMgr::openVoiceBundle(SoundDesc *sound, int &disk, const Common::String &prefix) {')
    edit(sndmgr, '\t\t\tchar voxfile[20];\n\t\t\tif (disk == -1)\n\t\t\t\tdisk = _vm->VAR(_vm->VAR_CURRENTDISK);\n\t\t\tCommon::sprintf_s(voxfile, "voxdisk%d.bun", disk);',
         '\t\t\tif (disk == -1)\n\t\t\t\tdisk = _vm->VAR(_vm->VAR_CURRENTDISK);\n\t\t\tconst Common::String voxfile = prefix + Common::String::format("voxdisk%d.bun", disk);')
    edit(sndmgr, '\t\t\tresult = sound->bundle->open(voxfile, compressed);', '\t\t\tresult = sound->bundle->open(voxfile.c_str(), compressed);')
    edit(sndmgr, '\t\t\tresult = openVoiceBundle(sound, disk);', '\t\t\tresult = openHDVoice(sound, soundName, disk, header_outside);')
    edit(sndmgr, 'ImuseDigiSndMgr::SoundDesc *ImuseDigiSndMgr::openSound(',
         '#include "scumm/hd_voice_select.inc"\n\nImuseDigiSndMgr::SoundDesc *ImuseDigiSndMgr::openSound(')
