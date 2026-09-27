"""Options book (room 92): HD painting behind the Save/Load spread, and the
options spread re-laid out for the 16:9 book (see hd_book_layout.h)."""
from pathlib import Path


def patch(root, edit):
    for name in ('hd_book.inc', 'hd_book_layout.h', 'hd_save_thumbs.inc', 'hd_autosave.h', 'hd_autosave.inc'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
    edit('engines/scumm/scumm.h', '\tbool hasHDFontSizeMenu() const;', '''\tbool hasHDFontSizeMenu() const;
\tbool hdBookOptionsPage() const;
\tbool hdBookSpreadShown() const;
\tconst byte *hdBookSpread();
\tCommon::Array<byte> _hdBookSpread;
\tint _hdBookSpreadState = 0;
\tbool _hdBookSpreadChecked = false;
\tbool hdBookHidesObject(int object) const;
\tbool hdBookLaidOut() const;
\tbool hdBookLayoutActive() const;
\tbool hdBookPlace(int &x, int &y) const;
\tvoid hdBookScriptMouse();
\tvoid setHDFontSizeFromBook(int x);
\tbool _hdBookInjecting = false;
\tint _hdBookCapture = -2; // HdBookLayout::kFree
\tstruct HdBookImage { Common::String name; int w = 0, h = 0; Common::Array<uint32> pixels; };
\tstruct HdBookStamp { Common::Rect box; Common::Array<byte> native; Common::Array<uint32> pixels; };
\tCommon::Array<HdBookImage> _hdBookImages;
\tCommon::Array<HdBookStamp> _hdBookStamps;
\tbool hdBookImage(const Common::String &name, HdBookImage &out);
\tvoid addHDBookStamp(const Common::Rect &box, int brightness, const HdBookImage *image);
\tvoid drawHDBookStamps();
\tvoid removeHDSaveThumbnails(const Common::String &save, const Common::String &keep);
\tvoid copyHDSaveThumbnail(int slot);
\tint _hdBookLoad = -1;
\tbool hdBookLoadShift() const;
\tint hdBookLoadSlot(int tile) const;
\tint hdBookStampSlot(int tile) const;
\tbool hdBookNumber(byte *text, int x, int y) const;
\tbool hdBookSavegameName(int tile, Common::String &name);''')
    gfx = 'engines/scumm/gfx.cpp'
    edit(gfx, '#include "scumm/hd_banner.h"', '#include "scumm/hd_banner.h"\n#include "scumm/hd_book_layout.h"\n#include "scumm/hd_autosave.h"')
    edit(gfx, '#include "scumm/hd_font_size_menu.inc"', '#include "scumm/hd_font_size_menu.inc"\n\n#include "scumm/hd_book.inc"')
    # Both CPU native passes: foreground (step 2) and the UI re-overlay (step
    # 2.6b). Room 92 never uses the GPU scene path.
    edit(gfx, '\t\tint dirtyCount = 0;', '\t\tint dirtyCount = 0;\n\t\tconst byte *hdSpread = hdBookSpread();')
    edit(gfx, 'isForeground = (curPix != cleanRow[sx]);',
         'isForeground = (curPix != cleanRow[sx]) && !(hdSpread && curPix == hdSpread[pos]);')
    edit(gfx, '\t\tint step26b_count = 0;\n', '\t\tint step26b_count = 0;\n\t\tconst byte *hdSpread = hdBookSpread();\n')
    edit(gfx, '\t\t\t\tif (curPix == cleanPix)\n\t\t\t\t\tcontinue;',
         '\t\t\t\tif (curPix == cleanPix || (hdSpread && curPix == hdSpread[mpos]))\n\t\t\t\t\tcontinue;')
    # Layout: queued items are drawn translated; the scripts read the pointer
    # translated back. The Text Size slider joins the queue once per frame.
    edit('engines/scumm/scumm_v6.h', '\tint getBlastCount() const { return _blastObjectQueuePos; }',
         '\tvirtual void enqueueHDBookControls() {}\n\tint getBlastCount() const { return _blastObjectQueuePos; }')
    edit('engines/scumm/scumm_v7.h', '\tvoid drawTextImmediately(const byte *text, Common::Rect *clipRect,',
         '\tvoid enqueueHDBookControls() override;\n\tvoid drawTextImmediately(const byte *text, Common::Rect *clipRect,')
    edit(gfx, 'void ScummEngine_v6::drawDirtyScreenParts() {\n', 'void ScummEngine_v6::drawDirtyScreenParts() {\n\tenqueueHDBookControls();\n')
    edit('engines/scumm/object.cpp', '\tBlastObject *eo;\n\n\tif (_blastObjectQueuePos >= (int)ARRAYSIZE(_blastObjectQueue)) {',
         '\tBlastObject *eo;\n\n\tif (!hdBookPlace(objectX, objectY)) return;\n\tif (_blastObjectQueuePos >= (int)ARRAYSIZE(_blastObjectQueue)) {')
    # After conversion: scripts print slot numbers through variable codes.
    edit('engines/scumm/string_v7.cpp', '\tconvertMessageToString(text, bt.text, sizeof(bt.text));\n',
         '\tconvertMessageToString(text, bt.text, sizeof(bt.text));\n\tif (!hdBookNumber(bt.text, x, y) || !hdBookPlace(x, y)) return;\n')
    edit('engines/scumm/scumm.cpp', '\t\tVAR(VAR_MOUSE_Y) = _mouse.y;\n', '\t\tVAR(VAR_MOUSE_Y) = _mouse.y;\n\t\thdBookScriptMouse();\n')
    edit('engines/scumm/object.cpp', '\tif ((i < 1) || (od->obj_nr < 1) || !od->state)\n\t\treturn;\n',
         '\tif ((i < 1) || (od->obj_nr < 1) || !od->state || hdBookHidesObject(od->obj_nr))\n\t\treturn;\n')
    # HD save thumbnails (hd_save_thumbs.inc): written beside each save, drawn
    # over the book's native stamps; slot stamps follow the slot layout.
    edit(gfx, '\t// Step 2.7: Render HD font characters recorded during 8-bit drawing',
         '\tdrawHDBookStamps();\n\t// Step 2.7: Render HD font characters recorded during 8-bit drawing')
    edit('engines/scumm/scumm_v8.h', '\tvoid createInternalSaveStateThumbnail();', """\tvoid createInternalSaveStateThumbnail();
\tuint32 hdThumbnailKey() const;
\tbool captureHDSaveThumbnail(Graphics::Surface &out);
\tvoid writeHDSaveThumbnail(int slot, bool temporary);
\tvoid recordHDStamp(int slot, bool heap, int boxX, int boxY, int boxWidth, int boxHeight, int brightness, bool internal);
\tvoid hdChapterAutosave();
\tbool _hdChapterPending = false;
\tint _hdChapterRoom = -1;
\tuint32 _hdChapterSince = 0;""")
    saveload = 'engines/scumm/saveload.cpp'
    edit(saveload, '#include "graphics/thumbnail.h"', '#include "graphics/thumbnail.h"\n#include "common/hd_remaster.h"\n#include "image/png.h"\n#include "scumm/hd_autosave.h"')
    edit(saveload, 'bool ScummEngine_v8::fetchInternalSaveStateThumbnail(int slotId, bool isHeapSave) {',
         '#include "scumm/hd_save_thumbs.inc"\n#include "scumm/hd_autosave.inc"\n\nbool ScummEngine_v8::fetchInternalSaveStateThumbnail(int slotId, bool isHeapSave) {')
    edit(saveload, '\tif (thumbSurface)\n\t\tdelete[] thumbSurface;\n}\n',
         '\tif (thumbSurface)\n\t\tdelete[] thumbSurface;\n\trecordHDStamp(slot, hdHeap, boxX, boxY, boxWidth, boxHeight, brightness, foundInternalThumbnail);\n}\n')
    edit(saveload, '\tif (_stampShotsInQueue >= (int)ARRAYSIZE(_stampShots))\n\t\terror("ScummEngine_v8::stampShotEnqueue(): overflow in the queue");\n',
         '\tif (_stampShotsInQueue >= (int)ARRAYSIZE(_stampShots))\n\t\terror("ScummEngine_v8::stampShotEnqueue(): overflow in the queue");\n\thdBookPlace(boxX, boxY);\n\tslot = hdBookStampSlot(slot);\n')
    edit(saveload, '\t\tdebug(1, "State saved as \'%s\'", fileName.c_str());\n}\n\n#ifdef ENABLE_SCUMM_7_8\nvoid ScummEngine_v8::stampShotEnqueue',
         '\t\tdebug(1, "State saved as \'%s\'", fileName.c_str());\n\tif (!saveFailed) copyHDSaveThumbnail(slot);\n}\n\n#ifdef ENABLE_SCUMM_7_8\nvoid ScummEngine_v8::stampShotEnqueue')
    edit('engines/scumm/scumm.cpp', '\tif (_saveLoadFlag == 1) {\n\t\tcreateInternalSaveStateThumbnail();\n\t}\n',
         '\tif (_saveLoadFlag == 1) {\n\t\tcreateInternalSaveStateThumbnail();\n\t\twriteHDSaveThumbnail(_saveLoadSlot, _saveTemporaryState);\n\t}\n')
    # Autosave (hd_autosave.h/.inc): chapter trigger; Load page tile for slot 0.
    edit(saveload, '\tfoundInternalThumbnail = fetchInternalSaveStateThumbnail(slot == 0 ? 1 : slot, slot == 0);',
         '\tconst bool hdHeap = slot == 0;\n\tif (slot == HdAutosave::kStampSlot) slot = 0; // Load-page autosave tile: the file, not the heap.\n'
         '\tfoundInternalThumbnail = fetchInternalSaveStateThumbnail(hdHeap ? 1 : slot, hdHeap);')
    edit(saveload, 'thumbSurface = fetchScummVMSaveStateThumbnail(slot == 0 ? 1 : slot, slot == 0, brightness);',
         'thumbSurface = fetchScummVMSaveStateThumbnail(hdHeap ? 1 : slot, hdHeap, brightness);')
    script = 'engines/scumm/script_v8.cpp'
    edit(script, '\t\tif (getSavegameName(args[1], name)) {', '\t\tif (hdBookSavegameName(args[1], name)) {')
    edit(script, '\t\t_saveLoadSlot = args[1];\n\t\t_saveLoadFlag = 2;', '\t\t_saveLoadSlot = hdBookLoadSlot(args[1]);\n\t\t_saveLoadFlag = 2;')
    edit('engines/scumm/scumm.cpp', 'void ScummEngine_v8::scummLoop_handleSaveLoad() {\n', 'void ScummEngine_v8::scummLoop_handleSaveLoad() {\n\thdChapterAutosave();\n')
