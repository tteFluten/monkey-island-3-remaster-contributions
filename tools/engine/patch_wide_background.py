"""Present optional cannon side scenery behind the original gameplay surface."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'backends/graphics/opengl/hd_wide_background.inc').write_bytes(
        (here / 'hd_wide_background.inc').read_bytes())
    (root / 'common/hd_color_grade.h').write_bytes((here / 'hd_color_grade.h').read_bytes())
    edit('engines/scumm/scumm.h', '\tint _hdScale = 1;',
         '\tint _hdScale = 1;\n    void publishHDWideBackground(bool movie = false);')
    gl = 'backends/graphics/opengl/opengl-graphics.cpp'
    edit(gl, '#include "common/file.h"', '#include "common/file.h"\n#include "common/fs.h"')
    edit(gl, '#include "common/fs.h"', '#include "common/fs.h"\n#include "common/hd_color_grade.h"')
    edit('backends/graphics/opengl/opengl-graphics.h', '\tSurface *_gameScreen;', '''\tSurface *_gameScreen;
    Surface *_hdWideBackground = nullptr;
    Common::String _hdWideBackgroundKey;
    void updateHDWideBackground();
    void drawHDWideBackground();''')
    edit(gl, 'OpenGLGraphicsManager::~OpenGLGraphicsManager() {',
         'OpenGLGraphicsManager::~OpenGLGraphicsManager() {\n    delete _hdWideBackground;')
    edit(gl, 'namespace OpenGL {',
         'namespace OpenGL {\n\n#include "hd_wide_background.inc"')
    edit(gl, '\t// We only update the screen when there actually have been any changes.',
         '    updateHDWideBackground();\n\n\t// We only update the screen when there actually have been any changes.')
    edit(gl, '\t// First step: Draw the (virtual) game screen.',
         '    drawHDWideBackground();\n\n\t// First step: Draw the (virtual) game screen.')
    edit(gl, '\t\t_gameScreen->recreate();',
         '\t\t_gameScreen->recreate();\n        if (_hdWideBackground) _hdWideBackground->recreate();')
    edit(gl, 'void OpenGLGraphicsManager::notifyContextDestroy() {',
         'void OpenGLGraphicsManager::notifyContextDestroy() {\n    if (_hdWideBackground) _hdWideBackground->destroy();')
