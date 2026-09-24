"""Preserve native actor depth when replacing room-object textures."""
from pathlib import Path


def patch(root, edit):
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "scumm/quiver_native.h"',
         '#include "scumm/quiver_native.h"\n#include "scumm/hd_object_depth.h"')
    marker = '\t// Step 2.5: Overlay HD object textures on top of composite (after 8-bit compositing)'
    edit(gfx, marker, '#include "scumm/hd_object_depth.inc"\n' + marker)
    # Replace only room-object painting; blast/verb UI retains its overlay pass.
    file = root / gfx
    text = file.read_text()
    if 'HdObjectDepth::blit(' not in text:
        start = text.index('\t\t\tfor (int oy = 0; oy < hdObjH; oy++) {',
                           text.index('// Blit HD object with alpha transparency'))
        end = text.index('\n#ifndef NDEBUG', start)
        before = text[start:end]
        if 'Cover ALL pixels within HD object bounding box' not in before:
            raise RuntimeError('Pinned HD object blit changed')
        edit(gfx, before, '''\t\t\tHdObjectDepth::blit((uint32 *)_hdComposite.getPixels(), _hdComposite.pitch / 4,
                hdW, hdH, (const uint32 *)hdObjSurfPtr->getPixels(), hdObjSurfPtr->pitch / 4,
                hdObjW, hdObjH, (int)hdX, (int)hdY, scale,
                nativeActorMask.data(), hdAlphaMask);
''')
    # The cannon door's provider matte contains a gray RGB fringe. Correct only
    # this texture at presentation time; retain its master and alpha coverage.
    text = file.read_text()
    old = 'nativeActorMask.data(), hdAlphaMask);'
    new = 'nativeActorMask.data(), hdAlphaMask, _currentRoom == 9 && od.obj_nr == 275);'
    if old in text:
        file.write_text(text.replace(old, new, 1))
    elif new not in text:
        raise RuntimeError('HD object edge correction hook missing')
    for name in ('hd_object_depth.h', 'hd_object_depth.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
