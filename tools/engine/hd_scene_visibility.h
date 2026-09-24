#ifndef SCUMM_HD_SCENE_VISIBILITY_H
#define SCUMM_HD_SCENE_VISIBILITY_H

namespace HdSceneVisibility {
// Match COMI's drawRoomObjects/drawRoomObject rules. Loaded FLOBJs such as
// the inventory panel are resources, not evidence that their UI is open.
// Their native blast/verb passes own drawing them on screen.
template<class Object>
bool roomObject(const Object *objects, int count, int index) {
    if (index <= 0 || index >= count || objects[index].obj_nr <= 0 ||
        !(objects[index].state & 15)) return false;
    for (int depth = 0; depth < count; ++depth) {
        const Object &object = objects[index];
        if (!object.parent) return object.fl_object_index == 0;
        if (object.parent <= 0 || object.parent >= count) return false;
        if ((objects[object.parent].state & 15) != object.parentstate) return false;
        index = object.parent;
    }
    return false;
}

// Extracted COMI object PNGs enumerate IMAG images from zero. The original
// engine selects those same images with states starting at one.
inline int imageIndex(int state) { return state > 0 ? state - 1 : -1; }

// These costumes are sparse, palette-dependent ripples. The generated PNGs
// contain an opaque gray matte and baked colors; retain the original animated
// transparent effect over the HD background, including native depth/palette.
inline bool nativePaletteEffect(int room, int costume) {
    return (room == 14 && (costume == 73 || costume == 74)) ||
           (room == 15 && (costume == 80 || costume == 83));
}
}
#endif
