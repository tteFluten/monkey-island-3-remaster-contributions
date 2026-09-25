"""Replace known ambient water sprites with masked, presentation-rate shading."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'common/hd_water.h').write_bytes((here / 'hd_water.h').read_bytes())
    (root / 'engines/scumm/hd_water_surface.inc').write_bytes((here / 'hd_water_surface.inc').read_bytes())
    edit('engines/scumm/gfx.cpp', 'namespace Scumm {',
         'namespace Scumm {\n#include "scumm/hd_water_surface.inc"')
    # All successful replacements are in quiverPoses, including the empty
    # water poses. The legacy pack must not paint those PNGs back over the GPU.
    edit('engines/scumm/gfx.cpp',
         'if (HdSceneVisibility::nativePaletteEffect(_currentRoom, a->_costume)) continue;',
         '''if (HdSceneVisibility::nativePaletteEffect(_currentRoom, a->_costume)) continue;
            bool shaderWater = false;
            for (const auto &pose : quiverPoses)
                if (pose.actor == a && pose.water) { shaderWater = true; break; }
            if (shaderWater) continue;''')
    edit('engines/scumm/scumm.cpp', 'void ScummEngine::pauseEngineIntern(bool pause) {',
         'void ScummEngine::pauseEngineIntern(bool pause) {\n    HdRemaster::state().waterPaused = pause;')
    edit('engines/scumm/gfx.cpp',
         'const bool interpolation = _hdInterpolating, hadDof = remaster.dof;',
         'const bool interpolation = _hdInterpolating, hadDof = remaster.dof, hadWater = remaster.water, hadWaterSurface = remaster.waterSurface;')
    edit('engines/scumm/gfx.cpp', 'remaster.active = remaster.ui = true; remaster.dof = hadDof;',
         'remaster.active = remaster.ui = true; remaster.dof = hadDof; remaster.water = hadWater; remaster.waterSurface = hadWaterSurface;')
    # No eager PNG decoding for ambient water in GPU mode. Compatibility mode
    # retains the existing loader and all fallback artwork.
    manager = 'engines/scumm/hd_costume_manager.h'
    edit(manager, '#include "scumm/hd_scene_visibility.h"',
         '#include "scumm/hd_scene_visibility.h"\n#include "common/hd_remaster.h"\n#include "common/config-manager.h"')
    edit(manager, 'if (*owner == room && !HdSceneVisibility::nativePaletteEffect(room, it->_key))',
         '''if (*owner == room && !HdSceneVisibility::nativePaletteEffect(room, it->_key) &&
                    !(HdRemaster::state().active && HdWater::ambient(room, it->_key) &&
                      (!ConfMan.hasKey("hd_water_shader") || ConfMan.getBool("hd_water_shader"))))''')
    edit('engines/scumm/gfx.cpp',
         'actor->_costume && !HdSceneVisibility::nativePaletteEffect(_currentRoom, actor->_costume))',
         '''actor->_costume && !HdSceneVisibility::nativePaletteEffect(_currentRoom, actor->_costume) &&
                        !(remaster.water && HdWater::ambient(_currentRoom, actor->_costume)))''')
