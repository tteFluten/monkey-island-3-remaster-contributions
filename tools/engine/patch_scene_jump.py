"""Native J menu; embed scene names so no running workshop is required."""
import json
from pathlib import Path

EXCLUDED = frozenset(range(1, 9)) | {87, 88, 91, 92, 93}
SCENES = Path(__file__).resolve().parents[2] / 'data/scenes'


def catalog(directory=SCENES):
    rooms = {}
    for path in sorted(directory.glob('*.json')):
        scene = json.loads(path.read_text())['scene']
        number = scene.get('roomNumber')
        if number is None:
            continue
        if type(number) is not int or not 1 <= number <= 94 or number in rooms:
            raise ValueError(f'Invalid or duplicate room number in {path}')
        name = scene['name']
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'Missing room name in {path}')
        rooms[number] = name
    if set(rooms) != set(range(1, 95)):
        raise ValueError('Scene picker requires the complete COMI room catalog (1–94)')
    return [(number, name) for number, name in sorted(rooms.items()) if number not in EXCLUDED]


def catalog_header(directory=SCENES):
    rows = '\n'.join(f'    {{{number}, {json.dumps(name, ensure_ascii=True)}}},'
                     for number, name in catalog(directory))
    return ('// Generated from data/scenes; do not edit.\n'
            '#ifndef HD_SCENE_JUMP_ROOMS_H\n#define HD_SCENE_JUMP_ROOMS_H\n'
            '#include "scumm/hd_scene_jump.h"\nnamespace HdSceneJump {\n'
            'static const Room kRooms[] = {\n' + rows + '\n};\n'
            'const int kCount = sizeof(kRooms) / sizeof(kRooms[0]);\n}\n#endif\n')


def patch(root, edit):
    here = Path(__file__).parent
    for name in ('hd_scene_jump.h', 'hd_scene_jump.inc'):
        (root / 'engines/scumm' / name).write_bytes((here / name).read_bytes())
    (root / 'engines/scumm/hd_scene_jump_rooms.h').write_text(catalog_header())
    edit('engines/scumm/scumm.h', '#include "common/keyboard.h"',
         '#include "common/keyboard.h"\n#include "scumm/hd_scene_jump.h"')
    edit('engines/scumm/scumm.h', '\tvoid playtestTick();', '''\tvoid playtestTick();
    bool playtestReadyForJump();
    bool playtestJumpToRoom(int room);
    bool handleHDSceneJumpEvent(const Common::Event &event);
    void drawHDSceneJumpPanel();
    Common::Point hdSceneJumpPosition() const;
    HdSceneJump::State _hdSceneJump;
    bool _hdSceneJumpKeys[Common::KEYCODE_LAST] = {};
    unsigned _hdSceneJumpButtons = 0;''')
    edit('engines/scumm/input.cpp', 'void ScummEngine::parseEvent(Common::Event event) {',
         'void ScummEngine::parseEvent(Common::Event event) {\n\tif (handleHDSceneJumpEvent(event)) return;')
    edit('engines/scumm/gfx.cpp', '#include "scumm/hd_color_grade.inc"',
         '#include "scumm/hd_color_grade.inc"\n#include "scumm/hd_scene_jump.inc"')
    edit('engines/scumm/gfx.cpp', '#include "scumm/hd_scene_look.h"',
         '#include "scumm/hd_scene_look.h"\n#include "scumm/hd_scene_jump_rooms.h"')
    edit('engines/scumm/gfx.cpp', '\tdrawHDLookPanel();',
         '\tdrawHDLookPanel();\n\tdrawHDSceneJumpPanel();')
