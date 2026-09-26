"""Scene catalog and menu state tests; no game data or saves required."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from engine.patch_scene_jump import catalog, catalog_header, EXCLUDED, SCENES


class SceneJumpTests(unittest.TestCase):
    def test_catalog_matches_every_gameplay_manifest(self):
        entries = catalog()
        self.assertEqual([n for n, _ in entries], [n for n in range(1, 95) if n not in EXCLUDED])
        self.assertEqual(len(entries), 81)
        manifests = [json.loads(p.read_text())['scene'] for p in SCENES.glob('*.json')]
        names = {s['roomNumber']: s['name'] for s in manifests if 'roomNumber' in s}
        self.assertEqual(dict(entries), {n: names[n] for n in range(1, 95) if n not in EXCLUDED})

    def test_incomplete_duplicate_and_unsafe_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for n in range(1, 95):
                (root / f'{n}.json').write_text(json.dumps({'scene': {'roomNumber': n, 'name': f'room {n}'}}))
            (root / '9.json').write_text(json.dumps({'scene': {'roomNumber': 9, 'name': 'a "quote" \\ path'}}))
            self.assertIn(r'a \"quote\" \\ path', catalog_header(root))
            (root / 'duplicate.json').write_text((root / '9.json').read_text())
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                catalog(root)
            (root / 'duplicate.json').unlink()
            (root / '94.json').unlink()
            with self.assertRaisesRegex(ValueError, 'complete'):
                catalog(root)

    def test_native_selection_and_request_lifecycle(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scumm').mkdir()
            shutil.copy(Path(__file__).parent / 'engine/hd_scene_jump.h', root / 'scumm/hd_scene_jump.h')
            (root / 'rooms.h').write_text(catalog_header())
            (root / 'test.cpp').write_text(r'''
#include "rooms.h"
#include <cassert>
using namespace HdSceneJump;
int main() {
    State s;
    assert(!s.open && !s.pending);
    // Every room opens selected and visible, including the very last page.
    for (int i = 0; i < kCount; ++i) {
        s.show(kRooms[i].number, kRooms, kCount);
        assert(s.open && s.selected == i && s.first <= i && i < s.first + kRows);
        assert(s.first >= 0 && s.first <= kCount - kRows);
        s.choose(i, kRooms, kCount);
        assert(!s.open && !s.pending); // Same room does not restart scripts.
    }
    s.show(9, kRooms, kCount);
    s.move(-1, kCount); assert(s.selected == 0 && s.first == 0);
    s.move(kRows, kCount); assert(s.selected == kRows && s.first == 1);
    s.move(1000, kCount); assert(s.selected == kCount - 1 && s.first == kCount - kRows);
    s.move(-1000, kCount); assert(s.selected == 0 && s.first == 0);
    s.choose(-1, kRooms, kCount); s.choose(kCount, kRooms, kCount);
    assert(s.open && !s.pending);
    // Only the engine-loop consumer may execute a queued jump.
    s.choose(6, kRooms, kCount); assert(s.open && s.pending == 15);
    assert(s.takePending(true, 9) == 15);
    assert(!s.open && !s.pending && s.takePending(true, 9) == 0);
    // Busy state, a scripted room change, Escape and J all discard requests.
    s.show(9, kRooms, kCount); s.choose(6, kRooms, kCount);
    assert(s.takePending(false, 9) == 0 && !s.open);
    assert(s.takePending(true, 9) == 0);
    s.show(9, kRooms, kCount); s.choose(6, kRooms, kCount);
    assert(s.takePending(true, 11) == 0 && !s.open);
    s.show(9, kRooms, kCount); s.choose(6, kRooms, kCount); s.close();
    assert(s.takePending(true, 9) == 0);
    s.show(87, kRooms, kCount); assert(s.selected == 0);
    s.show(9, kRooms, 0); assert(!s.open && !s.pending);
    const Room small[] = {{9, "cannon"}, {15, "town"}};
    s.show(15, small, 2); s.move(50, 2); assert(s.selected == 1 && s.first == 0);
}
''')
            subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror', '-I', str(root),
                            str(root / 'test.cpp'), '-o', str(root / 'test')], check=True)
            subprocess.run([str(root / 'test')], check=True)

    def test_shared_jump_preserves_state_before_destination_scripts(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler required')
        # Compile the real transition against a small engine boundary. The
        # destination-script callback inspects state at the moment it is entered.
        bridge = (Path(__file__).parent / 'engine/playtest.inc').read_text()
        transition = bridge[bridge.index('bool ScummEngine::playtestReadyForJump'):bridge.index('void ScummEngine::refreshHDRoomBackground')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = r'''
#include "hd_scene_jump.h"
#include <cassert>
struct Actor { int _room = 9; };
struct Sound { int stopped = 0; void stopAllSounds() { ++stopped; } };
const int GID_CMI = 1;
struct Config { bool session = true; bool hasKey(const char *) { return session; } } ConfMan;
struct ScummEngine {
    bool paused = false, movie = false, inventoryOpen = false, _fullRedraw = false;
    int _saveLoadFlag = 0, _currentRoom = 9, _numActors = 2, ego = 1;
    struct Game { int id = GID_CMI; } _game;
    struct Script { int cutSceneStackPointer = 0; } vm;
    int inventory[3] = {12, 45, 98}, variables[3] = {4, 7, 13};
    Actor actor; Actor *_actors[2] = {nullptr, &actor};
    Sound sound; Sound *_sound = &sound;
    HdSceneJump::State _hdSceneJump;
    int VAR_EGO = 0, entered = 0;
    int VAR(int) { return ego; }
    bool isPaused() { return paused; }
    bool isSmushActive() { return movie; }
    bool hdInventoryOpen() { return inventoryOpen; }
    bool playtestReadyForJump();
    bool playtestJumpToRoom(int);
    void startScene(int room, Actor *actorArg, int object) {
        assert(inventory[0] == 12 && inventory[1] == 45 && inventory[2] == 98);
        assert(variables[0] == 4 && variables[1] == 7 && variables[2] == 13);
        assert(actor._room == room && !actorArg && object == 0);
        assert(sound.stopped && !_hdSceneJump.open && !_hdSceneJump.pending);
        entered = room;
    }
};
'''
            source += transition + r'''
int main() {
    ScummEngine vm;
    vm.paused = true;
    assert(!vm.playtestJumpToRoom(15) && vm.entered == 0 && vm.actor._room == 9);
    vm.paused = false;
    vm.movie = true; assert(!vm.playtestReadyForJump()); vm.movie = false;
    vm.inventoryOpen = true; assert(!vm.playtestReadyForJump()); vm.inventoryOpen = false;
    vm._saveLoadFlag = 1; assert(!vm.playtestReadyForJump()); vm._saveLoadFlag = 0;
    vm.vm.cutSceneStackPointer = 1; assert(!vm.playtestReadyForJump()); vm.vm.cutSceneStackPointer = 0;
    vm.VAR_EGO = 0xFF; assert(!vm.playtestReadyForJump()); vm.VAR_EGO = 0;
    vm.ego = 0; assert(!vm.playtestReadyForJump());
    vm.ego = vm._numActors; assert(!vm.playtestReadyForJump()); vm.ego = 1;
    vm._currentRoom = 87; assert(!vm.playtestReadyForJump());
    vm._currentRoom = 92; assert(!vm.playtestReadyForJump());
    vm._currentRoom = 0; assert(!vm.playtestReadyForJump()); vm._currentRoom = 9;
    ConfMan.session = false; assert(!vm.playtestReadyForJump()); ConfMan.session = true;
    vm._game.id = 2; assert(!vm.playtestReadyForJump()); vm._game.id = GID_CMI;
    assert(vm.playtestReadyForJump());
    assert(!vm.playtestJumpToRoom(0) && !vm.playtestJumpToRoom(95));
    assert(!vm.sound.stopped && !vm._fullRedraw);
    vm._hdSceneJump.open = true; vm._hdSceneJump.pending = 15;
    assert(vm.playtestJumpToRoom(15) && vm.entered == 15 && vm._fullRedraw);
    assert(vm.playtestJumpToRoom(61) && vm.entered == 61 && vm.sound.stopped == 2);
}
'''
            (root / 'test.cpp').write_text(source)
            subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(Path(__file__).parent / 'engine'), str(root / 'test.cpp'),
                            '-o', str(root / 'test')], check=True)
            subprocess.run([str(root / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
