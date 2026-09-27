"""Keep the complete HD frame behind engine banners such as the quit prompt.

Also retire the book's Quit request once its prompt is answered.
"""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_banner.h', 'hd_banner.inc'):
        (root / 'engines/scumm' / name).write_bytes((here / name).read_bytes())
    edit('engines/scumm/scumm.h', '\tGraphics::Surface _hdComposite;', '''\tGraphics::Surface _hdComposite;
\t// Last complete HD frame and its native screen, retained while a banner pauses the engine.
\tGraphics::Surface _hdBannerFrame, _hdBannerText;
\tCommon::Array<byte> _hdBannerBase;
\tint _hdBannerState = 0, _hdBannerBaseRoom = -1, _hdBannerBaseX = 0, _hdBannerBaseTop = 0;
\tint _hdBannerBaseW = 0, _hdBannerBaseH = 0;
\tbool renderHDBannerFrame();
\tvoid captureHDBannerBase();
\tvoid drawHDBannerFonts(int hdW, int hdH, int visW, int visH, const byte *native, int pitch);''')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "scumm/quiver_native.h"', '#include "scumm/quiver_native.h"\n#include "scumm/hd_banner.h"')
    edit(gfx, '#include "scumm/hd_motion.inc"', '#include "scumm/hd_motion.inc"\n\n#include "scumm/hd_banner.inc"')
    edit(gfx, '    if (!_hdInterpolating) {\n        captureHDMotion();',
         '    if (renderHDBannerFrame()) return;\n    if (!_hdInterpolating) {\n        captureHDMotion();')
    edit('engines/scumm/scumm.cpp', 'ScummEngine::~ScummEngine() {',
         'ScummEngine::~ScummEngine() {\n    _hdBannerFrame.free();\n    _hdBannerText.free();')
    # Book controls and Scene Look keys must not change settings behind a
    # banner: waitForBannerInput keeps polling parseEvent while it is shown.
    handlers = ('\tif (handleHDFontSizeEvent(event)) return;\n\tif (handleHDAspectEvent(event)) return;\n'
                '\tif (handleHDDepthOfFieldEvent(event)) return;\n\tif (handleHDLookEvent(event)) return;\n')
    edit('engines/scumm/input.cpp', handlers,
         '\tif (!_messageBannerActive) {\n' + handlers.replace('\tif', '\t\tif') + '\t}\n')
    # The book's Quit button (kernel 34) sets _quitFromScriptCmd, but the COMI
    # room-92 prompt never clears it. After "No", any later quit event in the
    # book (window close, Cmd-Q, the workshop's Stop) would prompt again.
    edit('engines/scumm/gfx_gui.cpp', '\t\t\t_comiQuitMenuIsOpen = false;\n',
         '\t\t\t_comiQuitMenuIsOpen = false;\n\t\t\t_quitFromScriptCmd = false;\n')
