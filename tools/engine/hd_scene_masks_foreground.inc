// Rendering overrides only: never write to room resources or saved game data.
namespace {
struct MaskForegroundCache {
    std::string key;
    int revision=-1,width=0,height=0,left=0,top=0,scale=0;
    std::vector<signed char> pixels[8];
    std::vector<byte> native[8];
};
MaskForegroundCache &maskForegroundCache(bool native=false){static MaskForegroundCache c[2];return c[native?0:1];}
}
const signed char *ScummEngine::hdMasksForegroundRaster(int plane,int width,int height,int scale) {
    auto &s=HdMasks::state();auto *d=s.draft();
    if(_game.id!=GID_CMI||s.room!=_currentRoom||!d||plane<1||plane>7)return nullptr;
    const auto *f=HdMasks::foreground(static_cast<const HdMasks::Document &>(d->live),plane);
    if(!f)return nullptr;
    auto &c=maskForegroundCache(scale==1);const int left=_virtscr[kMainVirtScreen].xstart,top=_screenTop;
    if(c.key!=s.key||c.revision!=s.revision||c.width!=width||c.height!=height||c.left!=left||c.top!=top||c.scale!=scale){
        c.key=s.key;c.revision=s.revision;c.width=width;c.height=height;c.left=left;c.top=top;c.scale=scale;
        for(auto &p:c.pixels)p.clear();
    }
    if(c.pixels[plane].empty())HdMasks::rasterForeground(c.pixels[plane],width,height,f,left,top,scale);
    return c.pixels[plane].data();
}
bool ScummEngine::hdMasksForegroundBypass(int plane) {
    auto &s=HdMasks::state();return s.room==_currentRoom&&s.open&&s.foregroundTab&&s.bypassForeground&&s.plane==plane&&hdMasksAvailable();
}
byte *ScummEngine::hdMasksActorMask(int actor,bool hitTest,int x,int y,int z) {
    byte *original=getMaskBuffer(x,y,z);
    if(hitTest||(_game.id==GID_CMI&&actor>=0&&actor<_numActors&&_actors[actor]&&_actors[actor]->_costume==1&&_actors[actor]->_layer<0))return original;
    if(_game.id!=GID_CMI||!_hdBackgroundSurface.getPixels()||z<1||z>=_gdi->_numZBuffer)return original;
    const bool bypass=hdMasksForegroundBypass(z);
    const signed char *coverage=hdMasksForegroundRaster(z,_screenWidth,_screenHeight,1);
    if(!bypass&&!coverage)return original;
    auto &bytes=maskForegroundCache(true).native[z];
    const int stride=_gdi->_numStrips,size=(_roomHeight+10)*stride;
    const byte *source=_gdi->getMaskBuffer(0,0,z);bytes.assign(source,source+size);
    int left=_virtscr[kMainVirtScreen].xstart;
    for(int yy=0;yy<_screenHeight;++yy)for(int xx=0;xx<_screenWidth;++xx){
        int value=bypass?0:coverage[yy*_screenWidth+xx];if(value<0)continue;
        int offset=(yy+_screenTop)*stride+(xx+left)/8;
        if(offset<0||offset>=size)continue;
        byte bit=0x80>>((xx+left)&7);if(value)bytes[offset]|=bit;else bytes[offset]&=~bit;
    }
    int offset=y*stride+(x+left)/8;
    return offset>=0&&offset<size?bytes.data()+offset:original;
}
void ScummEngine::hdMasksRedrawActors() {
    for(int i=1;i<_numActors;++i)if(_actors[i]&&_actors[i]->_room==_currentRoom){_actors[i]->_needRedraw=true;_actors[i]->_needBgReset=true;}
    _fullRedraw=true;
}
void ScummEngine::hdMasksTraceForeground(HdMasks::Document &next) {
    using namespace HdMasks;auto &s=state();
    if(s.plane<1||s.plane>=_gdi->_numZBuffer){s.error="No foreground depth plane in this room";return;}
    const auto *existing=foreground(static_cast<const Document &>(next),s.plane);
    const int w=_screenWidth,h=_screenHeight,left=_virtscr[kMainVirtScreen].xstart,top=_screenTop;
    // Only import native pixels that have not already been converted. Keep
    // authored fractional vertices and hide/show order exactly as they are.
    std::vector<signed char> replaced(w*h,-1);
    if(existing)for(const auto &ring:existing->replace)rasterRing(replaced,w,h,ring,left,top,1,0);
    std::vector<byte> pixels(w*h);bool any=false;
    for(int y=0;y<h;++y){const byte *row=getMaskBuffer(0,y+top,s.plane);for(int x=0;x<w;++x){
        pixels[y*w+x]=replaced[y*w+x]<0&&HdObjectDepth::masked(row,x,left&7);any|=pixels[y*w+x]!=0;}}
    if(any){
        auto traced=contours(pixels.data(),w,h,w);Foreground merged;merged.plane=s.plane;
        if(existing)merged=*existing;
        if(merged.order.empty()){for(unsigned i=0;i<merged.zones.size();++i)merged.order.push_back(i+1);for(unsigned i=0;i<merged.holes.size();++i)merged.order.push_back(-int(i)-1);}
        const unsigned authoredCount=merged.order.size();
        for(auto *rings:{&traced.zones,&traced.holes})for(auto &ring:*rings)for(auto &p:ring){p.x=left+p.x*w/1000;p.y=top+p.y*h/1000;}
        for(const auto &ring:traced.zones)addForegroundRing(merged,ring,false);
        for(const auto &ring:traced.holes)addForegroundRing(merged,ring,true);
        // Apply imported native coverage before all authored corrections, without
        // changing existing shape IDs or their precise vertices.
        std::rotate(merged.order.begin(),merged.order.begin()+authoredCount,merged.order.end());
        merged.replace.push_back(rectangle({double(left),double(top)},{double(left+w),double(top+h)}));
        foreground(next,s.plane)=merged;
        // Validate before presenting handles; failed conversion leaves the draft intact.
        if(!validate(next,s.error))return;
        s.preview=next;s.pending=true;
    }
    const auto *f=foreground(static_cast<const Document &>(next),s.plane);
    s.selected=s.node=-1;s.error.clear();
    if(f&&!f->zones.empty()){s.selected=0;s.hole=false;}
    else if(f&&!f->holes.empty()){s.selected=0;s.hole=true;}
    else s.error="No clipping on this layer. Try Clip layer >, or draw a Hide / Show shape.";
}
