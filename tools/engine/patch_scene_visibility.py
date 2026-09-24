"""Use native visibility and palette effects over HD room backgrounds."""
from pathlib import Path


def patch(root, edit):
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "scumm/hd_actor_shadow.h"',
         '#include "scumm/hd_actor_shadow.h"\n#include "scumm/hd_scene_visibility.h"')
    file = root / gfx
    text = file.read_text()
    if 'HdSceneVisibility::roomObject(' not in text:
        start = text.index('\t\t\t// Skip objects with state == 0 in the 8-bit engine')
        end = text.index('\n\t\t\tconst Graphics::Surface *hdObjSurfPtr', start)
        text = text[:start] + '''\t\t\t// Only replace a room image the original engine actually displays.
            if (!HdSceneVisibility::roomObject(_objs, _numLocalObjects, oi)) continue;
            const int objRoom = _currentRoom;
            const int objState = HdSceneVisibility::imageIndex(getState(od.obj_nr));
            if (objState < 0 || !_hdObjectManager->hasObject(od.obj_nr, objRoom, objState)) {
                ++step25_skipped;
                continue; // A missing state keeps the original image, never another state.
            }
''' + text[end:]
        start = text.index('\t\t\t// CULL: only render HD object')
        end = text.index('\t\t\t// Blit HD object with alpha transparency', start)
        text = text[:start] + '''            // Pixel differences cannot establish object visibility: unrelated
            // actors/waves overlap the same rectangle. Only clip offscreen bounds.
            if (xPos >= visW || yPos >= visH ||
                xPos + hdObjSurfPtr->w / scale <= 0 || yPos + hdObjSurfPtr->h / scale <= 0) {
                ++step25_culled;
                continue;
            }

''' + text[end:]
    # The legacy costume pack must use the same native effect fallback.
    anchor = '// ── Complete character heuristic'
    before = '\t\t\t' + anchor
    after = '\t\t\tif (HdSceneVisibility::nativePaletteEffect(_currentRoom, a->_costume)) continue;\n\n' + before
    if after not in text:
        if before not in text:
            raise RuntimeError('Legacy costume collection hook missing')
        text = text.replace(before, after, 1)
    # Remove the old heuristic's explanation as well as its implementation.
    start = text.find('\t// ── Inventory Active Detection')
    if start >= 0:
        end = text.index('\t\t// V8 (COMI): objects drawn in reverse ID order', start)
        text = text[:start] + text[end:]
    file.write_text(text)
    for name in ('hd_scene_visibility.h',):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
