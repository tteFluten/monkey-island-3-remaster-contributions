"""Missing legacy atlases must not intercept the HD font-sheet render path."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DialogueFontScopeTests(unittest.TestCase):
    def test_missing_atlases_and_nested_scope_restoration(self):
        engine = ROOT / '.playtest/engine'
        if not shutil.which('c++') or not (engine / 'build/config.h').exists():
            self.skipTest('Configured local engine and C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'scope.cpp'
            binary = Path(directory) / 'scope'
            source.write_text(r'''
#include "dialogue_font.h"
#include <cassert>
static bool atlasesLoaded = false;
namespace Scumm {
DialogueFont::~DialogueFont() {}
bool DialogueFont::available() const { return atlasesLoaded; }
}
int main() {
    Scumm::DialogueFont font;
    // Reproduction: an eligible dialogue with the legacy assets disabled
    // must fall through to HdFontManager, not force native NUT rendering.
    for (int scale : {4, 6}) {
        Scumm::DialogueFontScope scope(font, true, scale);
        assert(!font.active);
        assert(font.scale == scale);
    }
    assert(!font.active && font.scale == 4);

    atlasesLoaded = true;
    {
        Scumm::DialogueFontScope dialogue(font, true, 6);
        assert(font.active && font.scale == 6);
        {
            Scumm::DialogueFontScope menu(font, false, 4);
            assert(!font.active && font.scale == 4);
        }
        assert(font.active && font.scale == 6);
    }
    assert(!font.active && font.scale == 4);
}
''')
            subprocess.run(['c++', '-std=c++11', '-DHAVE_CONFIG_H',
                            '-I', str(ROOT / 'tools/engine'),
                            '-I', str(engine / 'build'), '-I', str(engine / 'source'),
                            str(source), '-o', str(binary)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
