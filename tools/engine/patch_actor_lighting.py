"""Carry the game's live RGB palette shading into the HD costume compositor."""
from pathlib import Path


def patch(root, edit):
    edit('engines/scumm/actor.h', '#include "scumm/scumm.h"',
         '#include "scumm/scumm.h"\n#include "scumm/hd_actor_lighting.h"')
    edit('engines/scumm/actor.h', '\tint _hdRelX = 0, _hdRelY = 0;',
         '\tunsigned int _hdPaletteUsage[256] = {};\n\tint hdPaletteColor(int slot) const { return _palette[slot]; }\n\tint _hdRelX = 0, _hdRelY = 0;')
    edit('engines/scumm/actor.cpp', 'void Actor::initActor(int mode) {',
         'void Actor::initActor(int mode) {\n\tmemset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));')
    needle = '\t\t// Record the vertical extent of the drawn actor'
    edit('engines/scumm/actor.cpp', needle, needle + '''
        memset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));
        if (quiverCapture) {
            for (uint i = 0; i < _quiverAfter.size(); ++i)
                if (_quiverAfter[i] != _quiverUnder[i]) ++_hdPaletteUsage[_quiverAfter[i]];
        }''')
    # Costume changes and restored saves must not use the previous pose's usage.
    edit('engines/scumm/actor.cpp', '\t// V1 zak uses palette[] as a dynamic costume color array.',
         '\tmemset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));\n\t// V1 zak uses palette[] as a dynamic costume color array.')
    edit('engines/scumm/actor.cpp', '\ts.syncArray(_palette, 64,',
         '\tif (s.isLoading()) memset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));\n\ts.syncArray(_palette, 64,')
    # Keep earlier patch anchors intact when upgrading an existing build.
    edit('engines/scumm/actor.h', '\tunsigned int _hdPaletteUsage[256] = {};',
         '\tHdActorLighting::StableSamples _hdLightingSamples;\n\tunsigned int _hdPaletteUsage[256] = {};')
    init = 'void Actor::initActor(int mode) {\n\tmemset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));'
    edit('engines/scumm/actor.cpp', init, init + '\n\t_hdLightingSamples.reset();')
    costume = '\tmemset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));\n\t// V1 zak uses palette[] as a dynamic costume color array.'
    edit('engines/scumm/actor.cpp', costume, '\t_hdLightingSamples.reset();\n' + costume)
    load = '\tif (s.isLoading()) memset(_hdPaletteUsage, 0, sizeof(_hdPaletteUsage));'
    edit('engines/scumm/actor.cpp', load, '\tif (s.isLoading()) _hdLightingSamples.reset();\n' + load)
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "scumm/hd_object_depth.h"',
         '#include "scumm/hd_object_depth.h"\n#include "scumm/hd_actor_lighting.h"')
    # Insert before the Quiver pass, without separating other patch anchors.
    edit(gfx, '\tconst bool quiverActive =',
         '#include "scumm/hd_actor_lighting.inc"\n\tconst bool quiverActive =')
    edit(gfx, '\t\t\tstep26_loaded++;',
         '\t\t\tconst HdActorLighting::Tint lighting = actorLighting(a);\n\t\t\tstep26_loaded++;')
    edit(gfx, '\t\t\t\t\tuint32 pix = srcRow[srcX];',
         '\t\t\t\t\tuint32 pix = lighting.apply(srcRow[srcX]);')
    for name in ('hd_actor_lighting.h', 'hd_actor_lighting.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
