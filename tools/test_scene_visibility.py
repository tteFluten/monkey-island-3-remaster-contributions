"""HD replacements must obey native room visibility and preserve sea effects."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SceneVisibilityTests(unittest.TestCase):
    def test_inventory_parent_states_and_native_water(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'scene.cpp'
            binary = Path(directory) / 'scene'
            source.write_text(r'''
#include "hd_scene_visibility.h"
#include <cassert>
struct Object { int obj_nr, state, fl_object_index, parent, parentstate; };
int main() {
    // Inventory panel remains loaded in Puerto Pollo. Overlapping sea pixels
    // (or a positive state) must not make a floating UI resource a room image.
    Object objects[] = {{0,0,0,0,0}, {114,0,3,0,0}, {376,1,0,0,0},
                        {383,1,0,2,2}, {385,0,0,0,0}};
    using namespace HdSceneVisibility;
    assert(!roomObject(objects, 5, 1));
    objects[1].state = 1;
    assert(!roomObject(objects, 5, 1));
    assert(roomObject(objects, 5, 2));
    assert(!roomObject(objects, 5, 3)); // parent closed
    objects[2].state = 2;
    assert(roomObject(objects, 5, 3)); // parent opens
    assert(!roomObject(objects, 5, 4)); // hidden ordinary object
    assert(imageIndex(0) == -1 && imageIndex(1) == 0 && imageIndex(2) == 1);
    objects[3].parent = 3; objects[3].parentstate = 1;
    assert(!roomObject(objects, 5, 3)); // cycle cannot hang the compositor
    objects[3].parent = 99;
    assert(!roomObject(objects, 5, 3));
    assert(!roomObject(objects, 5, -1) && !roomObject(objects, 5, 5));
    // Both halves of the scrolling bay retain the original transparent,
    // palette-driven animation; other costumes still use their HD art.
    assert(nativePaletteEffect(14, 73) && nativePaletteEffect(14, 74));
    assert(!nativePaletteEffect(14, 2) && !nativePaletteEffect(14, 72));
    assert(!nativePaletteEffect(9, 73));
    // Town panorama has different left/right wave resources from the beach.
    assert(nativePaletteEffect(15, 80) && nativePaletteEffect(15, 83));
    assert(!nativePaletteEffect(15, 75) && !nativePaletteEffect(15, 85));
    assert(!nativePaletteEffect(14, 80) && !nativePaletteEffect(9, 83));
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(Path(__file__).parent / 'engine'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
