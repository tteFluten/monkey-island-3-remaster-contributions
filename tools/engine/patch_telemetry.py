"""Measure completed native swaps, separately from CPU compositing/request rates."""
from pathlib import Path

def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_remaster.h', 'hd_color_grade.h'):
        (root / 'common' / name).write_bytes((here / name).read_bytes())
    for path in ('engines/scumm/gfx.cpp', 'engines/scumm/scumm.cpp',
                 'backends/graphics/openglsdl/openglsdl-graphics.cpp'):
        edit(path, '#include "common/config-manager.h"', '#include "common/config-manager.h"\n#include "common/hd_remaster.h"')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '\tuint32 _hdFrameStartTime = _system->getMillis();',
         '\tconst double hdCpuStarted = HdRemaster::milliseconds();\n\tHdRemaster::state().room = _currentRoom;\n\tuint32 _hdFrameStartTime = _system->getMillis();')
    edit(gfx, '\t// HD debug dump — trigger dump when _hdDebugDumpCount >= 3',
         '\tHdRemaster::state().cpuWork += HdRemaster::milliseconds() - hdCpuStarted;\n\t// HD debug dump — trigger dump when _hdDebugDumpCount >= 3')
    gl = 'backends/graphics/openglsdl/openglsdl-graphics.cpp'
    edit(gl, '\tSDL_GL_SwapWindow(_window->getSDLWindow());', '''\tSDL_GL_SwapWindow(_window->getSDLWindow());
    if (ConfMan.hasKey("playtest_session")) {
        HdRemaster::state().highResTime = []() -> double { return 1000.0 * SDL_GetPerformanceCounter() / SDL_GetPerformanceFrequency(); };
        SDL_GL_GetDrawableSize(_window->getSDLWindow(), &HdRemaster::state().drawableWidth,
                              &HdRemaster::state().drawableHeight);
        HdRemaster::state().presented(HdRemaster::milliseconds());
    }''')
