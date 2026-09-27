"""Keep gameplay speech inside the visible widescreen presentation."""
from pathlib import Path


def patch(root, edit):
    for name in ('hd_subtitle_bounds.h', 'hd_subtitle_test.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
    edit('engines/scumm/scumm_v7.h', '\tstruct BlastText : TextObject {',
         '\tstruct BlastText : TextObject {\n        bool subtitle = false;')
    edit('engines/scumm/scumm.h', '\tstruct HdFontChar {',
         '    bool _hdSubtitleClipActive = false;\n    bool _hdSubtitleProbeEnabled = false;\n\tstruct HdFontChar {')
    edit('engines/scumm/playtest.inc', '\tbool ready = playtestReadyForJump();',
         '\tbool ready = playtestReadyForJump();\n    _hdSubtitleProbeEnabled = getenv("MI3_ENGINE_TEST_INPUT") != nullptr;')
    text = 'engines/scumm/string_v7.cpp'
    edit(text, '#include "common/config-manager.h"', '''#include "common/config-manager.h"
#include "common/file.h"
#include "common/fs.h"
#include "common/hd_remaster.h"
#include "scumm/hd_subtitle_bounds.h"''')
    edit(text, '\tbt.charset = charset;', '\tbt.charset = charset;\n    bt.subtitle = ttsIsSubtitle;')
    edit(text, 'void ScummEngine_v7::drawBlastTexts() {',
         'void ScummEngine_v7::drawBlastTexts() {\n#include "scumm/hd_subtitle_test.inc"')
    edit(text, '\t\tBlastText &bt = _blastTextQueue[i];', '''\t\tBlastText &bt = _blastTextQueue[i];
        _hdSubtitleClipActive = bt.subtitle && _game.id == GID_CMI &&
            _hdScale > 1 && hdAspectRatio() == 169 && !hdInventoryOpen() && _currentRoom != 92;
        if (_hdSubtitleClipActive) bt.flags = (TextStyleFlags)(bt.flags | kStyleWordWrap);''')
    before = '\t\t\t// This is for the "narrow" paragraph wrapping type'
    edit(text, before, '''            if (_hdSubtitleClipActive) {
                const auto &presentation = HdRemaster::state();
                const bool cover = _screenWidth >= 864 ||
                    (ConfMan.hasKey("hd_wide_background_active") && ConfMan.getBool("hd_wide_background_active"));
                const HdAspect::Rect safe = HdSubtitleBounds::safeArea(presentation.drawableWidth,
                    presentation.drawableHeight, _screenWidth, cover);
                bt.rect = Common::Rect(safe.x, safe.y, safe.x + safe.w, safe.y + safe.h);
            }

''' + before)
    edit(text, '\t\tbt.rect.top += _screenTop;',
         '\t\t_hdSubtitleClipActive = false;\n\t\tbt.rect.top += _screenTop;')
    edit('engines/scumm/charset.cpp', '\t\t\tfc.xFraction = _hdXFraction;',
         '\t\t\tfc.xFraction = _hdXFraction;\n            if (_vm->_hdSubtitleClipActive) fc.clip = clipRect;')
    edit('engines/scumm/gfx.cpp',
         '\t\t\tif (_hdFontManager->drawChar(fi->fontSlot, fi->chr, _hdComposite, hdX, hdY, tR, tG, tB))',
         '''            // Preserve subtitle clipping through the HD atlas pass, including
            // glyph outlines and words that cannot be broken any further.
            Common::Rect textClip(hdW, hdH);
            if (!fi->clip.isEmpty()) {
                textClip = Common::Rect(fi->clip.left * hdW / MAX(1, visW),
                    fi->clip.top * hdH / MAX(1, visH), fi->clip.right * hdW / MAX(1, visW),
                    fi->clip.bottom * hdH / MAX(1, visH));
                textClip.clip(Common::Rect(hdW, hdH));
            }
            if (textClip.isEmpty()) continue;
            Graphics::Surface textTarget = _hdComposite.getSubArea(textClip);
\t\t\tif (_hdFontManager->drawChar(fi->fontSlot, fi->chr, textTarget,
                    hdX - textClip.left, hdY - textClip.top, tR, tG, tB))''')
