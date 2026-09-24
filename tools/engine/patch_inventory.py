"""Replace the native inventory panel and composite its icons above it."""
from pathlib import Path


def patch(root, edit):
    edit('engines/scumm/scumm_v6.h', '\tvoid drawBlastObject(BlastObject *eo);',
         '\tvoid drawBlastObject(BlastObject *eo, bool hdInventory = false);')
    edit('engines/scumm/scumm_v6.h', '\tint getBlastCount() const',
         '\tbool hasHDInventory();\n\tvoid drawHDInventory();\n\tint getBlastCount() const')
    edit('engines/scumm/object.cpp', '#include "scumm/bomp.h"',
         '#include "scumm/bomp.h"\n#include "scumm/hd_object_manager.h"\n#include "scumm/hd_inventory.h"')
    edit('engines/scumm/object.cpp', 'void ScummEngine_v6::drawBlastObject(BlastObject *eo) {',
         '''#include "scumm/hd_inventory.inc"

void ScummEngine_v6::drawBlastObject(BlastObject *eo, bool hdInventory) {
    // Keep the original restoration/hit rectangles, but never bake the old
    // chest or its icons into the scene underneath the replacement panel.
    if (!hdInventory && HdInventory::isObject(eo->number) && hasHDInventory()) return;''')
    edit('engines/scumm/object.cpp', '\tdrawBomp(bdd);\n\n\tmarkRectAsDirty',
         '\tif (hdInventory) {\n#include "scumm/hd_inventory_blast.inc"\n\t\treturn;\n\t}\n\tdrawBomp(bdd);\n\n\tmarkRectAsDirty')
    file = root / 'engines/scumm/gfx.cpp'
    text = file.read_text()
    start = text.find('\t// Step 2.5b: Render inventory items from blast queue')
    if start >= 0:
        end = text.index('\n#include "scumm/hd_actor_lighting.inc"', start)
        text = text[:start] + text[end:]
    file.write_text(text)
    edit('engines/scumm/gfx.cpp', '\t// Step 2.7: Render HD font characters recorded during 8-bit drawing',
         '\t// Native inventory UI: panel first, then every queued item, above the scene.\n\tstatic_cast<ScummEngine_v6 *>(this)->drawHDInventory();\n\n\t// Step 2.7: Render HD font characters recorded during 8-bit drawing')
    # Hidden verb slots retain their resource IDs after killVerb().
    edit('engines/scumm/gfx.cpp', 'if (!vst->hd_obj_nr || vst->hd_obj_nr == 114)',
         'if (!vst->verbid || !vst->curmode || vst->saveid || !vst->hd_obj_nr || vst->hd_obj_nr == 114)')
    for name in ('hd_inventory.h', 'hd_inventory.inc', 'hd_inventory_blast.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
