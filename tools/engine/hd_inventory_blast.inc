// bdd contains the original image dimensions, position, palette and scaling.
const int room = _hdObjectManager->findObjectRoom(eo->number);
const Graphics::Surface *replacement = _hdObjectManager->getObjectSurface(
    eo->number, room < 0 ? _currentRoom : room, HdInventory::imageIndex(eo->image));
const bool useReplacement = replacement && bdd.scale_x == 255 && bdd.scale_y == 255 && bdd.shadowMode == 0;
if (useReplacement) {
    HdInventory::blit(_hdComposite, *replacement, bdd.x * _hdScale, bdd.y * _hdScale,
                     bdd.srcwidth * _hdScale, bdd.srcheight * _hdScale);
} else if (hasHDInventory()) {
    // A missing HD icon must still appear on top of the new panel. Decode
    // through the native BOMP renderer, preserving native scaling/palette.
    Graphics::Surface native;
    native.create(bdd.srcwidth, bdd.srcheight, Graphics::PixelFormat::createFormatCLUT8());
    memset(native.getPixels(), 255, native.pitch * native.h);
    bdd.dst = native;
    bdd.x = bdd.y = 0;
    drawBomp(bdd);
    HdInventory::blit(_hdComposite, native, eo->rect.left * _hdScale, eo->rect.top * _hdScale, native.w * _hdScale,
                     native.h * _hdScale, _currentPalette);
    native.free();
}
if (_hdFrameCount % 30 == 0) hdPrintf("HD-INVENTORY obj=%d image=%d source=%s pos=(%d,%d)", eo->number,
         eo->image, useReplacement ? "hd" : "native", eo->rect.left, eo->rect.top);
