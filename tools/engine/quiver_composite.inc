// Validated poses have already been removed from quiverNative before the native
// foreground copy. Draw only their replacement textures, in original depth order.
if (!quiverPoses.empty()) {
    for (uint ai = 0; ai < quiverPoses.size(); ++ai) {
        Actor *a = quiverPoses[ai].actor;
        const bool coin = a->_costume == 1 && a->_layer < 0;
        if (coin != hdCoinPass) continue;
        const HdActorLighting::Tint lighting = coin ? HdActorLighting::Tint() : actorLighting(a);
        Common::Array<Graphics::Surface *> &textures = quiverPoses[ai].textures;
        const bool editableAnimation=!coin&&!quiverPoses[ai].water&&(VAR_EGO==0xff||a->_number!=VAR(VAR_EGO))&&(!textures.empty()||quiverPoses[ai].nativeAnimation);
        HdMasks::Point animationShift;
        if(editableAnimation){
            HdMasks::state().animationPack=ConfMan.hasKey("playtest_character_pack")?ConfMan.get("playtest_character_pack").c_str():"original";
            HdMasks::AnimationVisual v;v.actor=a->_number;v.costume=a->_costume;v.room=_currentRoom;v.key=HdMasks::animationKey(v.actor,v.costume);
            v.anchorX=a->getRealPos().x;v.anchorY=a->getRealPos().y;
            int bx=32767,by=32767,br=-32767,bb=-32767;
            for(const auto &part:a->_quiverDraws){bx=MIN(bx,part.screenLeft);by=MIN(by,part.screenTop);br=MAX(br,part.screenLeft+part.screenWidth);bb=MAX(bb,part.screenTop+part.screenHeight);v.cel=part.cel;}
            v.x=bx+vs->xstart;v.y=by+_screenTop;v.w=MAX(0,br-bx);v.h=MAX(0,bb-by);
            HdMasks::state().animationVisuals.push_back(v);animationShift=HdMasks::effectiveAnimation(v.key,v.cel);
        }
        HdSprites::Frame nativeFrame;
        const unsigned char *nativeMatte=nullptr;
        const bool nativeCapture=quiverPoses[ai].nativeAnimation&&HdMasks::state().open&&HdMasks::state().animationsTab;
        if(quiverPoses[ai].nativeAnimation){auto &v=HdMasks::state().animationVisuals.back();
            if(nativeCapture||HdMasks::hasSpriteMask(v.key,v.cel)){
                nativeFrame=HdSprites::make("animation:"+v.key,v.cel,v.room,v.x,v.y,v.w,v.h);nativeFrame.anchorX=v.anchorX;nativeFrame.anchorY=v.anchorY;nativeFrame.mirror=a->_quiverDraws.back().mirror;
                for(int y=0;y<visH;++y)for(int x=0;x<visW;++x){int offset=y*visW+x;byte index=a->_quiverAfter[offset];if(index==a->_quiverUnder[offset])continue;
                    const byte *rgb=_currentPalette+index*3;uint32 color=0xff000000u|rgb[0]|(rgb[1]<<8)|(rgb[2]<<16);
                    HdSprites::paint(nativeFrame,x+vs->xstart,y+_screenTop,1,1,[&](double,double){return color;});}
                nativeMatte=HdMasks::spriteMaskRaster(v.key,v.cel,nativeFrame.pw,nativeFrame.ph,nativeFrame.pw/v.w,nativeFrame.ph/v.h,nativeFrame.mirror,[&](int x,int y){return nativeFrame.pixels[y*nativeFrame.pw+x];});
            }
        }
        if (quiverPoses[ai].nativeColorFallback) {
            const int z=a->_quiverDraws[0].z;
            const signed char *movedMask=quiverPoses[ai].nativeAnimation?hdMasksForegroundRaster(z,hdW,hdH,scale):nullptr;
            const bool bypass=hdMasksForegroundBypass(z);
            for (int y = 0; y < visH; ++y) {
                const byte *native = !quiverWithoutCoin.empty() ? &quiverWithoutCoin[y * visW] :
                    !quiverWithoutWater.empty() ? &quiverWithoutWater[y * visW] :
                    (const byte *)vs->getBasePtr(vs->xstart, y + _screenTop);
                for (int x = 0; x < visW; ++x) {
                    const int offset = y * visW + x;
                    const byte index = a->_quiverAfter[offset];
                    // A moved flame needs its source pixels even when Guybrush stood
                    // in front of its original location. Occlusion is tested at
                    // the destination below; ordinary native fallbacks stay put.
                    if (index == a->_quiverUnder[offset] || (!quiverPoses[ai].nativeAnimation && native[x] != index)) continue;
                    const byte *rgb = (quiverPoses[ai].nativeAnimation?_currentPalette:_darkenPalette) + index * 3;
                    const uint32 paletteColor=0xff000000u | rgb[0] | (rgb[1] << 8) | (rgb[2] << 16);
                    const uint32 color = quiverPoses[ai].nativeAnimation?paletteColor:lighting.apply(paletteColor);
                    if(quiverPoses[ai].nativeAnimation&&HdMasks::spriteMaskPreview(HdMasks::animationKey(a->_number,a->_costume)))continue;
                    const int dx=(int)std::round(animationShift.x*scale),dy=(int)std::round(animationShift.y*scale);
                    for (int yy = MAX(0,y * scale+dy); yy < MIN(hdH, (y + 1) * scale+dy); ++yy)
                        for (int xx = MAX(0,x * scale+dx); xx < MIN(hdW, (x + 1) * scale+dx); ++xx) {
                            if(quiverPoses[ai].nativeAnimation){
                                const int nx=xx/scale,ny=yy/scale;
                                const byte *current=!quiverWithoutCoin.empty()?&quiverWithoutCoin[ny*visW]:!quiverWithoutWater.empty()?&quiverWithoutWater[ny*visW]:(const byte *)vs->getBasePtr(vs->xstart,ny+_screenTop);
                                if(current[nx]!=a->_quiverAfter[ny*visW+nx])continue;
                                if(!bypass){int authored=movedMask?movedMask[yy*hdW+xx]:-1;
                                    const byte *row=z>=0&&z<_gdi->_numZBuffer?getMaskBuffer(0,ny+_screenTop,z):nullptr;
                                    if(authored>=0?authored!=0:HdObjectDepth::masked(row,nx,vs->xstart&7))continue;}
                            }
                            unsigned alpha=255;
                            if(nativeMatte){auto &v=HdMasks::state().animationVisuals.back();int mx=((xx-dx+.5)/scale+vs->xstart-v.x)*nativeFrame.pw/v.w,my=((yy-dy+.5)/scale+_screenTop-v.y)*nativeFrame.ph/v.h;
                                if(mx<0||my<0||mx>=nativeFrame.pw||my>=nativeFrame.ph)continue;alpha=nativeMatte[my*nativeFrame.pw+mx];}
                            if(!alpha)continue;uint32 &dest=*(uint32 *)_hdComposite.getBasePtr(xx,yy);
                            if(alpha==255)dest=color;else{uint32 r=((color&255)*alpha+(dest&255)*(255-alpha)+127)/255,g=(((color>>8)&255)*alpha+((dest>>8)&255)*(255-alpha)+127)/255,b=(((color>>16)&255)*alpha+((dest>>16)&255)*(255-alpha)+127)/255;
                                dest=r|(g<<8)|(b<<16)|((alpha+((dest>>24)*(255-alpha)+127)/255)<<24);}
                            hdAlphaMask[yy * hdW + xx] = 1;
                        }
                }
            }
            if(nativeCapture)HdSprites::remember(std::move(nativeFrame));
            continue;
        }
        for (uint di = 0; di < textures.size(); ++di) {
            const Actor::QuiverDraw &d = a->_quiverDraws[di];
            const Graphics::Surface &texture = *textures[di];
            if (coin && d.cel < 63) {
                for (uint pi = 0; pi < d.coinPixels.size(); ++pi) {
                    const Actor::CoinPixel &p = d.coinPixels[pi];
                    const byte *rgb = _currentPalette + p.color * 3;
                    uint32 color = _hdComposite.format.RGBToColor(rgb[0], rgb[1], rgb[2]);
                    for (int y = p.y * scale; y < MIN(hdH, (p.y + 1) * scale); ++y)
                        for (int x = p.x * scale; x < MIN(hdW, (p.x + 1) * scale); ++x) {
                            *(uint32 *)_hdComposite.getBasePtr(x, y) = color;
                            hdAlphaMask[y * hdW + x] = 1;
                        }
                }
                continue;
            }
            int edgeTreatment = HdCostumeEdge::guybrushHead(d.costume, d.cel) ? 1 : 0;
            // The last alpha row of this Topaz head is empty, exposing a line
            // between the head and torso. Extend its adjacent edge row only
            // when the original matching body is present at the native join.
            if (quiverPoses[ai].topaz && _currentRoom == 9 && d.costume == 2 && d.cel == 52)
                for (uint bi = 0; bi < textures.size(); ++bi) {
                    const Actor::QuiverDraw &body = a->_quiverDraws[bi];
                    if (body.cel == 31 && body.mirror == d.mirror &&
                        d.screenTop + d.screenHeight == body.screenTop + 1)
                        edgeTreatment = 3;
                }
            // Bounds come from the original decoder's scale table, not a
            // floating-point approximation of actor scaling.
            int w = d.screenWidth * scale;
            int h = d.screenHeight * scale;
            if (!w || !h) continue;
            int left = d.screenLeft * scale;
            int top = d.screenTop * scale;
            if(VAR_EGO!=0xff&&a->_number==VAR(VAR_EGO)&&HdHead::headCel(d.costume,d.cel)){
                auto &head=HdHead::state();auto &view=head.visual;
                view.anchorX=a->getRealPos().x;view.anchorY=a->getRealPos().y;view.valid=true;view.room=_currentRoom;view.costume=d.costume;view.cel=d.cel;view.mirror=d.mirror;
                view.pack=ConfMan.hasKey("playtest_character_pack")?ConfMan.get("playtest_character_pack").c_str():"unknown";
                // One alignment follows all separate head frames in this
                // costume, including speech, so animation cannot undo a fix.
                view.key=HdHead::key(view.pack,d.costume,-1);view.sourceWidth=d.width;view.sourceHeight=d.height;
                view.head.x=d.screenLeft+vs->xstart;view.head.y=d.screenTop+_screenTop;view.head.w=d.screenWidth;view.head.h=d.screenHeight;
                int bx=32767,by=32767,br=-32767,bb=-32767;
                for(const auto &part:a->_quiverDraws)if(!HdHead::headCel(part.costume,part.cel)){
                    bx=MIN(bx,part.screenLeft);by=MIN(by,part.screenTop);br=MAX(br,part.screenLeft+part.screenWidth);bb=MAX(bb,part.screenTop+part.screenHeight);
                }
                view.body.x=bx+vs->xstart;view.body.y=by+_screenTop;view.body.w=MAX(0,br-bx);view.body.h=MAX(0,bb-by);
                auto shift=HdHead::scaled(HdHead::poseOffset(view.pack,view.costume,view.cel),view.head.w,view.head.h,view.sourceWidth,view.sourceHeight,d.mirror);
                left+=(int)std::round(shift.x*scale);top+=(int)std::round(shift.y*scale);
            }
            const bool captureHead=HdMasks::state().open&&HdMasks::state().headTab&&VAR_EGO!=0xff&&a->_number==VAR(VAR_EGO)&&HdHead::headCel(d.costume,d.cel);
            if(captureHead||(editableAnimation&&HdMasks::state().open&&HdMasks::state().animationsTab)){
                const std::string group=captureHead?"head:"+HdHead::state().visual.key:"animation:"+HdMasks::animationKey(a->_number,a->_costume);
                auto f=HdSprites::make(group,d.cel,_currentRoom,d.screenLeft+vs->xstart,d.screenTop+_screenTop,d.screenWidth,d.screenHeight);
                f.sourceW=d.width;f.sourceH=d.height;f.mirror=d.mirror;f.anchorX=a->getRealPos().x;f.anchorY=a->getRealPos().y;
                HdSprites::paint(f,f.x,f.y,f.w,f.h,[&](double u,double v){int x=MIN(texture.w-1,(int)(u*texture.w)),y=MIN(texture.h-1,(int)(v*texture.h));if(d.mirror)x=texture.w-1-x;return lighting.apply(HdCostumeEdge::sample((const uint32 *)texture.getPixels(),texture.pitch/4,texture.w,texture.h,x,y,edgeTreatment));});
                HdSprites::remember(std::move(f));
            }
            if(editableAnimation&&HdMasks::spriteMaskPreview(HdMasks::animationKey(a->_number,a->_costume)))continue;
            unsigned int cannonFraction = 1024;
            const Graphics::Surface &cannonFrom = quiverPoses[ai].cannonFrom;
            if (cannonFrom.getPixels()) {
                cannonFraction = _hdMotionFraction;
                const auto &from = _hdMotionCannon.from;
                const auto &to = _hdMotionCannon.to;
                // Align the two barrel poses to interpolated bounds before
                // blending their pixels, so the base and outline move together.
                left = HdMotion::Track::mix(from.left * scale, to.left * scale, cannonFraction);
                top = HdMotion::Track::mix(from.top * scale, to.top * scale, cannonFraction);
                w = HdMotion::Track::mix(from.width * scale, to.width * scale, cannonFraction);
                h = HdMotion::Track::mix(from.height * scale, to.height * scale, cannonFraction);
            }
            if(editableAnimation)animationShift=HdMasks::effectiveAnimation(HdMasks::animationKey(a->_number,a->_costume),d.cel);
            left+=(int)std::round(animationShift.x*scale);top+=(int)std::round(animationShift.y*scale);
            static HdCostumeRaster::Cache rasterCache;
            rasterCache.scope(_currentRoom, _playtestCommandId);
            const uint32 *raster = HdRemaster::state().active ? rasterCache.get(
                (const uint32 *)texture.getPixels(), texture.pitch / 4, texture.w, texture.h,
                w, h, d.costume, d.cel, d.mirror, edgeTreatment, lighting) : nullptr;
            const uint32 *cannonRaster = cannonFraction < 1024 && HdRemaster::state().active ? rasterCache.get(
                (const uint32 *)cannonFrom.getPixels(), cannonFrom.pitch / 4, cannonFrom.w, cannonFrom.h,
                w, h, 35, _hdMotionCannon.from.cel, _hdMotionCannon.from.mirror, 0, lighting) : nullptr;
            const unsigned char *spriteMatte=editableAnimation?HdMasks::spriteMaskRaster(HdMasks::animationKey(a->_number,a->_costume),d.cel,w,h,double(w)/d.screenWidth,double(h)/d.screenHeight,d.mirror,[&](int x,int y){
                if(raster)return raster[y*w+x];int sx=x*texture.w/w,sy=y*texture.h/h;if(d.mirror)sx=texture.w-1-sx;
                return HdCostumeEdge::sample((const uint32 *)texture.getPixels(),texture.pitch/4,texture.w,texture.h,sx,sy,edgeTreatment);
            }):nullptr;
            const signed char *authoredMask = coin ? nullptr : hdMasksForegroundRaster(d.z, hdW, hdH, scale);
            const bool bypassMask = !coin && hdMasksForegroundBypass(d.z);
            for (int yy = MAX(0, top); yy < MIN(hdH, top + h); ++yy) {
                const int ny = yy / scale;
                const byte *nativeRow = !coin && !quiverWithoutCoin.empty()
                    ? &quiverWithoutCoin[ny * visW] : !coin && !quiverWithoutWater.empty()
                    ? &quiverWithoutWater[ny * visW] : (const byte *)vs->getBasePtr(vs->xstart, ny + _screenTop);
                const byte *actorRow = &a->_quiverAfter[ny * visW];
                // Resolve the z-buffer resource once per row, never once per HD
                // pixel. Preserve sub-strip camera offsets in the byte lookup.
                const byte *maskRow = d.z >= 0 && d.z < _gdi->_numZBuffer ? getMaskBuffer(0, ny + _screenTop, d.z) : nullptr;
                const int maskOffset = vs->xstart & 7;
                int sourceY = (yy - top) * texture.h / h;
                uint32 *dest = (uint32 *)_hdComposite.getBasePtr(0, yy);
                for (int xx = MAX(0, left); xx < MIN(hdW, left + w); ++xx) {
                    int nx = xx / scale;
                    if (nativeRow[nx] != actorRow[nx]) continue;
                    if (!coin && !bypassMask) {
                        int authored = authoredMask ? authoredMask[yy * hdW + xx] : -1;
                        if (authored >= 0 ? authored != 0 : HdObjectDepth::masked(maskRow, nx, maskOffset)) continue;
                    }
                    int sourceX = (xx - left) * texture.w / w;
                    if (d.mirror) sourceX = texture.w - 1 - sourceX;
                    // Extend real outline RGB into the soft matte BEFORE room
                    // lighting; retain alpha and the native geometry exactly.
                    uint32 color = raster ? raster[(yy - top) * w + xx - left] : lighting.apply(HdCostumeEdge::sample(
                        (const uint32 *)texture.getPixels(), texture.pitch / 4,
                        texture.w, texture.h, sourceX, sourceY, edgeTreatment));
                    if (cannonFraction < 1024) {
                        int oldX = (xx - left) * cannonFrom.w / w;
                        if (_hdMotionCannon.from.mirror) oldX = cannonFrom.w - 1 - oldX;
                        const int oldY = (yy - top) * cannonFrom.h / h;
                        const uint32 oldColor = cannonRaster ? cannonRaster[(yy - top) * w + xx - left] :
                            lighting.apply(*(const uint32 *)cannonFrom.getBasePtr(oldX, oldY));
                        color = HdMotion::CannonAim::blend(oldColor, color, cannonFraction);
                    }
                    uint32 alpha = spriteMatte?spriteMatte[(yy-top)*w+xx-left]:color>>24;
                    color=(color&0xffffffu)|(alpha<<24);
                    if (!alpha) continue;
                    if (alpha == 255) {
                        dest[xx] = color; hdAlphaMask[yy * hdW + xx] = 1; continue;
                    }
                    uint32 previous = dest[xx];
                    uint32 r = ((color & 255) * alpha + (previous & 255) * (255 - alpha) + 127) / 255;
                    uint32 g = (((color >> 8) & 255) * alpha + ((previous >> 8) & 255) * (255 - alpha) + 127) / 255;
                    uint32 b = (((color >> 16) & 255) * alpha + ((previous >> 16) & 255) * (255 - alpha) + 127) / 255;
                    dest[xx] = r | (g << 8) | (b << 16) |
                        ((alpha + ((previous >> 24) * (255 - alpha) + 127) / 255) << 24);
                    hdAlphaMask[yy * hdW + xx] = 1;
                }
            }
            if (_hdFrameCount % 30 == 0)
                hdPrintf("QUIVER actor=%d costume=%d cel=%d at=%d,%d size=%d,%d mirror=%d light=%d,%d,%d", a->_number, d.costume, d.cel, left, top, w, h, d.mirror, lighting.channel[0], lighting.channel[1], lighting.channel[2]);
        }
        for (uint i = 0; i < textures.size(); ++i) {
            delete textures[i];
        }
    }
}

if (hdCoinPass) {
    if (_hdUICostumeManager) _hdUICostumeManager->endBorrow();
    if (_hdQuiverManager) _hdQuiverManager->endBorrow();
}
