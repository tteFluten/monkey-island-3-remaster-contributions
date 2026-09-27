"""Inventory compositor: alpha, layering, native fallback, scale and clipping."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

if __package__:
    from .engine.patch_color_grade import patch as patch_color_grade
    from .engine.patch_inventory import patch as patch_inventory
else:
    from engine.patch_color_grade import patch as patch_color_grade
    from engine.patch_inventory import patch as patch_inventory


class InventoryTests(unittest.TestCase):
    def test_color_grade_precedes_inventory_and_patches_repeat(self):
        # Exercise both a fresh combined build and an engine already using
        # main's color-grade patch before inventory support is added.
        for existing_color_grade in (False, True):
            with self.subTest(existing_color_grade=existing_color_grade), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'engines/scumm'
                source.mkdir(parents=True)
                fixtures = {
                    'scumm.h': '    bool _hdDepthOfFieldMouseDown = false;\n\tint _hdScale = 1;\n',
                    'scumm.cpp': 'VAR(VAR_MOUSE_X) = _mouse.x;\nVAR(VAR_VIRT_MOUSE_X) = _virtualMouse.x;\n',
                    'verbs.cpp': 'int ScummEngine::findVerbAtPos(int x, int y) const {\n',
                    'scumm_v6.h': '\tvoid drawBlastObject(BlastObject *eo);\n\tint getBlastCount() const\n',
                    'input.cpp': '\tif (handleHDDepthOfFieldEvent(event)) return;\n',
                    'object.cpp': '#include "scumm/bomp.h"\n'
                        'void ScummEngine_v6::drawBlastObject(BlastObject *eo) {\n'
                        '\tdrawBomp(bdd);\n\n\tmarkRectAsDirty\n',
                    'gfx.cpp': '#include "scumm/hd_depth_of_field.h"\n'
                        '#include "scumm/hd_depth_of_field.inc"\n'
                        '\t// Step 2.7: Render HD font characters recorded during 8-bit drawing\n'
                        'if (!vst->hd_obj_nr || vst->hd_obj_nr == 114)\n'
                        '\tdrawHDDepthOfFieldMenu();\n\tdrawHDAspectMenu();\n',
                }
                for name, content in fixtures.items():
                    (source / name).write_text(content)

                def edit(name, before, after):
                    file = root / name
                    text = file.read_text()
                    if after not in text:
                        self.assertIn(before, text)
                        file.write_text(text.replace(before, after, 1))

                if existing_color_grade:
                    patch_color_grade(root, edit)
                patch_inventory(root, edit)
                patch_color_grade(root, edit)
                first = {p.name: p.read_bytes() for p in source.iterdir()}
                patch_inventory(root, edit)
                patch_color_grade(root, edit)
                self.assertEqual(first, {p.name: p.read_bytes() for p in source.iterdir()})
                gfx = (source / 'gfx.cpp').read_text()
                grade = 'renderHDColorGrade();'
                inventory = 'static_cast<ScummEngine_v6 *>(this)->drawHDInventory();'
                self.assertEqual(gfx.count(grade), 1)
                self.assertEqual(gfx.count(inventory), 1)
                self.assertLess(gfx.index(grade), gfx.index(inventory))
                self.assertLess(gfx.index(inventory), gfx.index('// Step 2.7:'))

    def test_panel_items_and_clipping(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'inventory.cpp'
            binary = Path(directory) / 'inventory'
            source.write_text(r'''
#include "hd_inventory.h"
#include <cassert>
#include <vector>
struct Surface {
    int w, h, bpp;
    std::vector<unsigned int> data;
    Surface(int w_, int h_, int bpp_ = 4): w(w_), h(h_), bpp(bpp_), data(w*h) {}
    void *getBasePtr(int x, int y) { return (unsigned char *)data.data() + (y*w+x)*bpp; }
    const void *getBasePtr(int x, int y) const { return (const unsigned char *)data.data() + (y*w+x)*bpp; }
};
int main() {
    using namespace HdInventory;
    assert(imageIndex(1) == 0 && imageIndex(2) == 1 && imageIndex(0) == -1);
    assert(centerOffset(640) == 0 && centerOffset(864) == 112);
    // Centering changes UI placement only, with the inverse used for input.
    assert(432 - centerOffset(864) == 320);
    assert(over(0x800000ff, 0) == 0x80000080);
    assert(overScene(over(0x800000ff, 0), 0xff000011) == over(0x800000ff, 0xff000011));
    Surface scene(8,8), panel(2,2), item(1,1);
    for (auto &p: scene.data) p = 0xff000011;
    panel.data = {0, 0xff000033, 0xff000033, 0x80000055};
    blit(scene, panel, 0, 0, 8, 8);
    assert(scene.data[0] == 0xff000011); // transparent border reveals scene, no old panel
    assert(scene.data[7] == 0xff000033);
    assert(scene.data[63] == 0xff000033); // true alpha blend
    item.data[0] = 0xff123456;
    blit(scene, item, 2, 5, 2, 2);
    assert(scene.data[5*8+2] == item.data[0]); // item above panel
    assert(scene.data[7*8+2] == 0xff000033); // neighboring wood retained
    Surface native(2,1,1);
    auto bytes = (unsigned char *)native.getBasePtr(0,0);
    bytes[0] = 7; bytes[1] = 255;
    unsigned char palette[768] = {};
    palette[21] = 1; palette[22] = 2; palette[23] = 3;
    blit(scene, native, 2, 5, 4, 2, palette);
    assert(scene.data[5*8+2] == 0xff030201); // missing HD item keeps native palette
    assert(scene.data[5*8+4] == 0xff000033); // BOMP transparency keeps panel
    blit(scene, item, -1, -1, 2, 2);
    assert(scene.data[0] == item.data[0]);
    blit(scene, item, 7, 7, 8, 8);
    assert(scene.data[63] == item.data[0]);
    blit(scene, item, -20, -20, 2, 2);
    blit(scene, item, 20, 20, 2, 2);
    blit(scene, item, 0, 0, 0, 0);
    // Same native icon geometry at the supported 4x and 6x scales.
    for (int scale: {4,6}) {
        Surface canvas(10*scale,10*scale);
        blit(canvas, item, scale, 2*scale, 2*scale, 3*scale);
        int count = 0;
        for (auto p: canvas.data) if (p == item.data[0]) ++count;
        assert(count == 6*scale*scale);
    }
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(Path(__file__).parent / 'engine'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
