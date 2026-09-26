"""Replace known ambient water sprites with masked, presentation-rate shading."""
from pathlib import Path


def patch(root, edit):
    here = Path(__file__).parent
    (root / 'common/hd_water.h').write_bytes((here / 'hd_water.h').read_bytes())
    (root / 'engines/scumm/hd_water_surface.inc').write_bytes((here / 'hd_water_surface.inc').read_bytes())
    edit('engines/scumm/gfx.cpp', 'namespace Scumm {',
         'namespace Scumm {\n#include "scumm/hd_water_surface.inc"')
    # All successful replacements are in quiverPoses, including the empty
    # water poses. The legacy pack must not paint those PNGs back over the GPU.
    edit('engines/scumm/gfx.cpp',
         'if (HdSceneVisibility::nativePaletteEffect(_currentRoom, a->_costume)) continue;',
         '''if (HdSceneVisibility::nativePaletteEffect(_currentRoom, a->_costume)) continue;
            bool shaderWater = false;
            for (const auto &pose : quiverPoses)
                if (pose.actor == a && pose.water) { shaderWater = true; break; }
            if (shaderWater) continue;''')
    edit('engines/scumm/scumm.cpp', 'void ScummEngine::pauseEngineIntern(bool pause) {',
         'void ScummEngine::pauseEngineIntern(bool pause) {\n    HdRemaster::state().waterPaused = pause;')
    edit('engines/scumm/gfx.cpp',
         'const bool interpolation = _hdInterpolating, hadDof = remaster.dof;',
         'const bool interpolation = _hdInterpolating, hadDof = remaster.dof, hadWater = remaster.water, hadWaterSurface = remaster.waterSurface;')
    edit('engines/scumm/gfx.cpp', 'remaster.active = remaster.ui = true; remaster.dof = hadDof;',
         'remaster.active = remaster.ui = true; remaster.dof = hadDof; remaster.water = hadWater; remaster.waterSurface = hadWaterSurface;')
    # No eager PNG decoding for ambient water in GPU mode. Compatibility mode
    # retains the existing loader and all fallback artwork.
    manager = 'engines/scumm/hd_costume_manager.h'
    edit(manager, '#include "scumm/hd_scene_visibility.h"',
         '#include "scumm/hd_scene_visibility.h"\n#include "common/hd_remaster.h"\n#include "common/config-manager.h"')
    edit(manager, 'if (*owner == room && !HdSceneVisibility::nativePaletteEffect(room, it->_key))',
         '''if (*owner == room && !HdSceneVisibility::nativePaletteEffect(room, it->_key) &&
                    !(HdRemaster::state().active && HdWater::ambient(room, it->_key) &&
                      (!ConfMan.hasKey("hd_water_shader") || ConfMan.getBool("hd_water_shader"))))''')
    edit('engines/scumm/gfx.cpp',
         'actor->_costume && !HdSceneVisibility::nativePaletteEffect(_currentRoom, actor->_costume))',
         '''actor->_costume && !HdSceneVisibility::nativePaletteEffect(_currentRoom, actor->_costume) &&
                        !(remaster.water && HdWater::ambient(_currentRoom, actor->_costume)))''')

    # Cannon and waterline defer future HD animation frames, including scripted
    # poses not used until later. Decode them off the engine thread, using the
    # existing exact-pack batch decoder. Keep the rollout explicit in one place.
    (root / 'engines/scumm/hd_room_prefetch.inc').write_bytes((here / 'hd_room_prefetch.inc').read_bytes())
    edit(manager, '    void preloadRoomCostumes(int room) {', '''private:
    struct RoomPrefetch;
    RoomPrefetch *_roomPrefetch = nullptr;
    void stopRoomPrefetch();
public:
    static bool usesAsyncRoomLoading(int room) { return room == 9 || room == 11; }
    void queueRoomCostume(int room, int costume);
    void queueRoomCostumes(int room);
    void prefetchRoomStep(int room);
    void preloadRoomCostumes(int room) {''')
    implementation = 'engines/scumm/hd_costume_manager.cpp'
    edit(implementation, 'HdCostumeManager::~HdCostumeManager() {',
         'HdCostumeManager::~HdCostumeManager() {\n    stopRoomPrefetch();')
    edit(implementation, 'int HdCostumeManager::preloadCostumeRange(',
         '#include "scumm/hd_room_prefetch.inc"\n\nint HdCostumeManager::preloadCostumeRange(')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '''            // Decode the selected visible costumes during room loading. This
            // uses the existing bounded cache and batch decoder; no unrelated
            // room textures are decoded on the presentation deadline.''', '''            // Cannon and waterline queue future poses asynchronously.
            // Other rooms retain their existing bounded-cache prewarm.''')
    edit(gfx, '''            if (playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())
                _hdQuiverManager->preloadRoomCostumes(_currentRoom);''', '''            if (!HdCostumeManager::usesAsyncRoomLoading(_currentRoom) && playtestExactRoom(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())
                _hdQuiverManager->preloadRoomCostumes(_currentRoom);''')
    edit(gfx, '                        _hdQuiverManager->preloadCostumeRange(actor->_costume, 0, 65535);', '''                    {
                        if (HdCostumeManager::usesAsyncRoomLoading(_currentRoom)) _hdQuiverManager->queueRoomCostume(_currentRoom, actor->_costume);
                        else _hdQuiverManager->preloadCostumeRange(actor->_costume, 0, 65535);
                    }''')
    edit(gfx, '\t\t\thdPrintf("ROOM CHANGE: entering room %d, %d objects:", _currentRoom, _numLocalObjects);', '''            // Visible costumes go first; later scripted poses follow them.
            if (HdCostumeManager::usesAsyncRoomLoading(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled())
                _hdQuiverManager->queueRoomCostumes(_currentRoom);
\t\t\thdPrintf("ROOM CHANGE: entering room %d, %d objects:", _currentRoom, _numLocalObjects);''')
    edit(gfx, '''\t\t\tint prewarmCostumes = 0;
\t\t\tif (_hdCostumeManager && _hdCostumeManager->isEnabled()) {''', '''\t\t\tint prewarmCostumes = 0;
            // The selected exact pack does not draw legacy sprites.
\t\t\tif (!(HdCostumeManager::usesAsyncRoomLoading(_currentRoom) && _hdQuiverManager && _hdQuiverManager->isEnabled()) &&
                _hdCostumeManager && _hdCostumeManager->isEnabled()) {''')
    # Poll before presentation, even for a static scene. A pending job returns
    # immediately; only completed jobs join and transfer their pixel storage.
    edit('engines/scumm/scumm.cpp',
         '            if (hdPresentation) { presentHDMotion(); presentHDCursor(); }', '''            if (_hdQuiverManager) _hdQuiverManager->prefetchRoomStep(_currentRoom);
            if (hdPresentation) { presentHDMotion(); presentHDCursor(); }''')
