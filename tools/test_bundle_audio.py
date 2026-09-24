"""Exercise the patched native audio loader against invalid and valid headers."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BundleAudioTests(unittest.TestCase):
    def test_native_loader_rejects_bad_headers_and_keeps_valid_audio(self):
        root = Path(__file__).resolve().parents[1]
        source = root / '.playtest/engine/source/engines/scumm/imuse_digi/dimuse_bndmgr.cpp'
        if not source.exists() or not shutil.which('c++'):
            self.skipTest('Prepared native engine and C++ compiler required')
        text = source.read_text()
        method = text[text.index('bool BundleMgr::loadCompTable('):text.index('int32 BundleMgr::seekFile(')]
        harness = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
using int32 = int32_t; using uint32 = uint32_t; using int64 = int64_t; using byte = unsigned char;
#define MKTAG(a,b,c,d) ((uint32(a)<<24)|(uint32(b)<<16)|(uint32(c)<<8)|uint32(d))
const char *tag2str(uint32) { return "fixture"; }
void warning(const char *, ...) {}
void debug(const char *, ...) {}
struct File {
    std::vector<byte> data = std::vector<byte>(64, 0);
    int pos = 0, bytesRead = 0;
    bool seek(int offset, int mode) {
        int target = mode == SEEK_SET ? offset : pos + offset;
        if (target < 0 || target > (int)data.size()) return false;
        pos = target; return true;
    }
    int64 size() const { return data.size(); }
    uint32 readUint32BE() {
        assert(pos + 4 <= (int)data.size()); bytesRead += 4;
        uint32 v = 0; for (int i = 0; i < 4; ++i) v = (v << 8) | data[pos++]; return v;
    }
    std::string getDebugName() { return "test.bun"; }
    void put(int p, uint32 v) { for (int i=3;i>=0;--i) { data[p+i]=v&255; v>>=8; } }
};
struct BundleMgr {
    struct Entry { int32 offset=0, size=64; char filename[24]="speech.imx"; } _bundleTable[1];
    struct CompTable { int32 offset, size, codec; };
    File file;
    File *_file = &file;
    bool _isUncompressed = false;
    int32 _numCompItems = 0, _lastBlockDecompressedSize = 0;
    CompTable *_compTable = nullptr;
    byte *_compInputBuff = nullptr;
    BundleMgr() {
        file.put(0, MKTAG('C','O','M','P')); file.put(4,1); file.put(12,4);
        file.put(16,32); file.put(20,4); file.put(24,0);
    }
    ~BundleMgr() { free(_compTable); free(_compInputBuff); }
    bool loadCompTable(int32);
};
'''
        cases = r'''
int main() {
    { BundleMgr b; assert(b.loadCompTable(0)); assert(b._numCompItems==1); assert(b._compTable[0].size==4); }
    { BundleMgr b; b.file.put(0,MKTAG('i','M','U','S')); assert(b.loadCompTable(0)); assert(b._isUncompressed); }
    { BundleMgr b; b.file.put(0,0xc8912822); b.file.put(4,0xffa32119);
      assert(!b.loadCompTable(0)); assert(b.file.bytesRead==4); assert(!b._compTable); }
    { BundleMgr b; b.file.put(4,0); assert(!b.loadCompTable(0)); assert(!b._compTable); }
    { BundleMgr b; b.file.put(4,0xffffffff); assert(!b.loadCompTable(0)); assert(!b._compTable); }
    { BundleMgr b; b.file.put(4,0x7fffffff); assert(!b.loadCompTable(0)); assert(!b._compTable); }
    { BundleMgr b; b.file.put(4,4); assert(!b.loadCompTable(0)); } // table larger than entry
    { BundleMgr b; b._bundleTable[0].size=15; assert(!b.loadCompTable(0)); assert(!b.file.bytesRead); }
    { BundleMgr b; b._bundleTable[0].offset=-1; assert(!b.loadCompTable(0)); }
    { BundleMgr b; b._bundleTable[0].offset=32; assert(!b.loadCompTable(0)); }
    { BundleMgr b; b.file.data.resize(63); assert(!b.loadCompTable(0)); }
    { BundleMgr b; b._bundleTable[0].offset=0x7fffffff; assert(!b.loadCompTable(0)); }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'bundle.cpp'
            binary = Path(directory) / 'bundle'
            cpp.write_text(harness + method + cases)
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined', str(cpp), '-o', str(binary)],
                           check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
