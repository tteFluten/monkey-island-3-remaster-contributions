"""60 Hz presentation stays independent of slower SCUMM simulation ticks."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class FramePacingTests(unittest.TestCase):
    def test_fractional_carry_late_frames_pause_and_clock_wrap(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'pacing.cpp'
            binary = Path(directory) / 'pacing'
            source.write_text(r'''
#include "hd_frame_pacer.h"
#include <cassert>
int main() {
    HdPresentation::FramePacer p;
    assert(p.due(0));
    for (unsigned int frame = 0; frame < 600; ++frame) {
        unsigned int now = frame * 1000 / 60;
        assert(p.due(now));
        p.presented(now);
        assert(!p.due(now));
        assert(p.next == (frame + 1) * 1000 / 60);
        assert(p.delay(now) == 16 || p.delay(now) == 17);
    }
    // A render hitch skips missed presentations instead of spinning to catch up.
    p.presented(10045);
    assert(p.next == 10050 && p.delay(10045) == 5);
    // Resuming from a long pause cannot cause a burst of old frames.
    p.presented(30000);
    assert(p.next == 30016 && !p.due(30000));
    // The unsigned platform clock can wrap after a long-running session.
    p.started = false;
    p.presented(0xfffffff8u);
    assert(p.next == 8 && p.delay(0xfffffff8u) == 16);
    assert(!p.due(7) && p.due(8));
    // The vsynced GPU path bypasses due(). Repeated early update attempts
    // must not push the CPU menu's first presentation into the future.
    HdPresentation::FramePacer transition;
    transition.presented(1000);
    for (int attempt = 0; attempt < 10000; ++attempt)
        transition.presented(1001);
    assert(transition.next == 1016 && transition.delay(1001) == 15);
    assert(transition.due(1016));
    transition.presented(1016);
    assert(transition.next == 1033);
    HdPresentation::SwapPacer swap;
    swap.presented(0);
    assert(swap.delay(5) == 7); // Render work comes before the deadline wait.
    for (int frame = 1; frame < 600; ++frame) {
        const double now = frame * 1000.0 / 60.0;
        swap.presented(now);
        assert(swap.next > now + 16 && swap.next < now + 17);
    }
    swap.presented(20000); // Suspension drops old deadlines.
    assert(swap.delay(20001) == 11);
    swap.presented(20028); // A missed display interval cannot trigger a burst.
    assert(swap.delay(20029) == 11);
    swap.reset(); assert(swap.delay(20030) == 0);
    // Slower game ticks coexist with 60 presentation updates each second.
    HdPresentation::FramePacer separate;
    int gameTicks = 0, presentations = 0;
    for (unsigned int now = 0; now < 1000; ++now) {
        if (now % 50 == 0) ++gameTicks;
        if (separate.due(now)) { ++presentations; separate.presented(now); }
    }
    assert(gameTicks == 20 && presentations == 60);
}
''')
            include = Path(__file__).resolve().parent / 'engine'
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(include), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
