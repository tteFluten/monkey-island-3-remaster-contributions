"""Language packs: string-table lines, remaster strings, autosave labels and
the pack tool (language_pack.py)."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).parent))
import language_pack  # noqa: E402


class LanguageTests(unittest.TestCase):
    def test_lines_strings_and_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'language.cpp'
            source.write_text(r"""
#include "hd_language.h"
#include <cassert>
#include <cstring>
using namespace HdLanguage;
int main() {
    assert(fromCode("en") == kEnglish && fromCode("es") == kSpanish && fromCode("fr") == kEnglish && fromCode("") == kEnglish);
    char tag[13];
    int start = -1;
    const char *line = "atlh302\t...God of the Volcano";
    assert(parseLine(line, (int)strlen(line), tag, start) && !strcmp(tag, "ATLH302") && !strcmp(line + start, "...God of the Volcano"));
    line = "SYST200 Are you sure?";
    assert(parseLine(line, (int)strlen(line), tag, start) && !strcmp(tag, "SYST200") && line[start] == 'A');
    line = "NOTEXTATALL";
    assert(!parseLine(line, (int)strlen(line), tag, start));
    line = "\ttext";
    assert(!parseLine(line, (int)strlen(line), tag, start));
    char escaped[] = "one\\ntwo\\n";
    unescape(escaped);
    assert(!strcmp(escaped, "one\ntwo\n"));
    assert(!strcmp(text(kEnglish, kTextSize), "Text Size") && !strcmp(text(kSpanish, kTextSize), "Tama\xF1o del texto"));
    assert(!strcmp(text(kSpanish, kSpanishName), "Espa\xF1ol") && !strcmp(text(99, kTextSize), "Text Size"));
    char s[64];
    autosaveLabel(kEnglish, -3, s, sizeof s); assert(!strcmp(s, "Autosave"));
    autosaveLabel(kEnglish, 0, s, sizeof s); assert(!strcmp(s, "Autosave (just now)"));
    autosaveLabel(kEnglish, 12, s, sizeof s); assert(!strcmp(s, "Autosave (12 min ago)"));
    autosaveLabel(kEnglish, 61, s, sizeof s); assert(!strcmp(s, "Autosave (1 hour ago)"));
    autosaveLabel(kEnglish, 185, s, sizeof s); assert(!strcmp(s, "Autosave (3 hours ago)"));
    autosaveLabel(kEnglish, 1500, s, sizeof s); assert(!strcmp(s, "Autosave (yesterday)"));
    autosaveLabel(kEnglish, 1440 * 9, s, sizeof s); assert(!strcmp(s, "Autosave (9 days ago)"));
    autosaveLabel(kSpanish, 0, s, sizeof s); assert(!strcmp(s, "Autoguardado (ahora mismo)"));
    autosaveLabel(kSpanish, 12, s, sizeof s); assert(!strcmp(s, "Autoguardado (hace 12 min)"));
    autosaveLabel(kSpanish, 185, s, sizeof s); assert(!strcmp(s, "Autoguardado (hace 3 horas)"));
    autosaveLabel(kSpanish, 1440 * 9, s, sizeof s); assert(!strcmp(s, "Autoguardado (hace 9 d\xED" "as)"));
    autosaveLabel(kEnglish, 12, s, 10); assert(!strcmp(s, "Autosave "));
}
""")
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', '-I',
                            str(Path(__file__).parent / 'engine'), str(source),
                            '-o', str(root / 'language')], check=True, capture_output=True)
            subprocess.run([str(root / 'language')], check=True, capture_output=True)

    def test_pack_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game, pack = root / 'game', root / 'pack'
            (pack / 'voices').mkdir(parents=True)
            game.mkdir()
            (game / 'LANGUAGE.TAB').write_bytes(b'SA__026\tSave Game\r\nCNWY034 Mangy dogs!\r\nbad\r\n')
            entry = b'CNWY034\0' + b'IMX\0' + struct.pack('>II', 0, 0)   # LB83 index: name, extension, offset, size
            (game / 'VOXDISK1.BUN').write_bytes(struct.pack('>4sII', b'LB83', 12, 1) + entry)
            self.assertEqual(language_pack.read_table(b'\xef\xbb\xbfSA__026\tGuardar\r\n', 'utf-8'), {'SA__026': 'Guardar'})
            self.assertEqual(language_pack.spoken(game), {'CNWY034': 1})
            english = language_pack.english_lines(game)
            self.assertEqual(english['SA__026'], 'Save Game')
            self.assertEqual(english['SYST201'], 'Yes')

            (pack / 'overrides.tab').write_text('SA__026\tGuardar partida\r\nSYST201\tS\u00ed\r\n', encoding='utf-8')
            with wave.open(str(pack / 'voices/CNWY034.wav'), 'wb') as out:
                out.setnchannels(1); out.setsampwidth(2); out.setframerate(22050); out.writeframes(b'\0\0' * 10)
            self.assertTrue(language_pack.check(pack, game))

            (pack / 'overrides.tab').write_text('NOPE001\tx\r\nSA__026\t\u2603\r\n', encoding='utf-8')
            with wave.open(str(pack / 'voices/CNWY034.wav'), 'wb') as out:
                out.setnchannels(1); out.setsampwidth(1); out.setframerate(22050); out.writeframes(b'\0' * 10)
            self.assertFalse(language_pack.check(pack, game))


if __name__ == '__main__':
    unittest.main()
