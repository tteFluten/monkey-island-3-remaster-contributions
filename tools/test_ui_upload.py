"""Changing or erasing dialogue must update every affected texture row."""
import shutil, subprocess, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class UIUploadTests(unittest.TestCase):
    def test_dirty_rows_and_erased_text(self):
        if not shutil.which('c++'): self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'ui.cpp'; binary=Path(tmp)/'ui'
            source.write_text(r'''
#include "hd_ui_upload.h"
#include <cassert>
#include <cstring>
int main() {
 unsigned char previous[8*12]={}, current[8*16]={};
 auto check=[&](int top,int bottom) {
  auto r=HdUIUpload::changed(previous,12,current,16,8,8);
  assert(r.top==top && r.bottom==bottom);
  for(int y=r.top;y<r.bottom;++y) std::memcpy(previous+y*12,current+y*16,8);
  for(int y=0;y<8;++y) assert(!std::memcmp(previous+y*12,current+y*16,8));
 };
 check(8,8);
 current[2*16+1]=255; current[3*16+7]=128; check(2,4);
 current[2*16+1]=0; current[3*16+7]=0; current[6*16+2]=200; check(2,7);
 current[6*16+2]=0; check(6,7); check(8,8);
 current[15]=128; check(8,8); // Padding does not belong to the texture.
 current[0]=100; current[7*16+7]=254; check(0,8);
}
''')
            subprocess.run(['c++','-std=c++11','-fsanitize=address,undefined','-I',str(ROOT/'tools/engine'),str(source),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True,capture_output=True,timeout=10)
if __name__=='__main__': unittest.main()
