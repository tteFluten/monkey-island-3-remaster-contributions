"""60 Hz presentation and independent HD pointer updates; original game timing."""
from pathlib import Path


def patch(root, edit):
    scumm = 'engines/scumm/scumm.cpp'
    path = root / scumm
    text = path.read_text()
    start = text.find('\t\t\t// HD mode frame limiter: limit to ~30fps')
    if start != -1:
        end = text.index('\n\t\t}', start)
        text = text[:start] + '\t\t\t// Presentation is paced independently in waitForTimer().\n' + text[end:]
        path.write_text(text)
    header = 'engines/scumm/scumm.h'
    edit(header, '#include "engines/engine.h"',
         '#include "scumm/hd_frame_pacer.h"\n#include "engines/engine.h"')
    edit(header, '\tvoid renderHDComposite();',
         '\tvoid renderHDComposite();\n\tvoid presentHDCursor();\n\tCommon::Rect _hdPresentedCursor;\n\tHdPresentation::FramePacer _hdPresentationPacer;')
    edit(scumm, '\tuint32 msecDelay = getIntegralTime(quarterFrames * (1000 / getTimerFrequency()));',
         '\tconst bool hdPresentation = _hdScale > 1 && _hdBackgroundSurface.getPixels() && !isSmushActive();\n\tuint32 msecDelay = getIntegralTime(quarterFrames * (1000 / getTimerFrequency()));')
    # This update is in waitForTimer, not SMUSH or game logic.
    if 'if (!hdPresentation || _hdPresentationPacer.due(cur))' not in path.read_text():
        edit(scumm, '\t\t_system->updateScreen();\n\t\tcur = _system->getMillis();', '''
        cur = _system->getMillis();
        if (!hdPresentation || _hdPresentationPacer.due(cur)) {
            if (hdPresentation) presentHDCursor();
            _system->updateScreen();
            if (hdPresentation) _hdPresentationPacer.presented(cur);
        }
        cur = _system->getMillis();''')
    edit(scumm, '\t\t_system->delayMillis(MIN<uint32>(10, endTime - cur));', '''
        uint32 sleepMs = MIN<uint32>(10, endTime - cur);
        if (hdPresentation) sleepMs = MIN(sleepMs, _hdPresentationPacer.delay(cur));
        _system->delayMillis(sleepMs);''')
    edit(scumm, 'if (hdPresentation) _hdPresentationPacer.presented(cur);', '''if (hdPresentation) {
                _hdPresentationPacer.presented(cur);
                static uint32 started = 0, frames = 0;
                if (!frames) started = cur;
                if (++frames == 121) {
                    hdPrintf("HD-PRESENT: updates=120 elapsed=%ums Hz=%.1f", cur - started,
                             cur > started ? 120000.0 / (cur - started) : 0.0);
                    frames = 0;
                }
            }''')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '\t// Cursor already composited in the single screen copy above.',
         '\t// Cursor already composited in the single screen copy above.\n\t// The clean HD scene now stays cursor-free for independent presentation.\n\tpresentHDCursor();')
    # Other features insert includes at this same anchor. Check the include
    # itself so a subsequent patch run cannot duplicate its definitions.
    if '#include "scumm/hd_cursor_present.inc"' not in (root / gfx).read_text():
        edit(gfx, 'void ScummEngine::renderHDComposite() {',
             '#include "scumm/hd_cursor_present.inc"\n\nvoid ScummEngine::renderHDComposite() {')
    # The exact-pose manager already loads the chosen character pack. Avoid
    # prefetching the unused legacy pack on every frame in these rooms.
    edit(gfx, '\t\tif (_hdCostumeManager && _hdCostumeManager->isEnabled()) {\n\t\t\tfor (int ai = 0; ai < _numActors && pfBudget;',
         '\t\tif (!quiverActive && _hdCostumeManager && _hdCostumeManager->isEnabled()) {\n\t\t\tfor (int ai = 0; ai < _numActors && pfBudget;')
    for name in ('hd_frame_pacer.h', 'hd_cursor_present.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
