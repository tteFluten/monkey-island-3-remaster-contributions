from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class ExactRoomTests(unittest.TestCase):
    def test_pack_scope_and_original_fallback(self):
        if not shutil.which('c++'):self.skipTest('C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'common').mkdir()
            (root/'common/config-manager.h').write_text('''#include <string>
struct Config { std::string pack; bool hasKey(const char*) const { return !pack.empty(); }
std::string get(const char*) const { return pack; } }; static Config ConfMan;
''')
            (root/'test.cpp').write_text('''#include "exact_costume_rooms.h"
#include <cassert>
int main() {
 for (const char *pack : {"topaz", "topaz-crisp"}) {
  ConfMan.pack=pack;
  for(int room : {1,9,10,16,51,87,94}) assert(Scumm::playtestExactRoom(room));
  assert(!Scumm::playtestExactRoom(0));
 }
 for(const char *pack : {"quiver", "original", ""}) {
  ConfMan.pack=pack;
  assert(Scumm::playtestExactRoom(9));assert(Scumm::playtestExactRoom(87));
  for(int room : {10,16,51}) assert(!Scumm::playtestExactRoom(room));
 }
}''')
            includes=Path(__file__).resolve().parent/'engine'
            subprocess.run(['c++','-std=c++11','-I'+str(root),'-I'+str(includes),str(root/'test.cpp'),'-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True)


if __name__=='__main__':unittest.main()
