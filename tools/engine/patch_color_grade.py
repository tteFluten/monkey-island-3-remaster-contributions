"""Per-room color grades and the playtest Look panel (focus + color)."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_color_grade.h', 'hd_color_grade.inc', 'hd_scene_look.h'):
        (root / 'engines/scumm' / name).write_bytes((here / name).read_bytes())
    gfx = 'engines/scumm/gfx.cpp'
    # Anchors follow the depth-of-field patch so its repeat edits still match.
    edit(gfx, '#include "scumm/hd_depth_of_field.h"',
         '#include "scumm/hd_depth_of_field.h"\n#include "scumm/hd_color_grade.h"\n#include "scumm/hd_scene_look.h"\n#include "common/formats/json.h"')
    edit(gfx, '#include "scumm/hd_depth_of_field.inc"\n',
         '#include "scumm/hd_depth_of_field.inc"\n#include "scumm/hd_color_grade.inc"\n')
    edit('engines/scumm/scumm.h', '    bool _hdDepthOfFieldMouseDown = false;', '''    bool _hdDepthOfFieldMouseDown = false;
    void renderHDColorGrade();
    bool handleHDLookEvent(const Common::Event &event);
    void drawHDLookPanel();
    Common::Point hdLookPosition() const;''')
    # Grade the scene before HD text, verbs, inventory and cursor are drawn.
    marker = '\t// Step 2.7: Render HD font characters recorded during 8-bit drawing'
    inventory = '\t// Native inventory UI: panel first, then every queued item, above the scene.'
    if inventory in (root / gfx).read_text():
        marker = inventory
    edit(gfx, marker, '\trenderHDColorGrade();\n\n' + marker)
    edit('engines/scumm/input.cpp', '\tif (handleHDDepthOfFieldEvent(event)) return;',
         '\tif (handleHDDepthOfFieldEvent(event)) return;\n\tif (handleHDLookEvent(event)) return;')
    # Before the other overlays: the font-size patch anchors on the gap after its call.
    edit(gfx, '\tdrawHDDepthOfFieldMenu();\n\tdrawHDAspectMenu();',
         '\tdrawHDLookPanel();\n\tdrawHDDepthOfFieldMenu();\n\tdrawHDAspectMenu();')
