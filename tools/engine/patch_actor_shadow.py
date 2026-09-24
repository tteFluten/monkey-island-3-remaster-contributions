"""Procedural solid oval contact shadows beneath grounded characters."""
from pathlib import Path


def patch(root, edit):
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "scumm/hd_actor_lighting.h"',
         '#include "scumm/hd_actor_lighting.h"\n#include "scumm/hd_actor_shadow.h"')
    # Keep the existing SVG include/comment anchor intact for repeat builds.
    marker = '\t// Step 2: Composite game content (8-bit → 32-bit via palette) over HD background'
    edit(gfx, marker, marker + '\n#include "scumm/hd_actor_shadow.inc"')
    for name in ('hd_actor_shadow.h', 'hd_actor_shadow.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
