"""Live authoring overlay and resource-independent walk/water overrides."""
from pathlib import Path
from scene_masks_defaults import header


def patch(root, edit):
    here = Path(__file__).parent
    # Parse standard-library headers before ScummVM's forbidden libc macros.
    edit('common/scummsys.h', '#include "common/forbidden.h"', '#ifdef __cplusplus\n#include <vector>\n#include <map>\n#include <string>\n#include <algorithm>\n#include <cmath>\n#endif\n#include "common/forbidden.h"')
    edit('engines/scumm/actor.h', '\tvoid stopActorMoving();', '\tvoid stopActorMoving();\n    Common::Point hdMasksDestination() const { return _walkdata.dest; }\n    int hdMasksDirection() const { return _walkdata.destdir; }')
    for name in ('hd_sprite_frames.h', 'hd_actor_head.h', 'hd_scene_masks.h', 'hd_scene_masks_io.h'):
        (root / 'common' / name).write_bytes((here / name).read_bytes())
    (root / 'common/hd_scene_masks_defaults.h').write_text(header())
    for name in ('hd_animation_masks_editor.inc', 'hd_sprite_frames_editor.inc', 'hd_scene_animations_editor.inc', 'hd_actor_head_editor.inc', 'hd_scene_masks_boxes.inc', 'hd_scene_masks_editor.inc', 'hd_scene_masks_foreground.inc'):
        (root / 'engines/scumm' / name).write_bytes((here / name).read_bytes())
    edit('engines/scumm/scumm.h', '\tvoid playtestTick();', '''\tvoid playtestTick();
    void hdMasksSync();
    const signed char *hdMasksForegroundRaster(int plane,int width,int height,int scale);
    bool hdMasksForegroundBypass(int plane);
    byte *hdMasksActorMask(int actor,bool hitTest,int x,int y,int z);
    void hdMasksRedrawActors();
    void hdMasksTraceForeground(HdMasks::Document &next);
    int hdMasksBoxCount(int count);
    Box *hdMasksExtraBox(int id);
    bool hdMasksCoordinates(int id, BoxCoords &out);
    bool hdMasksDisabled(int id);
    int hdMasksNextBox(int from, int to);
    bool hdMasksConnected(int from, int to);
    void hdMasksTrimExtras(unsigned count);
    bool hdMasksAvailable();
    void hdHeadTick();
    void hdHeadAction(int action);
    bool handleHDHeadEvent(const Common::Event &event);
    void drawHDHead(Graphics::Surface &surface);
    bool hdMasksApply(const HdMasks::Document &, bool history);
    void hdMasksTick();
    void hdMasksAction(int action);
    bool handleHDMasksEvent(const Common::Event &event);
    void hdSpriteFrameAction(int action);
    void drawHDSpriteOnion(Graphics::Surface &surface,bool head);
    void hdAnimationMaskAction(int action);
    bool handleHDAnimationMaskEvent(const Common::Event &event);
    void drawHDAnimationMask(Graphics::Surface &surface);
    void hdAnimationsTick();
    void hdAnimationsAction(int action);
    bool handleHDAnimationsEvent(const Common::Event &event);
    void drawHDAnimations(Graphics::Surface &surface);
    void drawHDMasks();''')
    edit('engines/scumm/scumm.h', '#include "common/keyboard.h"', '#include "common/keyboard.h"\n#include "common/hd_scene_masks.h"')
    boxes = 'engines/scumm/boxes.cpp'
    edit(boxes, '#include "scumm/scumm.h"', '#define FORBIDDEN_SYMBOL_ALLOW_ALL\n#include "common/hd_scene_masks_io.h"\n#include "common/hd_scene_masks_defaults.h"\n#include "common/hd_plunder_map.h"\n#include "common/hd_voodoo_exterior.h"\n#include "common/config-manager.h"\n#include "scumm/scumm.h"')
    edit(boxes, '#define BOX_DEBUG 0', '#define BOX_DEBUG 0\n#include "scumm/hd_scene_masks_boxes.inc"')
    edit(boxes, 'return (byte)READ_LE_UINT32(ptr);', 'return (byte)hdMasksBoxCount(READ_LE_UINT32(ptr));')
    edit(boxes, 'Box *ScummEngine::getBoxBaseAddr(int box) {', 'Box *ScummEngine::getBoxBaseAddr(int box) {\n    if (_game.version == 8) { Box *extra = hdMasksExtraBox(box); if (extra) return extra; }')
    edit(boxes, 'BoxCoords ScummEngine::getBoxCoordinates(int boxnum) {', 'BoxCoords ScummEngine::getBoxCoordinates(int boxnum) {\n    BoxCoords authored; if (_game.version == 8 && hdMasksCoordinates(boxnum, authored)) return authored;')
    edit(boxes, 'return (byte) FROM_LE_32(ptr->v8.flags);', 'return (byte) FROM_LE_32(ptr->v8.flags) | (hdMasksDisabled(box) ? kBoxInvisible : 0);')
    edit(boxes, 'int ScummEngine::getNextBox(byte from, byte to) {', 'int ScummEngine::getNextBox(byte from, byte to) {\n    if (_game.version == 8) { int next = hdMasksNextBox(from, to); if (next != -2) return next; }')
    # Script-triggered rebuilds still use the effective geometry. Allocate for
    # the actual count and worst-case compressed output, never a fixed 2 KB.
    path = root / boxes
    text = path.read_text().replace('const uint8 boxSize = (_game.version == 0) ? num : 64;', 'const int boxSize = MAX(1, num);')
    text = text.replace('byte *matrixStart = _res->createResource(rtMatrix, 1, BOX_MATRIX_SIZE);', 'const int matrixCapacity = num * (1 + 3 * num) + 1;\n\tbyte *matrixStart = _res->createResource(rtMatrix, 1, matrixCapacity);').replace('matrixStart + BOX_MATRIX_SIZE', 'matrixStart + matrixCapacity')
    path.write_text(text)
    edit(boxes, 'void ScummEngine::createBoxMatrix() {', '''void ScummEngine::createBoxMatrix() {
    // Rebuild script-owned routing from native resources; overrides remain separate.
    struct NativeScope { bool before; NativeScope():before(hdMaskNative){hdMaskNative=true;} ~NativeScope(){hdMaskNative=before;} } nativeScope;''')
    edit('engines/scumm/gfx.cpp', '#include "scumm/hd_scene_jump_rooms.h"', '#include "scumm/hd_scene_jump_rooms.h"\n#include "common/hd_scene_masks_io.h"\n#include "scumm/boxes.h"')
    edit('engines/scumm/gfx.cpp', '#include "scumm/hd_scene_jump.inc"', '#include "scumm/hd_scene_jump.inc"\n#include "scumm/hd_scene_masks_foreground.inc"\n#include "scumm/hd_scene_masks_editor.inc"')
    edit('engines/scumm/gfx.cpp', '\tdrawHDSceneJumpPanel();', '\tdrawHDSceneJumpPanel();\n\tdrawHDMasks();')
    edit('engines/scumm/scumm.cpp', '\tplaytestTick();', '\tplaytestTick();\n    hdMasksTick();')
    edit('engines/scumm/input.cpp', 'void ScummEngine::parseEvent(Common::Event event) {', 'void ScummEngine::parseEvent(Common::Event event) {\n    if (handleHDMasksEvent(event)) return;')
    edit('engines/scumm/room.cpp', 'void ScummEngine::resetRoomSubBlocks() {', 'void ScummEngine::resetRoomSubBlocks() {\n    HdMasks::state().room = -1; HdRemaster::state().maskVisible = HdRemaster::state().maskEditing = false;')
    edit('engines/scumm/saveload.cpp', 'bool ScummEngine::loadState(int slot, bool compat, Common::String &filename) {', 'bool ScummEngine::loadState(int slot, bool compat, Common::String &filename) {\n    HdMasks::state().room = -1; HdMasks::state().drag = HdMasks::state().pending = false;')
    # Capture raw presentation coordinates before scene-specific pointer mapping.
    edit('backends/graphics/sdl/sdl-graphics.cpp', '\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);', '''\tmouse.y = (int)(mouse.y * dpiScale + 0.5f);
    if (!_overlayInGUI && HdRemaster::state().maskVisible) {
        auto &m = HdMasks::state(); const auto &r = _activeArea.drawRect;
        const double width = HdRemaster::state().viewportWidth > 640 ? HdRemaster::state().viewportWidth : 854;
        const double h = r.height(), w = h * width / 480;
        if (h > 0) { m.rawX = (mouse.x-r.left-(r.width()-w)/2)*width/w; m.rawY = (mouse.y-r.top)*480/h; }
        if (HdRemaster::state().maskEditing) { setMousePosition(mouse.x,mouse.y); showSystemMouseCursor(true); return true; }
    }''')
    # Existing panels close the mask overlay on entry, including Test mode.
    edit('engines/scumm/hd_scene_jump.inc', 'hdColorGradeState().panel = false;', 'hdColorGradeState().panel = false; HdMasks::state().open = false;')
    edit('engines/scumm/hd_color_grade.inc', 'st.panel = true; st.row = 0;', 'HdMasks::state().open = false; st.panel = true; st.row = 0;')
    edit('engines/scumm/hd_color_grade.inc', 'st.panel = !st.panel;', 'HdMasks::state().open = false; st.panel = !st.panel;')
    # Additional overlay drawn after GPU scene effects, before the cursor.
    edit('backends/graphics/opengl/opengl-graphics.cpp', '\t// Second step: Draw the cursor', '    hdRemasterGL().drawMasks(_pipeline, _targetBuffer, _gameDrawRect, _overlayVisible);\n\t// Second step: Draw the cursor')
    edit('engines/scumm/scumm.h', 'uint16 _extraBoxFlags[65];', 'uint16 _extraBoxFlags[255];')
    edit(boxes, 'assert(box >= 0 && box < 65);', 'assert(box >= 0 && box < 255);')
    edit('engines/scumm/scumm.cpp', '#include "common/formats/json.h"', '#include "common/formats/json.h"\n#include "common/hd_scene_masks_io.h"')
    edit('engines/scumm/playtest.inc', '\tCommon::String temporary = directory + "/status.tmp";', r'''    if (ConfMan.hasKey("hd_aspect_test_input") && ConfMan.getBool("hd_aspect_test_input")) {
        auto &m=HdMasks::state(); auto *d=m.draft();
        status.deleteLastChar();
        status += Common::String::format(",\"maskEditor\":{\"open\":%s,\"visible\":%s,\"test\":%s,\"water\":%s,\"foreground\":%s,\"plane\":%d,\"planes\":%d,\"bypass\":%s,\"connections\":%s,\"dirty\":%s,\"selected\":%d,\"node\":%d,\"pointerX\":%d,\"pointerY\":%d,\"error\":%s,\"document\":",
            m.open?"true":"false",HdRemaster::state().maskVisible?"true":"false",m.test?"true":"false",m.waterTab?"true":"false",m.foregroundTab?"true":"false",m.plane,m.planeCount,m.bypassForeground?"true":"false",m.showConnections?"true":"false",d&&d->dirty?"true":"false",m.selected,m.node,m.rawX,m.rawY,Common::JSONValue(m.error.c_str()).stringify().c_str());
        if(d){auto *value=HdMasks::encode(d->live);status+=value->stringify();delete value;}else status+="null";
        status += Common::String::format(",\"animationMaskEdit\":%s,\"panelOpacity\":%d",m.animationMaskEdit?"true":"false",m.panelOpacity);
        status += Common::String::format(",\"animations\":%s,\"animationSelected\":%s,\"animationDrag\":%s,\"animationVisuals\":[",m.animationsTab?"true":"false",Common::JSONValue(m.animationSelected.c_str()).stringify().c_str(),m.animationDrag?"true":"false");
        for(unsigned i=0;i<m.animationVisuals.size();++i){auto &v=m.animationVisuals[i];auto p=HdMasks::effectiveAnimation(v.key,v.cel);if(i)status+=",";
            status+=Common::String::format("{\"key\":%s,\"actor\":%d,\"costume\":%d,\"cel\":%d,\"left\":%.4f,\"top\":%.4f,\"width\":%.4f,\"height\":%.4f,\"x\":%.4f,\"y\":%.4f}",Common::JSONValue(v.key.c_str()).stringify().c_str(),v.actor,v.costume,v.cel,v.x,v.y,v.w,v.h,p.x,p.y);}
        status+="]";
        auto maskVisual=HdMasks::animationEditVisual();auto maskShift=HdMasks::effectiveAnimation(maskVisual.key,maskVisual.cel);
        auto *maskFrame=HdSprites::get("animation:"+m.animationSelected,m.animationFrame);
        status+=Common::String::format(",\"animationMaskVisual\":{\"left\":%.4f,\"top\":%.4f,\"width\":%.4f,\"height\":%.4f,\"cel\":%d,\"mirror\":%s}",maskVisual.x+maskShift.x,maskVisual.y+maskShift.y,maskVisual.w,maskVisual.h,maskVisual.cel,maskFrame&&maskFrame->mirror?"true":"false");
        auto &head=HdHead::state();auto view=m.headTab?HdHead::editVisual():head.visual;auto offset=HdHead::poseOffset(view.pack,view.costume,view.cel);
        bool frameMode=m.headTab?head.frameMode:m.animationFrameMode;int frame=m.headTab?head.frame:m.animationFrame;
        std::string frameGroup=m.headTab?"head:"+head.visual.key:"animation:"+m.animationSelected;
        const std::string frameKey=m.headTab?HdHead::key(view.pack,view.costume,frame):HdMasks::animationFrameKey(m.animationSelected,frame);
        auto hv=HdHead::get(head.live,frameKey);auto av=d?HdMasks::animationOffset(d->live,frameKey):HdMasks::Point();
        status+=Common::String::format(",\"spriteFrames\":{\"onion\":%s,\"frameMode\":%s,\"frame\":%d,\"frameKey\":%s,\"x\":%.4f,\"y\":%.4f,\"captured\":[",m.onion?"true":"false",frameMode?"true":"false",frame,Common::JSONValue(frameKey.c_str()).stringify().c_str(),m.headTab?hv.x:av.x,m.headTab?hv.y:av.y);
        auto captured=HdSprites::cels(frameGroup);for(unsigned i=0;i<captured.size();++i){if(i)status+=",";status+=Common::String::format("%d",captured[i]);}status+="]}";
        status += Common::String::format(",\"head\":%s,\"headDebug\":{\"valid\":%s,\"dirty\":%s,\"drag\":%s,\"original\":%s,\"costume\":%d,\"cel\":%d,\"mirror\":%s,\"key\":%s,\"x\":%.4f,\"y\":%.4f,\"left\":%.4f,\"top\":%.4f,\"width\":%.4f,\"height\":%.4f,\"sourceWidth\":%.4f,\"sourceHeight\":%.4f}",
            m.headTab?"true":"false",view.valid?"true":"false",head.dirty()?"true":"false",head.drag?"true":"false",head.original?"true":"false",view.costume,view.cel,view.mirror?"true":"false",Common::JSONValue(view.key.c_str()).stringify().c_str(),offset.x,offset.y,view.head.x,view.head.y,view.head.w,view.head.h,view.sourceWidth,view.sourceHeight);
        status += Common::String::format(",\"moreOptions\":%s,\"controls\":[",m.moreOptions?"true":"false");
        for(unsigned i=0;i<m.controls.size();++i){auto &c=m.controls[i];if(i)status+=",";status+=Common::String::format("{\"slot\":%d,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}",c.slot,c.x,c.y,c.w,c.h);}
        status += Common::String::format("],\"clipPrecision\":{\"zoom\":%.2f,\"focusX\":%.4f,\"focusY\":%.4f,\"step\":%.2f,\"fill\":%d,\"outline\":%s,\"pan\":%s,\"insert\":%s}}}",m.clipView.zoom,m.clipView.focus.x,m.clipView.focus.y,m.clipStep,m.clipFill,m.clipOutline?"true":"false",m.clipPan?"true":"false",m.clipInsert?"true":"false");
    }
\tCommon::String temporary = directory + "/status.tmp";'''.replace('\\tCommon', '\tCommon'))
    # Added IDs are an authoring concern. Save ordinary resource IDs and an idle
    # route, without changing the actor's live movement or the save format.
    edit('engines/scumm/actor.cpp', 'void Actor::saveLoadWithSerializer(Common::Serializer &s) {', '''void Actor::saveLoadWithSerializer(Common::Serializer &s) {
    auto maskSyncBox = [&](byte &id, int version) {
        byte stored=id;
        auto &m=HdMasks::state();auto *d=m.draft();
        if(s.isSaving() && _vm->_game.id==GID_CMI && _room==m.room && d && d->walkChanged) {
            const auto *box=HdMasks::find(d->live,id);
            if(box && id>=d->base.boxes.size())stored=box->parent;
        }
        s.syncAsByte(stored, version);
        if(s.isLoading())id=stored;
    };''')
    actor = root / 'engines/scumm/actor.cpp'
    text = actor.read_text()
    for field in ('_walkbox', '_walkdata.destbox', '_walkdata.curbox'):
        text = text.replace(f's.syncAsByte({field}, VER(8));', f'maskSyncBox({field}, VER(8));')
    text = text.replace('s.syncAsByte(_moving, VER(8));', '''{
        byte moving=_moving;auto &m=HdMasks::state();auto *d=m.draft();
        if(s.isSaving() && _vm->_game.id==GID_CMI && _room==m.room && d && d->walkChanged)moving=0;
        s.syncAsByte(moving,VER(8));if(s.isLoading())_moving=moving;
    }''')
    actor.write_text(text)
    # Synthetic test keys carry their own modifiers; desktop state is unrelated.
    events = root / 'backends/events/sdl/sdl2-events.cpp'
    text = events.read_text()
    for fn in ('handleKeyDown', 'handleKeyUp'):
        start = text.index(f'bool SdlEventSource::{fn}(')
        end = text.find('\nbool ', start + 1)
        if end < 0: end = len(text)
        part = text[start:end].replace('SDLModToOSystemKeyFlags(SDL_GetModState(), event);', 'SDLModToOSystemKeyFlags(getenv("MI3_ENGINE_TEST_INPUT") && ev.key.windowID == 0 ? (SDL_Keymod)ev.key.keysym.mod : SDL_GetModState(), event);')
        text = text[:start] + part + text[end:]
    events.write_text(text)
    edit('backends/graphics/opengl/opengl-graphics.cpp', 'bool drawCursor = _cursorVisible && _cursor;', 'bool drawCursor = _cursorVisible && _cursor && !HdRemaster::state().maskEditing;')

    akos = root / 'engines/scumm/akos.cpp'
    text = akos.read_text().replace('_vm->getMaskBuffer(', '_vm->hdMasksActorMask(_actorID, _actorHitMode, ')
    akos.write_text(text)
