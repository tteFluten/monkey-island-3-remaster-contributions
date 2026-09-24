"""Optional camera depth of field over the original z-plane foreground."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_depth_of_field.h', 'hd_depth_of_field.inc'):
        (root / 'engines/scumm' / name).write_bytes((here / name).read_bytes())
    gfx = 'engines/scumm/gfx.cpp'
    # Standard headers belong outside namespace Scumm, with the other HD headers.
    edit(gfx, '#include "scumm/hd_costume_edge.h"',
         '#include "scumm/hd_costume_edge.h"\n#include "scumm/hd_depth_of_field.h"')
    edit(gfx, '#include "scumm/hd_aspect.inc"\n',
         '#include "scumm/hd_aspect.inc"\n#include "scumm/hd_depth_of_field.inc"\n')
    # Anchor after the aspect block so its own repeat edit still matches.
    edit('engines/scumm/scumm.h', '    const Graphics::Surface *_hdBackendCursor = nullptr;', '''    const Graphics::Surface *_hdBackendCursor = nullptr;
    int hdDepthOfFieldLevel() const;
    void renderHDDepthOfField(int backgroundX, int visW, int visH);
    uint32 hdDepthOfFieldBackground(int x, int y, int backgroundX, uint32 sharp) const;
    bool handleHDDepthOfFieldEvent(const Common::Event &event);
    void drawHDDepthOfFieldMenu();
    bool _hdDepthOfFieldMouseDown = false;''')
    # Blur the painting before native foreground, objects, costumes and UI.
    edit(gfx, '#include "scumm/quiver_prepare.inc"',
         '\trenderHDDepthOfField(srcBgX, visW, visH);\n\n#include "scumm/quiver_prepare.inc"')
    edit(gfx, '\t\t\t\t\t\t\t\tdstRow[ox] = bgR | (bgG << 8) | (bgB << 16) | (0xFF << 24);',
         '\t\t\t\t\t\t\t\tdstRow[ox] = hdDepthOfFieldBackground(maskX, maskY, bgRX,\n'
         '\t\t\t\t\t\t\t\t\tbgR | (bgG << 8) | (bgB << 16) | (0xFF << 24));')
    edit('engines/scumm/input.cpp', '\tif (handleHDAspectEvent(event)) return;',
         '\tif (handleHDAspectEvent(event)) return;\n\tif (handleHDDepthOfFieldEvent(event)) return;')
    edit(gfx, '\tdrawHDAspectMenu();\n\tdrawHDFontSizeMenu();',
         '\tdrawHDDepthOfFieldMenu();\n\tdrawHDAspectMenu();\n\tdrawHDFontSizeMenu();')
