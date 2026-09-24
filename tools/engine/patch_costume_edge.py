"""Remove gray matte RGB from Guybrush's separate head cels at presentation."""
from pathlib import Path


def patch(root, edit):
    gfx = root / 'engines/scumm/gfx.cpp'
    if '#include "scumm/hd_costume_edge.h"' not in gfx.read_text():
        edit('engines/scumm/gfx.cpp', '#include "scumm/hd_scene_visibility.h"',
             '#include "scumm/hd_scene_visibility.h"\n#include "scumm/hd_costume_edge.h"')
    for name in ('hd_costume_edge.h', 'quiver_composite.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
