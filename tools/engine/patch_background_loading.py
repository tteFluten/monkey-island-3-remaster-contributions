"""Cache and predecode room paintings and their widescreen/reflection sources."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'common/hd_background_cache.h').write_bytes((here / 'hd_background_cache.h').read_bytes())
    (root / 'engines/scumm/hd_background_prefetch.inc').write_bytes((here / 'hd_background_prefetch.inc').read_bytes())
    manager = 'engines/scumm/hd_asset_manager.cpp'
    # SDL/libc++ declarations must precede ScummVM's forbidden-symbol macros.
    edit(manager, '#include "scumm/hd_asset_manager.h"',
         '#include <SDL_thread.h>\n#include <SDL_atomic.h>\n#include <list>\n#include <deque>\n\n#include "scumm/hd_asset_manager.h"')
    for source in (manager, 'engines/scumm/scumm.cpp'):
        edit(source, '#include "common/config-manager.h"',
             '#include "common/config-manager.h"\n#include "common/hd_background_cache.h"')
    edit('backends/graphics/opengl/opengl-graphics.cpp', '#include "common/fs.h"',
         '#include "common/fs.h"\n#include "common/hd_background_cache.h"')
    edit('engines/scumm/hd_asset_manager.h', '\tbool loadBackground(int room, Graphics::Surface &surf);',
         '\tbool loadBackground(int room, Graphics::Surface &surf);\n\tvoid prefetchBackground(int room);')
    edit(manager, 'HDAssetManager::~HDAssetManager() {',
         'HDAssetManager::~HDAssetManager() {\n    HdBackground::cache().shutdown();')
    edit(manager, 'void HDAssetManager::setHDPath(const Common::String &path) {',
         'void HDAssetManager::setHDPath(const Common::String &path) {\n    HdBackground::cache().invalidate();')
    edit(manager, 'bool HDAssetManager::loadBackground(int room, Graphics::Surface &surf) {',
         '''#include "scumm/hd_background_prefetch.inc"

bool HDAssetManager::loadBackground(int room, Graphics::Surface &surf) {
    if (ConfMan.hasKey("playtest_session")) {
        if (_hdPath.empty() || !_bgFiles.contains(room)) return false;
        prefetchBackground(room);
        const bool loaded = HdBackground::cache().load(_bgFiles[room], surf);
        HdBackground::cache().step();
        return loaded;
    }''')
    edit('engines/scumm/room.cpp', 'void ScummEngine::startScene(int room, Actor *a, int objectNr) {',
         '''void ScummEngine::startScene(int room, Actor *a, int objectNr) {
    if (_game.id == GID_CMI && _hdAssetManager)
        _hdAssetManager->prefetchBackground(room);''')
    edit('engines/scumm/scumm.cpp', '            if (_hdQuiverManager) _hdQuiverManager->prefetchRoomStep(_currentRoom);',
         '''            HdBackground::cache().step();
            if (_hdQuiverManager) _hdQuiverManager->prefetchRoomStep(_currentRoom);''')
