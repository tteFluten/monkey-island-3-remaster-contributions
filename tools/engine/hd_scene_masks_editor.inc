// Included after the existing native panels in gfx.cpp.
namespace {
// Font atlases are 4x, independently of the background presentation scale.
const int kMaskScale=4,kMaskRowH=24;
int maskCanvasWidth(){auto &r=HdRemaster::state();return r.viewportWidth>640?r.viewportWidth:854;}
HdMasks::Point maskBaseView(HdMasks::Point p,bool water,bool inverse,int roomW,int roomH) {
    auto &r=HdRemaster::state();const double width=maskCanvasWidth(),pad=(width-r.viewportWidth)/2;
    const double cx=double(r.backgroundX)/MAX(1,r.scale),cy=double(r.backgroundY)/MAX(1,r.scale);
    if(water) {
        if(HdMasks::state().widePainting)return inverse?HdMasks::Point(p.x*1000/width,p.y*1000/480):HdMasks::Point(p.x*width/1000,p.y*480/1000);
        return inverse?HdMasks::Point((p.x-pad+cx)*1000/roomW,(p.y+cy)*1000/roomH):HdMasks::Point(p.x*roomW/1000-cx+pad,p.y*roomH/1000-cy);
    }
    if(r.voodooExterior){if(inverse)return {HdVoodooExterior::nativeX(p.x*2048/width),HdVoodooExterior::nativeY(p.y*1152/480)};return {HdVoodooExterior::paintX(p.x)*width/2048,HdVoodooExterior::paintY(p.y)*480/1152};}
    if(r.plunderMap){if(inverse)return {HdPlunderMap::interpolate(HdPlunderMap::kX,p.x*2048/width,true),HdPlunderMap::interpolate(HdPlunderMap::kY,p.y*1152/480,true)};return {HdPlunderMap::interpolate(HdPlunderMap::kX,p.x)*width/2048,HdPlunderMap::interpolate(HdPlunderMap::kY,p.y)*480/1152};}
    return inverse?HdMasks::Point(p.x-pad+cx,p.y+cy):HdMasks::Point(p.x-cx+pad,p.y-cy);
}
bool maskZoomed(){auto &s=HdMasks::state();return s.open&&(s.foregroundTab||(s.animationsTab&&s.animationMaskEdit))&&!s.test&&HdRemaster::state().active;}
HdMasks::Point maskView(HdMasks::Point p,bool water,bool inverse,int roomW,int roomH){
    auto &v=HdMasks::state().clipView;
    if(inverse&&maskZoomed())p=v.map(p,maskCanvasWidth(),true);
    p=maskBaseView(p,water,inverse,roomW,roomH);
    return !inverse&&maskZoomed()?v.map(p,maskCanvasWidth()):p;
}
int maskDetailOffset(){auto &s=HdMasks::state();return s.animationsTab&&s.animationMaskEdit?72:(s.animationsTab||s.foregroundTab)?48:s.headTab?24:0;}
int maskPanelHeight(){return (HdMasks::state().moreOptions?146:100)+maskDetailOffset();}
Common::Point maskPanelPosition() {
    auto &r=HdRemaster::state();const bool cover=r.viewportWidth>=864||(ConfMan.hasKey("hd_wide_background_active")&&ConfMan.getBool("hd_wide_background_active"));
    auto visible=HdAspect::visibleGame(r.drawableWidth,r.drawableHeight,169,maskCanvasWidth(),cover);
    return Common::Point(visible.x+6,visible.y+(HdMasks::state().menuBottom?MAX(6,visible.h-maskPanelHeight()-6):6));
}
int maskPanelWidth(){auto &r=HdRemaster::state();const bool cover=r.viewportWidth>=864||(ConfMan.hasKey("hd_wide_background_active")&&ConfMan.getBool("hd_wide_background_active"));
    return MIN(680,HdAspect::visibleGame(r.drawableWidth,r.drawableHeight,169,maskCanvasWidth(),cover).w-12);}
std::vector<HdMasks::Control> maskControls(){
    auto &s=HdMasks::state();auto p=maskPanelPosition();const int width=maskPanelWidth();
    std::vector<HdMasks::Control> controls;
    controls.push_back({20,p.x+width-92,p.y,89,16});
    auto row=[&](std::vector<int> slots,int y){for(unsigned i=0;i<slots.size();++i){int x=i*width/slots.size(),right=(i+1)*width/slots.size();controls.push_back({slots[i],p.x+x,p.y+y,right-x-3,kMaskRowH-3});}};
    row({0,1,2,28,18,45,3,4,5},18);
    if(s.animationsTab)row({6,29,30,46,10,11,19},42);
    else if(s.headTab)row({6,7,8,9,10,12,13,19},42);
    else if(s.foregroundTab)row({6,7,8,10,11,15,19},42);
    else if(s.waterTab)row({6,7,8,9,10,11,19},42);
    else row({6,7,9,10,11,19},42);
    if(s.foregroundTab){row({21,22,23,24,25,26,27},66);row({42,43,12,13},90);}
    if(s.animationsTab){if(s.animationMaskEdit){row({47,48,49,50,51},66);row({22,23,53,54,52,27},114);}else row({31,32,33,34,35,36},66);}
    if(s.animationsTab||s.headTab)row({38,39,40,41},s.animationsTab?90:66);
    if(s.moreOptions){
        if(s.animationsTab)row({s.animationMaskEdit?56:37,55},s.animationMaskEdit?172:148);
        else if(s.headTab)row({14,15,17,11,16,55},124);
        else if(s.foregroundTab)row({9,44,16,17,55},148);
        else if(s.waterTab)row({12,13,14,15,16,17,55},100);
        else row({8,12,13,14,15,16,17,55},100);
    }
    return controls;
}
bool maskPolygon(){auto &s=HdMasks::state();return s.waterTab||s.foregroundTab;}
std::vector<HdMasks::Ring> &maskRings(HdMasks::Document &d,bool hole){
    auto &s=HdMasks::state();if(s.foregroundTab){auto &f=HdMasks::foreground(d,s.plane);return hole?f.holes:f.zones;}return hole?d.water.holes:d.water.zones;
}
const std::vector<HdMasks::Ring> &maskRings(const HdMasks::Document &d,bool hole){
    static const std::vector<HdMasks::Ring> empty;auto &s=HdMasks::state();
    if(s.foregroundTab){auto *f=HdMasks::foreground(d,s.plane);return f?(hole?f->holes:f->zones):empty;}return hole?d.water.holes:d.water.zones;
}
void maskAuthored(HdMasks::Document &d){if(HdMasks::state().waterTab)d.water.authored=true;}
int maskButtonAction(int slot){
    static const int common[]={0,1,18,4,12,5,6,7,8,9,10,11};
    static const int walk[]={20,25,3,19,13,14},water[]={2,3,15,16,13,14},foreground[]={21,22,15,23,13,24};
    auto &s=HdMasks::state();if(slot>=46&&slot<=56)return slot+19;if(slot==45)return 64;if(slot==44)return 26;if(slot>=28&&slot<=43)return slot+19;if(slot==18)return 29;if(slot==19)return 38;if(slot==20)return 39;if(slot>=21&&slot<=27)return slot+19;
    if(s.headTab&&slot>=6){static const int head[]={6,30,31,32,33,34,10,11,35,36,13,37};return head[slot-6];}
    if(s.foregroundTab&&(slot==7||slot==8))return slot==7?27:28;if(slot<12)return slot==8&&!maskPolygon()?17:common[slot];
    return (s.foregroundTab?foreground:s.waterTab?water:walk)[slot-12];
}
HdMasks::Ring *maskSelected(HdMasks::Document &d) {
    auto &s=HdMasks::state();if(s.selected<0)return nullptr;
    if(!maskPolygon()){auto *b=HdMasks::find(d,s.selected);return b?&b->points:nullptr;}
    auto &list=maskRings(d,s.hole);return s.selected<(int)list.size()?&list[s.selected]:nullptr;
}
struct MaskEdge {int shape=-1,node=-1;bool hole=false;HdMasks::Point point;double distance=8;};
MaskEdge maskNearestEdge(const HdMasks::Document &doc,HdMasks::Point mouse,int rw,int rh){
    using namespace HdMasks;auto &s=state();MaskEdge hit;auto *f=foreground(doc,s.plane);if(!f)return hit;
    eachForeground(*f,[&](const Ring &ring,bool hole){
        for(unsigned i=0;i<ring.size();++i){Point a=ring[i],b=ring[(i+1)%ring.size()];
            for(int j=0;j<32;++j){double t0=j/32.0,t1=(j+1)/32.0;
                Point aa=maskView({a.x+(b.x-a.x)*t0,a.y+(b.y-a.y)*t0},false,false,rw,rh),bb=maskView({a.x+(b.x-a.x)*t1,a.y+(b.y-a.y)*t1},false,false,rw,rh);
                double dx=bb.x-aa.x,dy=bb.y-aa.y,len=dx*dx+dy*dy;
                double u=len?std::max(0.0,std::min(1.0,((mouse.x-aa.x)*dx+(mouse.y-aa.y)*dy)/len)):0;
                double dist=distance(mouse,{aa.x+u*dx,aa.y+u*dy});
                if(dist<=hit.distance){hit.distance=dist;hit.shape=&ring-(hole?f->holes:f->zones).data();hit.hole=hole;hit.node=i;
                    double t=t0+(t1-t0)*u;hit.point={a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t};}
            }
        }
    });return hit;
}
void maskInsertEdge(const MaskEdge &edge,HdMasks::Document &next){
    auto &s=HdMasks::state();if(edge.shape<0){s.error="Point at an outline edge to add a point";return;}
    s.selected=edge.shape;s.hole=edge.hole;auto *ring=maskSelected(next);
    if(!ring||HdMasks::distance(edge.point,(*ring)[edge.node])<.01||HdMasks::distance(edge.point,(*ring)[(edge.node+1)%ring->size()])<.01){s.error="Choose a spot between existing points";return;}
    ring->insert(ring->begin()+edge.node+1,edge.point);s.node=edge.node+1;s.preview=next;s.pending=true;s.clipInsert=false;s.error.clear();
}
void maskClipRectangle(HdMasks::Document &d,HdMasks::Point p) {
    auto &s=HdMasks::state();auto &f=HdMasks::foreground(d,s.plane);
    s.hole=s.clipTool==2;s.selected=(s.hole?f.holes:f.zones).size();
    HdMasks::addForegroundRing(f,HdMasks::rectangle(s.creation.front(),p),s.hole);
}
void maskPixel(Graphics::Surface &surface,int x,int y,byte r,byte g,byte b,byte alpha) {
    if(x<0||y<0||x>=surface.w||y>=surface.h)return;
    // Premultiplied overlay, composed after scene effects.
    uint32 *pixel=(uint32 *)surface.getBasePtr(x,y);byte oa,orr,og,ob;
    surface.format.colorToARGB(*pixel,oa,orr,og,ob);
    *pixel=surface.format.ARGBToColor(alpha+oa*(255-alpha)/255,r*alpha/255+orr*(255-alpha)/255,g*alpha/255+og*(255-alpha)/255,b*alpha/255+ob*(255-alpha)/255);
}
void maskLine(Graphics::Surface &surface,HdMasks::Point a,HdMasks::Point b,byte r,byte g,byte blue) {
    double length=HdMasks::distance(a,b);int count=MIN(12000,MAX(1,(int)std::ceil(length*kMaskScale)));
    for(int i=0;i<=count;++i){int x=(a.x+(b.x-a.x)*i/count)*kMaskScale,y=(a.y+(b.y-a.y)*i/count)*kMaskScale;for(int j=0;j<2;++j)maskPixel(surface,x+j,y,r,g,blue,230);}
}
// Native font cells have substantial transparent padding. Cache ink-cropped
// labels so button baselines and hit rectangles agree at every display ratio.
void maskText(Graphics::Surface &dest,HdFontManager *fonts,CharsetRenderer *charset,
              const Common::String &text,int left,int top,int width,int height,bool accent=false,bool plate=false,bool enabled=true){
    static std::map<std::string,Graphics::Surface *> cache;
    std::string key=std::to_string(width)+":"+(accent?"a":enabled?"n":"d")+text.c_str();
    auto found=cache.find(key);Graphics::Surface *ink=nullptr;
    if(found!=cache.end())ink=found->second;
    else{
        if(cache.size()>256){for(auto &p:cache){p.second->free();delete p.second;}cache.clear();}
        Graphics::Surface scratch;scratch.create(MAX(1,width-4)*kMaskScale,256,dest.format);memset(scratch.getPixels(),0,scratch.pitch*scratch.h);
        int size=fonts->getSizePercent(),font=charset->getCurID();fonts->setSizePercent(55);charset->setCurID(3);
        const auto *nut=dynamic_cast<const CharsetRendererNut *>(charset);int x100=0;
        for(unsigned i=0;i<text.size();++i){byte ch=text[i];if(x100/100>=scratch.w)break;
            fonts->drawChar(3,ch,scratch,x100/100,0,enabled?245:135,accent?220:enabled?239:145,accent?145:enabled?225:148);
            x100+=(nut?nut->getCharWidth100(ch):charset->getCharWidth(ch)*100)*kMaskScale;
        }
        charset->setCurID(font);fonts->setSizePercent(size);
        int first=scratch.h,last=0,right=0;
        for(int y=0;y<scratch.h;++y)for(int x=0;x<scratch.w;++x)if((*(const uint32 *)scratch.getBasePtr(x,y)>>dest.format.aShift)&255){first=MIN(first,y);last=MAX(last,y+1);right=MAX(right,x+1);}
        ink=new Graphics::Surface();ink->create(MAX(1,right),MAX(1,last-first),dest.format);memset(ink->getPixels(),0,ink->pitch*ink->h);
        if(last>first)for(int y=first;y<last;++y)memcpy(ink->getBasePtr(0,y-first),scratch.getBasePtr(0,y),right*4);
        scratch.free();cache[key]=ink;
    }
    if(plate){Common::Rect rect(left*kMaskScale,top*kMaskScale,(left+4)*kMaskScale+ink->w,(top+height)*kMaskScale);rect.clip(Common::Rect(dest.w,dest.h));dest.fillRect(rect,dest.format.ARGBToColor(235,18,28,32));}
    int x0=(left+2)*kMaskScale,y0=top*kMaskScale+MAX(0,(height*kMaskScale-ink->h)/2);
    for(int y=0;y<ink->h&&y<height*kMaskScale;++y)for(int x=0;x<ink->w;++x){
        int dx=x0+x,dy=y0+y;if(dx<0||dy<0||dx>=dest.w||dy>=dest.h)continue;
        uint32 pixel=*(const uint32 *)ink->getBasePtr(x,y);if((pixel>>dest.format.aShift)&255)*(uint32 *)dest.getBasePtr(dx,dy)=pixel;
    }
}
}
bool ScummEngine::hdMasksAvailable() {
    return _game.id==GID_CMI && ConfMan.hasKey("hd_scene_masks_path") && playtestReadyForJump() && !hdInventoryOpen() && !isPaused() && _hdComposite.getPixels() && _hdFontManager && _hdFontManager->hasFont(3);
}
bool ScummEngine::hdMasksApply(const HdMasks::Document &next,bool history) {
    using namespace HdMasks;auto &s=state();auto *d=s.draft();if(!d)return false;
    if(!validate(next,s.error))return false;
    const bool walk=!sameWalk(next,d->live);
    if(!walk&&sameWater(next.water,d->live.water)&&sameForeground(next,d->live)&&next.animations==d->live.animations&&next.animationMasks==d->live.animationMasks){s.error.clear();return true;}
    if(walk) {
        for(const auto &b:next.boxes){const auto *base=find(d->base,b.id);if((!base||b.points!=base->points)&&!validWalk(b.points,base?&base->points:nullptr)){s.error="Walkboxes must be convex and cannot cross";return false;}}
        // Preserve existing portals during reshaping. Explicit delete can disconnect an area.
        for(unsigned i=1;i<d->live.boxes.size();++i)for(unsigned j=i+1;j<d->live.boxes.size();++j){auto &a=d->live.boxes[i];auto &b=d->live.boxes[j];auto *na=find(next,a.id);auto *nb=find(next,b.id);
            if(na&&nb&&!a.disabled&&!b.disabled&&!na->disabled&&!nb->disabled&&((adjacent(a.points,b.points)&&!adjacent(na->points,nb->points))||(hdMasksConnected(a.id,b.id)&&touching(a.points,b.points)&&!touching(na->points,nb->points)))){s.error="Keep adjoining walkboxes connected (shared horizontal/vertical edge)";return false;}}
        for(int i=1;i<_numActors;++i){Actor *a=_actors[i];if(!a||a->_room!=_currentRoom||!a->_visible||a->_ignoreBoxes)continue;
            Point p(a->getRealPos().x,a->getRealPos().y);bool was=false,now=false;
            for(auto &b:d->live.boxes)if(b.id&&!b.disabled&&!(getBoxFlags(b.id)&kBoxInvisible)&&inside(b.points,p))was=true;
            for(auto &b:next.boxes)if(b.id&&!b.disabled&&!(getBoxFlags(b.id<(int)d->base.boxes.size()?b.id:b.parent)&kBoxInvisible)&&inside(b.points,p))now=true;
            if(was&&!now){s.error="Move the actor out of this area before changing it";return false;}
        }
    }
    if(walk)hdMasksTrimExtras(next.boxes.size());
    if(history)d->commit(next);else d->live=next;changed(*d);
    if(walk)for(int i=1;i<_numActors;++i){Actor *a=_actors[i];if(!a||a->_room!=_currentRoom||!a->_visible||a->_ignoreBoxes)continue;
        const auto position=a->getRealPos();int selected=-1;for(auto &b:d->live.boxes)if(b.id&&!b.disabled&&!(getBoxFlags(b.id)&kBoxInvisible)&&inside(b.points,{(double)position.x,(double)position.y})){selected=b.id;break;}
        bool moving=a->_moving!=0;auto destination=a->hdMasksDestination();int direction=a->hdMasksDirection();
        if(selected>=0){a->stopActorMoving();a->_walkbox=selected;if(moving)a->startWalkActor(destination.x,destination.y,direction);}
    }
    s.error.clear();hdMasksRedrawActors();return true;
}
void ScummEngine::hdMasksTick() {
    auto &s=HdMasks::state();
    static int command=-1; if(command!=_playtestCommandId){command=_playtestCommandId;s.room=-1;}
    hdMasksSync();
    hdHeadTick();hdAnimationsTick();
    // Save files contain native IDs. Reattach actors to authored areas after
    // room entry / restore, without serializing authoring state into the save.
    static int attached=-1;
    auto *draft=s.draft();
    if(attached!=s.revision && draft && s.room==_currentRoom) {
        attached=s.revision;
        if(draft->walkChanged)for(int i=1;i<_numActors;++i){Actor *a=_actors[i];if(!a||!a->_visible||a->_room!=_currentRoom||a->_ignoreBoxes)continue;
            const auto position=a->getRealPos();HdMasks::Point p(position.x,position.y);
            const auto *current=HdMasks::find(draft->live,a->_walkbox);
            if(current&&!current->disabled&&HdMasks::inside(current->points,p))continue;
            for(auto &box:draft->live.boxes)if(box.id&&!box.disabled&&!(getBoxFlags(box.id)&kBoxInvisible)&&HdMasks::inside(box.points,p)){
                bool moving=a->_moving!=0;auto destination=a->hdMasksDestination();int direction=a->hdMasksDirection();
                a->stopActorMoving();a->_walkbox=box.id;if(moving)a->startWalkActor(destination.x,destination.y,direction);break;
            }
        }
    }
    if(!s.open)return;
    if(!hdMasksAvailable()){s.animationMaskDrag=false;if(s.bypassForeground)hdMasksRedrawActors();s.clipPan=false;s.drag=s.pending=s.adding=s.bypassForeground=s.rectangleDrag=false;s.clipTool=0;s.creation.clear();HdRemaster::state().maskEditing=false;HdRemaster::state().maskVisible=false;return;}
    _fullRedraw=true;
    if(s.pending){s.pending=false;hdMasksApply(s.preview,true);}
}
void ScummEngine::hdMasksAction(int action) {
    using namespace HdMasks;auto &s=state();auto *d=s.draft();if(!d)return;
    if(action==74){s.panelOpacity=s.panelOpacity==80?35:s.panelOpacity+15;++s.uiRevision;return;}
    if(action>=65&&action<=75){hdAnimationMaskAction(action);return;}
    if(action>=57&&action<=60){hdSpriteFrameAction(action);return;}
    if(action>=48&&action<=56){hdAnimationsAction(action);return;}
    s.animationDrag=s.animationMaskDrag=false;
    if(action==38){s.moreOptions=!s.moreOptions;++s.uiRevision;return;}
    if(action==39){s.menuBottom=!s.menuBottom;++s.uiRevision;return;}
    if(action>=40&&action<=46){
        if(s.pending){s.pending=false;if(!hdMasksApply(s.preview,true))return;}
        s.drag=s.rectangleDrag=s.clipPan=false;s.test=false;s.error.clear();
        if(action==40){s.clipOutline=!s.clipOutline;s.creation.clear();s.adding=s.clipOutline&&s.clipTool;s.addHole=s.clipTool==2;}
        if(action==41){if(!HdRemaster::state().active){s.error="Zoom requires the OpenGL scene renderer";return;}s.clipView.at({maskCanvasWidth()/2.0,240},s.clipView.zoom==4?1:s.clipView.zoom*2,maskCanvasWidth());}
        if(action==42)s.clipStep=s.clipStep==1?.25:1;
        if(action==43)s.clipFill=s.clipFill==80?25:s.clipFill==25?0:80;
        if(action==44){s.clipInsert=!s.clipInsert;s.clipTool=0;s.adding=false;s.creation.clear();}
        if(action==45){Document next=d->live;auto *ring=maskSelected(next);if(ring&&s.node>=0&&s.node<(int)ring->size()&&ring->size()>3){ring->erase(ring->begin()+s.node);s.preview=next;s.pending=true;s.node=-1;}else s.error="Select a point; an outline needs at least three points";}
        if(action==46)s.clipView=EditView();
        ++s.uiRevision;hdMasksRedrawActors();return;
    }
    s.clipInsert=s.clipPan=false;
    if(s.pending){s.pending=false;if(!hdMasksApply(s.preview,true))return;}
    s.drag=s.rectangleDrag=false;s.creation.clear();s.adding=false;
    if(s.headTab&&(action==6||action==10||action==11||action==13||(action>=30&&action<=37))){hdHeadAction(action);return;}
    HdHead::state().drag=HdHead::state().original=false;
    Document next=d->live;
    if(s.foregroundTab&&_gdi->_numZBuffer<=1&&(action==7||action==8||action==15||action==23||action==27||action==28)){s.error="This room has no foreground depth planes";++s.uiRevision;return;}
    switch(action) {
    case 0:case 1:case 18:
        s.animationsTab=false;s.headTab=false;
        s.waterTab=action==1;s.foregroundTab=action==18;s.bypassForeground=false;s.test=false;s.clipTool=0;
        s.showWalk=action==0;s.showWater=action==1;s.showForeground=action==18;s.selected=s.node=-1;
        s.error.clear();
        if(s.foregroundTab){s.planeCount=MAX(0,_gdi->_numZBuffer-1);s.plane=MIN(MAX(1,s.plane),MAX(1,s.planeCount));
            Actor *ego=VAR_EGO!=0xff&&VAR(VAR_EGO)<_numActors?_actors[VAR(VAR_EGO)]:nullptr;
            if(ego)for(auto &draw:ego->_quiverDraws)if(draw.z>0&&draw.z<=s.planeCount){s.plane=draw.z;break;}}
        break;
    case 64:{
        s.open=false;s.bypassForeground=false;
        auto &look=hdColorGradeState();if(!look.loaded)hdLoadColorGrades(look);
        look.panel=look.shadowPage=true;look.waterPage=look.filmPage=look.editGlobal=look.shadowBypass=false;look.row=0;
        break;}
    case 47:
        s.animationsTab=true;s.headTab=s.waterTab=s.foregroundTab=s.test=false;s.bypassForeground=false;
        s.showWalk=s.showWater=s.showForeground=false;s.selected=s.node=-1;s.clipTool=0;s.error.clear();break;
    case 29:
        s.animationsTab=false;s.headTab=true;s.waterTab=s.foregroundTab=s.test=false;s.bypassForeground=false;
        s.showWalk=s.showWater=s.showForeground=false;s.selected=s.node=-1;s.clipTool=0;s.error.clear();break;
    case 2:s.showWalk=!s.showWalk;break;
    case 3:s.showWater=!s.showWater;break;
    case 4:s.test=!s.test;break;
    case 5:s.open=false;s.bypassForeground=false;break;
    case 6:s.test=false;s.clipTool=0;s.error.clear();if(s.foregroundTab){s.showForeground=true;s.bypassForeground=false;hdMasksTraceForeground(next);}break; // Select also leaves Test mode.
    case 7:case 8:
        s.test=false;s.clipTool=0;
        if(s.foregroundTab)s.bypassForeground=false;
        if(!maskPolygon()&&(!find(next,s.selected)||s.selected==0)){s.error="Select a walkbox to inherit scale and depth";break;}
        if(!maskPolygon()&&next.boxes.size()>=255){s.error="Walkbox ID limit reached";break;}
        if(action==8&&!maskPolygon()){s.error="Cutouts are available on Water and Foreground";break;}
        s.adding=true;s.addHole=action==8;s.error=maskPolygon()?"Click corners, then Enter to finish. Escape cancels.":"Click 4 corners touching an existing green area. Escape cancels.";break;
    case 27:case 28:
        s.test=false;s.bypassForeground=false;s.clipTool=action==27?1:2;s.selected=s.node=-1;s.error.clear();
        if(s.clipOutline){s.adding=true;s.addHole=action==28;}break;
    case 9:
        if(s.selected<0)break;
        if(s.foregroundTab)deleteForegroundRing(foreground(next,s.plane),s.selected,s.hole);
        else if(maskPolygon()){auto &rings=maskRings(next,s.hole);if(s.selected<(int)rings.size())rings.erase(rings.begin()+s.selected);maskAuthored(next);}
        else{auto *b=find(next,s.selected);if(b&&b->id)b->disabled=true;}
        s.preview=next;s.pending=true;s.selected=s.node=-1;break;
    case 10:case 11:{auto &src=action==10?d->undo:d->redo;auto &dst=action==10?d->redo:d->undo;if(!src.empty()){Document previous=d->live,target=src.back();if(hdMasksApply(target,false)){src.pop_back();dst.push_back(previous);}}s.selected=s.node=-1;break;}
    case 12:save(s.headTab);break;
    case 13:s.preview=d->saved;s.pending=true;s.selected=s.node=-1;break;
    case 14:s.preview=d->base;s.pending=true;s.selected=s.node=-1;break;
    case 15:{
        if(s.foregroundTab){s.test=false;s.clipTool=0;s.showForeground=true;s.bypassForeground=false;hdMasksTraceForeground(next);break;}
        if(!s.waterTab){s.error="Select Water to convert coverage";break;}
        if(next.water.authored){s.error="This water mask already has editable outlines";break;}
        auto &r=HdRemaster::state();auto &surface=hdWaterSurface();
        if(!r.water){s.error="Enable the water shader before converting its coverage";break;}
        if((s.room==10||s.room==11)&&surface.valid&&surface.room==s.room)next.water=contours(surface.depth.data(),surface.width,surface.height,surface.width);
        else if(r.waterCoverage.getPixels()){
            const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
            std::vector<byte> pixels(rw*rh,0);int ox=r.backgroundX/MAX(1,r.scale),oy=r.backgroundY/MAX(1,r.scale);
            for(int y=0;y<r.waterCoverage.h;++y)for(int x=0;x<r.waterCoverage.w;++x)if(x+ox>=0&&x+ox<rw&&y+oy>=0&&y+oy<rh)pixels[(y+oy)*rw+x+ox]=*(const byte *)r.waterCoverage.getBasePtr(x,y);
            next.water=contours(pixels.data(),rw,rh,rw);
        }else{s.error="No current water coverage to convert";break;}
        if(next.water.zones.empty()){s.error="No current water coverage to convert";break;}
        if(s.widePainting)for(auto *rings:{&next.water.zones,&next.water.holes})for(auto &ring:*rings)for(auto &point:ring)point.x=(point.x*640/1000+107)*1000/854;
        s.preview=next;s.pending=true;s.selected=s.node=-1;break;}
    case 16:if(s.waterTab){next.water.palette=next.water.palette=="any"?d->base.water.palette:"any";next.water.authored=true;s.preview=next;s.pending=true;}break;
    case 17:if(!maskPolygon()){auto *b=find(next,s.selected);if(b){b->disabled=false;s.preview=next;s.pending=true;}}break;
    case 26:{
        auto *ring=maskSelected(next);if(!ring){s.error="Select a foreground outline to simplify its corners";break;}
        *ring=simplifyRing(*ring);s.preview=next;s.pending=true;s.node=-1;break;}
    case 61:case 62:{
        s.test=false;s.clipTool=0;s.showForeground=true;s.bypassForeground=false;s.node=-1;s.error.clear();
        const auto *f=foreground(static_cast<const Document &>(next),s.plane);
        int zones=f?f->zones.size():0,holes=f?f->holes.size():0,total=zones+holes;
        if(!total){hdMasksTraceForeground(next);break;}
        int index=s.selected<0?(action==61?0:-1):s.selected+(s.hole?zones:0);
        index=(index+total+(action==61?-1:1))%total;s.hole=index>=zones;s.selected=s.hole?index-zones:index;
        break;}
    case 19:s.showForeground=!s.showForeground;break;
    case 20:s.showConnections=!s.showConnections;break;
    case 25:s.showBlocked=!s.showBlocked;break;
    case 21:case 22:
        s.planeCount=MAX(0,_gdi->_numZBuffer-1);
        if(s.planeCount)s.plane=(s.plane-1+s.planeCount+(action==21?-1:1))%s.planeCount+1;
        s.selected=s.node=-1;s.bypassForeground=false;s.clipTool=0;s.test=false;s.showForeground=true;s.error.clear();break;
    case 23:s.bypassForeground=!s.bypassForeground;break;
    case 24:
        next.foreground.erase(std::remove_if(next.foreground.begin(),next.foreground.end(),[&](const Foreground &f){return f.plane==s.plane;}),next.foreground.end());
        s.preview=next;s.pending=true;s.selected=s.node=-1;s.bypassForeground=false;break;
    }
    ++s.uiRevision;hdMasksRedrawActors();
}
bool ScummEngine::handleHDMasksEvent(const Common::Event &event) {
    using namespace HdMasks;auto &s=state();
    const bool key=event.type==Common::EVENT_KEYDOWN,upkey=event.type==Common::EVENT_KEYUP;
    int code=key||upkey?event.kbd.keycode:-1;bool index=code>=0&&code<512;
    unsigned down=event.type==Common::EVENT_LBUTTONDOWN?1:event.type==Common::EVENT_RBUTTONDOWN?2:event.type==Common::EVENT_MBUTTONDOWN?4:event.type==Common::EVENT_X1BUTTONDOWN?8:event.type==Common::EVENT_X2BUTTONDOWN?16:0;
    unsigned up=event.type==Common::EVENT_LBUTTONUP?1:event.type==Common::EVENT_RBUTTONUP?2:event.type==Common::EVENT_MBUTTONUP?4:event.type==Common::EVENT_X1BUTTONUP?8:event.type==Common::EVENT_X2BUTTONUP?16:0;
    if(key||down||(event.type==Common::EVENT_MOUSEMOVE&&(s.drag||s.adding)))++s.uiRevision;
    if(upkey&&index&&s.keys[code]){s.keys[code]=false;return true;}
    if(up&&(s.buttons&up)){s.buttons&=~up;if(s.clipPan){s.clipPan=false;return true;}if(s.animationMaskDrag)return handleHDAnimationMaskEvent(event);if(s.animationDrag)return handleHDAnimationsEvent(event);if(HdHead::state().drag)return handleHDHeadEvent(event);if(s.drag){s.drag=false;s.pending=hdMasksAvailable();
        if(s.rectangleDrag){auto *ring=maskSelected(s.preview);if(!ring||!simple(*ring)){s.pending=false;s.selected=s.node=-1;s.error="Click and drag to draw a rectangle. Escape cancels.";}
            else s.clipTool=0;s.rectangleDrag=false;s.creation.clear();}
    }return true;}
    if(key&&code==Common::KEYCODE_m&&!(event.kbd.flags&(Common::KBD_CTRL|Common::KBD_ALT|Common::KBD_META|Common::KBD_SHIFT))){
        if(index)s.keys[code]=true;if(event.kbdRepeat)return true;
        if(s.open){if(s.pending){s.pending=false;hdMasksApply(s.preview,true);}s.open=false;s.bypassForeground=false;hdMasksRedrawActors();}else if(hdMasksAvailable()){
            hdMasksSync();s.open=true;s.test=false;hdColorGradeState().panel=false;_hdSceneJump.close();
            _leftBtnPressed=_rightBtnPressed=0;_keyPressed=Common::KeyState();memset(_keyDownMap,0,sizeof(_keyDownMap));memset(_actionMap,0,sizeof(_actionMap));
        }
        s.animationDrag=s.animationMaskDrag=false;s.drag=s.pending=s.adding=s.rectangleDrag=s.clipPan=s.clipInsert=false;s.clipTool=0;s.creation.clear();HdHead::state().drag=HdHead::state().original=false;_fullRedraw=true;return true;
    }
    if(!s.open||!hdMasksAvailable())return false;
    hdMasksSync();auto *d=s.draft();if(!d)return false;
    if(s.pending&&(key||down)){s.pending=false;hdMasksApply(s.preview,true);}
    Common::Point panel=maskPanelPosition();Point mouse(s.rawX,s.rawY);
    if(down){
        for(auto &control:maskControls())if(mouse.x>=control.x&&mouse.x<control.x+control.w&&mouse.y>=control.y&&mouse.y<control.y+control.h){s.buttons|=down;if(down==1)hdMasksAction(maskButtonAction(control.slot));return true;}
        if(mouse.x>=panel.x&&mouse.x<panel.x+maskPanelWidth()&&mouse.y>=panel.y&&mouse.y<panel.y+maskPanelHeight()){s.buttons|=down;return true;}
    }
    if(key&&code==Common::KEYCODE_t){if(index)s.keys[code]=true;hdMasksAction(4);return true;}
    if(key&&code==Common::KEYCODE_h){if(index)s.keys[code]=true;hdMasksAction(29);return true;}
    if(s.test)return false;
    if(key&&index)s.keys[code]=true;
    if(s.headTab)return handleHDHeadEvent(event);
    if(s.foregroundTab||(s.animationsTab&&s.animationMaskEdit)){
        if(s.clipPan&&event.type==Common::EVENT_MOUSEMOVE){s.clipView.focus={s.panFocus.x-(mouse.x-s.panStart.x)/s.clipView.zoom,s.panFocus.y-(mouse.y-s.panStart.y)/s.clipView.zoom};s.clipView.constrain(maskCanvasWidth());++s.uiRevision;return true;}
        if((down==4||(down==1&&s.keys[Common::KEYCODE_SPACE]))&&maskZoomed()&&s.clipView.zoom>1){s.buttons|=down;s.clipPan=true;s.panStart=mouse;s.panFocus=s.clipView.focus;return true;}
        if(event.type==Common::EVENT_WHEELUP||event.type==Common::EVENT_WHEELDOWN){if(!s.drag&&!s.animationMaskDrag&&!s.clipPan&&maskZoomed()){
            double zoom=std::max(1.0,std::min(4.0,s.clipView.zoom*(event.type==Common::EVENT_WHEELUP?2:.5)));s.clipView.at(mouse,zoom,maskCanvasWidth());++s.uiRevision;
        }return true;}
        if(key&&code==Common::KEYCODE_0){hdMasksAction(46);return true;}
    }
    if(s.animationsTab)return handleHDAnimationsEvent(event);
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    Point p=maskView(mouse,s.waterTab,true,rw,rh);
    if(s.waterTab){p.x=std::max(0.0,std::min(1000.0,p.x));p.y=std::max(0.0,std::min(1000.0,p.y));}
    else if(!s.foregroundTab){p.x=std::round(p.x);p.y=std::round(p.y);}
    else{p.x=std::max(0.0,std::min(double(rw),p.x));p.y=std::max(0.0,std::min(double(rh),p.y));}
    if(s.drag&&event.type==Common::EVENT_MOUSEMOVE){
        if(s.rectangleDrag){s.preview=d->live;maskClipRectangle(s.preview,p);_fullRedraw=true;return true;}
        s.preview=d->live;auto *ring=maskSelected(s.preview);if(ring&&s.node>=0&&s.node<(int)ring->size()){
            // Preserve the grab offset: a click inside the handle's generous
            // hit target selects it without snapping the corner to the cursor.
            Point target(s.dragNode.x+p.x-s.dragStart.x,s.dragNode.y+p.y-s.dragStart.y);
            if(s.foregroundTab){double speed=(_system->getEventManager()->getModifierState()&Common::KBD_SHIFT)?0.1:1;
                target={s.dragNode.x+(p.x-s.dragStart.x)*speed,s.dragNode.y+(p.y-s.dragStart.y)*speed};s.dragStart=p;s.dragNode=target;}
            if(maskPolygon()){(*ring)[s.node]=target;maskAuthored(s.preview);}else moveShared(s.preview,s.selected,s.node,target);
        }_fullRedraw=true;return true;
    }
    if(down) {
        s.buttons|=down;if(down!=1)return true;
        if(s.foregroundTab&&(s.clipInsert||(_system->getEventManager()->getModifierState()&Common::KBD_CTRL))&&!s.adding){Document next=d->live;maskInsertEdge(maskNearestEdge(next,mouse,rw,rh),next);return true;}
        if(s.foregroundTab&&s.clipTool&&!s.clipOutline&&!s.adding){s.creation={p};s.rectangleDrag=s.drag=true;s.node=-1;s.preview=d->live;maskClipRectangle(s.preview,p);s.error.clear();_fullRedraw=true;return true;}
        if(s.adding){
            if(!maskPolygon()) { // Snap to existing corners in display pixels.
                double best=8;for(auto &b:d->live.boxes)for(auto candidate:b.points){double dist=distance(maskView(candidate,false,false,rw,rh),mouse);if(dist<best){best=dist;p=candidate;}}
            }
            s.creation.push_back(p);
            if(!maskPolygon()&&s.creation.size()==4){Document next=d->live;HdMasks::Box box;box.id=next.boxes.size();box.parent=s.selected;box.points=s.creation;
                const auto *parent=find(d->live,s.selected);if(parent)box.parent=parent->parent;
                bool connected=false;for(auto &b:next.boxes)if(!b.disabled&&adjacent(b.points,box.points))connected=true;
                if(!connected)s.error="New walkbox needs a shared horizontal or vertical edge";
                else{next.boxes.push_back(box);s.preview=next;s.pending=true;s.selected=box.id;}
                s.creation.clear();s.adding=false;
            }_fullRedraw=true;return true;
        }
        double best=s.foregroundTab?7:10;s.node=-1;int selected=-1;bool hole=false;
        auto scan=[&](const Ring &ring,int id,bool isHole){if(s.selected>=0&&(id!=s.selected||(maskPolygon()&&isHole!=s.hole)))return;for(unsigned i=0;i<ring.size();++i){double dist=distance(maskView(ring[i],s.waterTab,false,rw,rh),mouse);if(dist<best){best=dist;selected=id;s.node=i;hole=isHole;}}};
        if(maskPolygon()){for(bool hole:{false,true}){auto &rings=maskRings(static_cast<const Document &>(d->live),hole);for(unsigned i=0;i<rings.size();++i)scan(rings[i],i,hole);}}
        else {
            // Prefer the selected area's handles where corners overlap, then
            // allow grabbing any visible area's corner in a single gesture.
            for(auto &b:d->live.boxes)if(b.id==s.selected)scan(b.points,b.id,false);
            if(selected<0){int previous=s.selected;s.selected=-1;
                for(auto &b:d->live.boxes)if(b.id&&(s.showBlocked||(!b.disabled&&!(getBoxFlags(b.id)&kBoxInvisible))))scan(b.points,b.id,false);
                s.selected=previous;
            }
        }
        if(s.foregroundTab){int previous=s.selected;s.selected=-1;
            for(bool cut:{false,true}){auto &rings=maskRings(static_cast<const Document &>(d->live),cut);for(unsigned i=0;i<rings.size();++i)scan(rings[i],i,cut);}s.selected=previous;}
        if(selected>=0){s.selected=selected;s.hole=hole;s.drag=true;s.preview=d->live;s.error.clear();s.dragStart=p;s.dragNode=(*maskSelected(s.preview))[s.node];}
        else {
            if(s.foregroundTab){s.selected=-1;auto edge=maskNearestEdge(d->live,mouse,rw,rh);
                if(edge.shape>=0){s.selected=edge.shape;s.hole=edge.hole;}
                else{const auto *f=foreground(static_cast<const Document &>(d->live),s.plane);
                    if(f)eachForeground(*f,[&](const Ring &ring,bool hole){if(inside(ring,p)){const auto &rings=hole?f->holes:f->zones;s.selected=&ring-rings.data();s.hole=hole;}});}
                if(s.selected<0)s.error="No editable points here yet. Click Edit nodes, or try another clip layer.";}
            else if(maskPolygon()){for(bool hole:{false,true}){auto &rings=maskRings(static_cast<const Document &>(d->live),hole);for(unsigned i=0;i<rings.size();++i)if(inside(rings[i],p)){s.selected=i;s.hole=hole;}}}
            else{int hit=-1;for(auto &b:d->live.boxes)if(b.id&&inside(b.points,p)&&(!b.disabled&&!(getBoxFlags(b.id)&kBoxInvisible)))hit=b.id;
                if(hit<0&&s.showBlocked)for(auto &b:d->live.boxes)if(b.id&&inside(b.points,p))hit=b.id;
                s.selected=hit;}
        }
        _fullRedraw=true;return true;
    }
    if(key) {
        if(code==Common::KEYCODE_ESCAPE){if(s.drag||s.adding||s.clipTool||s.clipInsert||s.clipPan){if(s.rectangleDrag)s.selected=s.node=-1;s.drag=s.adding=s.rectangleDrag=s.clipPan=s.clipInsert=false;s.clipTool=0;s.creation.clear();s.error.clear();}else {s.open=false;s.bypassForeground=false;hdMasksRedrawActors();}}
        else if(code==Common::KEYCODE_TAB)hdMasksAction(s.foregroundTab?29:s.waterTab?18:1);
        else if(code==Common::KEYCODE_t)hdMasksAction(4);
        else if(code==Common::KEYCODE_s&&(event.kbd.flags&Common::KBD_CTRL))hdMasksAction(12);
        else if(code==Common::KEYCODE_s&&s.foregroundTab)hdMasksAction(26);
        else if(code==Common::KEYCODE_p&&s.foregroundTab)hdMasksAction(s.clipTool==2?8:7);
        else if(code==Common::KEYCODE_z&&(event.kbd.flags&Common::KBD_CTRL))hdMasksAction(event.kbd.flags&Common::KBD_SHIFT?11:10);
        else if(code==Common::KEYCODE_RETURN&&s.adding&&maskPolygon()){Document next=d->live;if(s.foregroundTab)addForegroundRing(foreground(next,s.plane),s.creation,s.addHole);else maskRings(next,s.addHole).push_back(s.creation);maskAuthored(next);s.selected=maskRings(next,s.addHole).size()-1;s.hole=s.addHole;s.node=-1;s.preview=next;s.pending=true;s.adding=false;s.clipTool=0;s.creation.clear();}
        else if((code==Common::KEYCODE_INSERT||code==Common::KEYCODE_e)&&s.foregroundTab){Document next=d->live;maskInsertEdge(maskNearestEdge(next,mouse,rw,rh),next);}
        else if((code==Common::KEYCODE_INSERT||code==Common::KEYCODE_e)&&maskPolygon()){Document next=d->live;auto *ring=maskSelected(next);if(ring){double nearest=1e9;int edge=-1;Point inserted;for(unsigned i=0;i<ring->size();++i){Point a=(*ring)[i],b=(*ring)[(i+1)%ring->size()];double len=(b.x-a.x)*(b.x-a.x)+(b.y-a.y)*(b.y-a.y);double t=len?std::max(0.0,std::min(1.0,((p.x-a.x)*(b.x-a.x)+(p.y-a.y)*(b.y-a.y))/len)):0;Point q(a.x+t*(b.x-a.x),a.y+t*(b.y-a.y));double dist=distance(q,p);if(dist<nearest){nearest=dist;edge=i;inserted=q;}}if(edge>=0){ring->insert(ring->begin()+edge+1,inserted);maskAuthored(next);s.preview=next;s.pending=true;s.node=edge+1;}}}
        else if(code==Common::KEYCODE_DELETE||code==Common::KEYCODE_BACKSPACE){if(maskPolygon()&&s.node>=0){Document next=d->live;auto *ring=maskSelected(next);if(ring&&ring->size()>3&&s.node<(int)ring->size()){ring->erase(ring->begin()+s.node);maskAuthored(next);s.preview=next;s.pending=true;s.node=-1;}}else hdMasksAction(9);}
        else if(code==Common::KEYCODE_LEFT||code==Common::KEYCODE_RIGHT||code==Common::KEYCODE_UP||code==Common::KEYCODE_DOWN){Document next=d->live;auto *ring=maskSelected(next);if(ring&&s.node>=0&&s.node<(int)ring->size()){Point q=(*ring)[s.node];double step=(s.foregroundTab?s.clipStep:1)*(event.kbd.flags&Common::KBD_SHIFT?5:1);q.x+=code==Common::KEYCODE_LEFT?-step:code==Common::KEYCODE_RIGHT?step:0;q.y+=code==Common::KEYCODE_UP?-step:code==Common::KEYCODE_DOWN?step:0;if(maskPolygon()){(*ring)[s.node]=q;maskAuthored(next);}else moveShared(next,s.selected,s.node,q);s.preview=next;s.pending=true;}}
        _fullRedraw=true;return true;
    }
    return up||upkey||event.type==Common::EVENT_MOUSEMOVE||event.type==Common::EVENT_WHEELUP||event.type==Common::EVENT_WHEELDOWN||event.type==Common::EVENT_CUSTOM_ENGINE_ACTION_START||event.type==Common::EVENT_CUSTOM_ENGINE_ACTION_END;
}
void ScummEngine::drawHDMasks() {
    using namespace HdMasks;auto &s=state();auto &r=HdRemaster::state();
    r.maskVisible=s.open&&hdMasksAvailable();r.maskEditing=r.maskVisible&&!s.test;
    r.maskZoom=maskZoomed()?s.clipView.zoom:1;r.maskFocusX=s.clipView.focus.x;r.maskFocusY=s.clipView.focus.y;
    if(!r.maskVisible)return;
    hdMasksSync();auto *d=s.draft();if(!d)return;
    s.planeCount=MAX(0,_gdi->_numZBuffer-1);s.plane=MIN(MAX(1,s.plane),MAX(1,s.planeCount));
    auto &image=r.maskOverlay;const int width=maskCanvasWidth(),rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    static Common::String previous;static uint32 generatedAt=0;
    Common::String cache=Common::String::format("%s:%d:%d:%d:%d:%d:%d:%d:%s",s.key.c_str(),s.revision,s.uiRevision,r.backgroundX,r.backgroundY,r.drawableWidth,r.drawableHeight,width,s.error.c_str());
    const uint32 now=_system->getMillis();
    // Live actors, script-controlled box flags and object depth masks can change
    // without an edit. Refresh those diagnostics at 10 Hz as gameplay continues.
    if(cache==previous&&now-generatedAt<100)return;
    previous=cache;generatedAt=now;++r.maskGeneration;
    HdRemaster::resize(image,width*kMaskScale,480*kMaskScale);memset(image.getPixels(),0,image.pitch*image.h);
    const Document &doc=s.drag?s.preview:d->live;
    auto project=[&](Point p,bool water){return maskView(p,water,false,rw,rh);};
    auto fillPixel=[&](int x,int y,byte red,byte green,byte blue,byte alpha){for(int a=0;a<kMaskScale;++a)for(int b=0;b<kMaskScale;++b)maskPixel(image,x*kMaskScale+a,y*kMaskScale+b,red,green,blue,alpha);};
    auto label=[&](Point p,const Common::String &text){maskText(image,_hdFontManager,_charset,text,(int)p.x,(int)p.y,14+text.size()*6,14,true,true);};
    const int activeLayer=s.animationsTab?4:s.headTab?3:s.foregroundTab?2:s.waterTab?1:0;
    auto outline=[&](const Ring &ring,int layer,int id,bool hole,bool disabled){
        const bool water=layer==1,selected=layer==activeLayer&&id==s.selected&&(layer==0||hole==s.hole);
        byte red=disabled?160:hole?255:layer==2?220:water?55:100,green=disabled?160:hole?160:layer==2?120:water?175:240,blue=disabled?160:hole?70:layer==2?255:water?255:145;
        if(layer==2&&hole){red=70;green=235;blue=170;}
        if(selected){red=255;green=225;blue=135;}
        Point center;for(auto p:ring){auto q=project(p,water);center.x+=q.x/ring.size();center.y+=q.y/ring.size();}
        if(layer==0){
            Ring view;for(unsigned i=0;i<ring.size();++i){Point a=ring[i],b=ring[(i+1)%ring.size()];for(int j=0;j<16;++j)view.push_back(project({a.x+(b.x-a.x)*j/16,a.y+(b.y-a.y)*j/16},false));}
            double left=width,right=0,top=480,bottom=0;for(auto q:view){left=std::min(left,q.x);right=std::max(right,q.x);top=std::min(top,q.y);bottom=std::max(bottom,q.y);}
            for(int y=MAX(0,(int)top);y<MIN(480,(int)bottom+1);++y)for(int x=MAX(0,(int)left);x<MIN(width,(int)right+1);++x)if(inside(view,{x+.5,y+.5}))fillPixel(x,y,red,green,blue,disabled?15:selected?65:30);
        }
        for(unsigned i=0;i<ring.size();++i){Point a=ring[i],b=ring[(i+1)%ring.size()];for(int j=0;j<16;++j){if(disabled&&(j&1))continue;maskLine(image,project({a.x+(b.x-a.x)*j/16,a.y+(b.y-a.y)*j/16},water),project({a.x+(b.x-a.x)*(j+1)/16,a.y+(b.y-a.y)*(j+1)/16},water),red,green,blue);}
            if((selected||(layer==0&&activeLayer==0)||(layer==2&&activeLayer==2))&&!s.test){Point q=project(a,water);bool current=selected&&(int)i==s.node;int radius=current?5:layer==2&&ring.size()>64?(selected?2:1):selected?4:3;
                for(int yy=-radius;yy<=radius;++yy)for(int xx=-radius;xx<=radius;++xx){bool rim=std::abs(xx)==radius||std::abs(yy)==radius;
                    fillPixel(int(q.x)+xx,int(q.y)+yy,current?255:rim?red:18,current?235:rim?green:28,current?180:rim?blue:32,255);}
                if(selected&&(layer==0||(layer==2&&(int)i==s.node)))label({q.x+6,q.y-14},Common::String::format("%d",i+1));
            }
        }
        if(center.x>=0&&center.x<width&&center.y>=0&&center.y<480)
            label(center,Common::String::format("%s%d%s",layer==0?(selected?"Area ":"#"):layer==2?(hole?"Show ":"Hide "):hole?"Cutout ":"Water ",id,disabled?" blocked":""));
    };
    if(s.showWater){
        const bool authoredWide=HdMasks::waterOverride(s.room)&&r.authoredWideWaterCoverage.getPixels();
        const Graphics::Surface &coverage=authoredWide?r.authoredWideWaterCoverage:r.voodooExterior?r.voodooWaterCoverage:r.plunderMap?r.plunderWaterCoverage:r.waterCoverage;
        if(r.water&&coverage.getPixels())for(int y=0;y<480;++y)for(int x=0;x<width;++x){int sx=authoredWide||r.voodooExterior||r.plunderMap?x*coverage.w/width:x-(width-r.viewportWidth)/2;int sy=y*coverage.h/480;
            if(sx>=0&&sx<coverage.w&&*(const byte *)coverage.getBasePtr(sx,sy))fillPixel(x,y,30,150,255,50);}
        for(unsigned i=0;i<doc.water.zones.size();++i)outline(doc.water.zones[i],1,i,false,false);
        for(unsigned i=0;i<doc.water.holes.size();++i)outline(doc.water.holes[i],1,i,true,false);
    }
    if(s.showForeground&&s.plane<=s.planeCount){
        const auto *f=foreground(doc,s.plane);
        const int fw=_screenWidth*kMaskScale,fh=_screenHeight*kMaskScale;
        std::vector<signed char> authored;if(s.clipFill)rasterForeground(authored,fw,fh,f,_virtscr[kMainVirtScreen].xstart,_screenTop,kMaskScale);
        for(int y=0;s.clipFill&&y<480;++y)for(int x=0;x<width;++x){
            Point p=maskView({x+.5,y+.5},false,true,rw,rh);
            int nx=int(p.x)-_virtscr[kMainVirtScreen].xstart,ny=int(p.y)-_screenTop;
            if(nx<0||nx>=_screenWidth||ny<0||ny>=_screenHeight)continue;
            int ax=int((p.x-_virtscr[kMainVirtScreen].xstart)*kMaskScale),ay=int((p.y-_screenTop)*kMaskScale);
            if(ax<0||ay<0||ax>=fw||ay>=fh)continue;
            int value=authored[ay*fw+ax];
            bool masked=value>=0?value!=0:HdObjectDepth::masked(getMaskBuffer(0,ny+_screenTop,s.plane),nx,_virtscr[kMainVirtScreen].xstart&7);
            if(masked)fillPixel(x,y,205,90,250,s.clipFill);
        }
        if(f){for(unsigned i=0;i<f->zones.size();++i)outline(f->zones[i],2,i,false,false);for(unsigned i=0;i<f->holes.size();++i)outline(f->holes[i],2,i,true,false);}
        if(s.clipInsert&&!s.test){auto edge=maskNearestEdge(doc,{double(s.rawX),double(s.rawY)},rw,rh);if(edge.shape>=0){auto q=project(edge.point,false);maskLine(image,{q.x-6,q.y},{q.x+6,q.y},255,245,160);maskLine(image,{q.x,q.y-6},{q.x,q.y+6},255,245,160);label({q.x+8,q.y-18},"Add point");}}
    }
    int actorBox=-1,actorPlane=0;
    Actor *ego=VAR_EGO!=0xff&&VAR(VAR_EGO)<_numActors?_actors[VAR(VAR_EGO)]:nullptr;
    if(ego&&ego->_room==_currentRoom){actorBox=ego->_walkbox;for(auto &draw:ego->_quiverDraws)actorPlane=MAX(actorPlane,draw.z);}
    if(s.showWalk){
        for(auto &b:doc.boxes)if(b.id){bool blocked=b.disabled||(getBoxFlags(b.id)&kBoxInvisible);if(!blocked||s.showBlocked||b.id==s.selected)outline(b.points,0,b.id,false,blocked);}
        if(activeLayer==0&&s.selected>0&&s.showConnections){auto *selected=find(doc,s.selected);if(selected){Point a;for(auto p:selected->points){a.x+=p.x/4;a.y+=p.y/4;}for(auto &b:doc.boxes)if(b.id!=s.selected&&!b.disabled&&hdMasksConnected(selected->id,b.id)){Point c;for(auto p:b.points){c.x+=p.x/4;c.y+=p.y/4;}maskLine(image,project(a,false),project(c,false),255,220,90);}}}
        if(ego&&ego->_room==_currentRoom){auto feet=ego->getRealPos();Point p=project({double(feet.x),double(feet.y+hdVoodooExteriorActorOffset(ego))},false);
            for(int i=0;i<24;++i){double a=i*6.283185/24,b=(i+1)*6.283185/24;maskLine(image,{p.x+7*std::cos(a),p.y+4*std::sin(a)},{p.x+7*std::cos(b),p.y+4*std::sin(b)},255,240,140);}
            label({p.x+10,p.y-20},Common::String::format("Feet: area %d",actorBox));}
    }
    if(s.adding){for(unsigned i=1;i<s.creation.size();++i)maskLine(image,project(s.creation[i-1],s.waterTab),project(s.creation[i],s.waterTab),255,255,255);if(!s.creation.empty())maskLine(image,project(s.creation.back(),s.waterTab),{(double)s.rawX,(double)s.rawY},255,255,255);}
    if(s.headTab)drawHDHead(image);
    if(s.animationsTab)drawHDAnimations(image);
    Common::Point panel=maskPanelPosition();
    const int panelWidth=maskPanelWidth();
    auto plate=[&](int x,int y,int w,int h,byte red,byte green,byte blue,byte alpha){Common::Rect rect(x*kMaskScale,y*kMaskScale,(x+w)*kMaskScale,(y+h)*kMaskScale);rect.clip(Common::Rect(image.w,image.h));image.fillRect(rect,image.format.ARGBToColor(alpha,red*alpha/255,green*alpha/255,blue*alpha/255));};
    plate(panel.x,panel.y,panelWidth,maskPanelHeight(),14,25,32,s.panelOpacity*255/100);
    s.controls=maskControls();
    for(const auto &control:s.controls){int action=maskButtonAction(control.slot);
        Common::String dynamicLabel;const char *text="";bool active=false,enabled=true;
        switch(action){
        case 0:text="Walk areas";active=activeLayer==0;break;case 1:text="Water";active=activeLayer==1;break;case 18:text="Clipping";active=activeLayer==2;break;
        case 4:text=s.test?"Edit [T]":"Play [T]";active=s.test;break;case 12:text=(s.headTab?HdHead::state().dirty():d->dirty)?"Save *":"Save";break;case 5:text="Close [M]";break;
        case 29:text="Head [H]";active=s.headTab;break;
        case 38:text=s.moreOptions?"Less options":"More options";active=s.moreOptions;break;
        case 39:text=s.menuBottom?"Menu to top":"Menu to bottom";break;
        case 40:text=s.clipOutline?"Shape: outline":"Shape: box";active=s.clipOutline;break;
        case 41:text=s.clipView.zoom==1?"Zoom: 1x":s.clipView.zoom==2?"Zoom: 2x":"Zoom: 4x";active=s.clipView.zoom>1;break;
        case 42:text=s.clipStep==1?"Nudge: 1px":"Nudge: 1/4px";active=s.clipStep<1;break;
        case 43:text=s.clipFill==80?"Fill: full":s.clipFill==25?"Fill: light":"Outlines only";active=s.clipFill<80;break;
        case 44:text="Add point";active=s.clipInsert;break;case 45:text="Delete point";enabled=s.node>=0;break;
        case 46:text="Reset view [0]";break;
        case 57:text=s.onion?"Onion: on":"Onion: off";active=s.onion;break;
        case 58:{bool frame=s.headTab?HdHead::state().frameMode:s.animationFrameMode;int cel=s.headTab?HdHead::state().frame:s.animationFrame;
            dynamicLabel=frame?Common::String::format("Edit: frame %d",cel):"Edit: whole sequence";text=dynamicLabel.c_str();active=frame;break;}
        case 59:text="< Frame";break;case 60:text="Frame >";break;
        case 65:text=s.animationMaskEdit?"Move sprite":"Mask PNG";active=s.animationMaskEdit;break;
        case 66:text="Keep area";active=s.adding&&!s.addHole;break;case 67:text="Cut hole";active=s.adding&&s.addHole;break;
        case 68:text="Delete shape";enabled=s.selected>=0;break;
        case 69:{auto *m=spriteMask(doc,spriteMaskKey(s.animationSelected,s.animationFrameMode?s.animationFrame:-1));int edge=m?m->edge:-1;text=edge==1?"Edge: hard":edge==2?"Edge: soft":edge==0?"Edge: original":"Edge: inherit";break;}
        case 70:{auto *m=spriteMask(doc,spriteMaskKey(s.animationSelected,s.animationFrameMode?s.animationFrame:-1));dynamicLabel=Common::String::format("Softness: %.2f px",m?m->feather:1);text=dynamicLabel.c_str();break;}
        case 71:text="Reset mask";break;case 72:text="Add point";active=s.animationMaskInsert;break;
        case 73:text="Delete point";enabled=s.node>=0;break;case 75:text="Revert saved mask";break;
        case 74:dynamicLabel=Common::String::format("Panel: %d%%",s.panelOpacity);text=dynamicLabel.c_str();break;
        case 64:text="Shadows";break;
        case 47:text="Animations";active=s.animationsTab;break;
        case 48:text="< Previous";break;case 49:text="Next >";break;
        case 50:text="Left";break;case 51:text="Right";break;case 52:text="Up";break;case 53:text="Down";break;
        case 54:text=s.animationStep==1?"Step: 1 px":"Step: 1/4 px";active=s.animationStep<1;break;
        case 55:text=s.animationFrameMode?"Reset frame":"Reset sequence";enabled=selectedAnimation()!=nullptr;break;case 56:text="Revert saved position";enabled=selectedAnimation()!=nullptr;break;
        case 30:text="Left";break;case 31:text="Right";break;case 32:text="Up";break;case 33:text="Down";break;case 34:text=HdHead::state().frameMode?"Reset frame":"Reset sequence";break;
        case 35:text=HdHead::state().step==1?"Step: 1 px":"Step: 1/4 px";active=HdHead::state().step<1;break;
        case 36:text="Body outline";active=HdHead::state().body;break;case 37:text="Peek original";active=HdHead::state().original;break;
        case 26:text="Simplify points";enabled=s.selected>=0;break;
        case 61:text="< Previous shape";break;case 62:text="Next shape >";break;
        case 6:text=s.foregroundTab?"Edit nodes":s.animationsTab&&s.animationMaskEdit?"Select nodes":"Select / drag";active=!s.adding&&!s.test&&!s.clipTool;break;case 7:text=s.foregroundTab?"Add mask":"Add area";active=s.adding&&!s.addHole;break;
        case 27:text="Hide Guybrush";active=s.clipTool==1;break;case 28:text="Show Guybrush";active=s.clipTool==2;break;
        case 8:text=s.foregroundTab?"Reveal actor":"Cut hole";active=s.adding&&s.addHole;break;case 9:text=activeLayer==0?"Disable area":"Delete shape";enabled=s.selected>=0;break;
        case 10:text="Undo";enabled=s.headTab?!HdHead::state().undo.empty():!d->undo.empty();break;case 11:text="Redo";enabled=s.headTab?!HdHead::state().redo.empty():!d->redo.empty();break;
        case 2:text="Show walk";active=s.showWalk;break;case 3:text="Show water";active=s.showWater;break;case 19:text="Clip overlay";active=s.showForeground;break;
        case 20:text="Connections";active=s.showConnections;break;case 25:text="Blocked areas";active=s.showBlocked;break;
        case 13:text="Revert saved";break;case 14:text="Reset room";break;case 17:text="Enable area";enabled=s.selected>=0;break;
        case 15:text=s.foregroundTab?"Edit nodes":"Trace water";break;case 16:text="Color filter";break;
        case 21:dynamicLabel=Common::String::format("< Clip layer %d / %d",s.plane,s.planeCount);text=dynamicLabel.c_str();enabled=s.planeCount>1;break;case 22:text="Clip layer >";enabled=s.planeCount>1;break;
        case 23:text=s.bypassForeground?"Restore clips":"Peek actor";active=s.bypassForeground;break;case 24:text="Reset clips";break;
        }
        const bool hover=s.rawX>=control.x&&s.rawX<control.x+control.w&&s.rawY>=control.y&&s.rawY<control.y+control.h;
        plate(control.x,control.y,control.w,control.h,active?42:hover?36:23,active?65:hover?49:35,active?67:hover?57:44,MIN(95,s.panelOpacity+(active||hover?10:0))*255/100);
        if(active)plate(control.x,control.y+control.h-2,control.w,2,230,190,115,255);
        maskText(image,_hdFontManager,_charset,text,control.x+3,control.y+1,control.w-6,control.h-3,active,false,enabled);
    }
    Common::String lines[4];
    const bool dirty=s.headTab?HdHead::state().dirty():d->dirty;
    lines[0]=Common::String::format("SCENE TOOLS   Room %d   |   %s   |   %s",s.room,s.test?"PLAY MODE":"EDIT MODE",dirty?"Unsaved changes - click Save":"Saved");
    if(activeLayer==4){
        auto edited=animationEditVisual();auto *v=edited.key.empty()?nullptr:&edited;auto p=v?effectiveAnimation(v->key,v->cel):Point();
        lines[1]=s.animationFrameMode?"Drag the gold frame preview. Only this frame changes. Whole sequence moves all frames together.":"Drag an outline to move every frame together. Edit: frame makes an individual correction.";
        lines[2]=v?Common::String::format("%s %d   Offset X %.2f / Y %.2f   Arrows: %.2f px   Shift + drag: fine",v->costume==7||v->costume==8?"Flame":"Animation",v->actor,p.x,p.y,s.animationStep):"Blue = animations. Gold = selected. Save keeps positions for this scene.";
        lines[3]="Frame arrows browse captured frames. Reset affects the current scope; other corrections remain.";
        if(s.animationMaskEdit){
            lines[1]="Keep area / Cut hole: click outline points, then Enter. Drag square nodes to retouch the border.";
            lines[2]="Mask follows the PNG. Edge: hard sharpens alpha; Edge: soft feathers inward. Wheel zooms; Space pans.";
            lines[3]=s.animationFrameMode?"Editing only this frame. Save keeps the mask; Reset mask restores its inherited appearance.":"Editing every frame in this animation. Frame arrows browse previews without changing this scope.";
        }
    }else if(activeLayer==3){
        auto &head=HdHead::state();auto v=HdHead::editVisual();auto offset=HdHead::poseOffset(v.pack,v.costume,v.cel);
        lines[1]=v.valid?(head.frameMode?"Drag the gold frame preview. Only this head frame changes. Whole sequence moves all heads.":"Drag the gold head box. Whole sequence moves all heads; Edit: frame corrects just one."):"No separate head in this pose. Let Guybrush stand normally, then try again.";
        lines[2]=head.original?"Original preview is on. Click Peek original to return to your edits.":"Gold = selected. Blue = body. Gray = original. Onion skins show captured neighboring frames.";
        lines[3]=Common::String::format("Offset X %.2f / Y %.2f   |   %s, pose %d   |   Shift + arrows moves 5 steps",offset.x,offset.y,v.pack.c_str(),v.cel);
    }else if(activeLayer==0){
        auto *box=find(doc,s.selected);bool blocked=box&&(box->disabled||(getBoxFlags(box->id)&kBoxInvisible));
        lines[1]=box?Common::String::format("Area %d: %s. Drag a square corner; arrow keys nudge it.",s.selected,blocked?"blocked":"walkable"):"Drag any square corner to reshape an area. Click inside to select it.";
        lines[2]="Green = walkable. Gold = selected. Dashed gray = blocked. Feet mark Guybrush.";
        lines[3]=s.test?"Click the scene to walk. Press T to edit again. M closes the editor.":"Add area: select an existing area, then click 4 corners. Shared edges stay joined.";
        if(box&&s.node>=0&&s.node<(int)box->points.size()&&!s.test){auto p=box->points[s.node];lines[3]=Common::String::format("%s corner %d: (%d, %d). Linked edges move together. Save keeps edits.",s.drag?"Dragging":"Selected",s.node+1,(int)p.x,(int)p.y);}
    }else if(activeLayer==2){
        lines[1]=s.clipInsert?"Click an outline edge to insert a point. The cross marks the exact position.":s.clipTool?Common::String::format("%s: drag a rectangle where you want the effect. Release to apply; Escape cancels.",s.clipTool==1?"Hide Guybrush":"Show Guybrush"):s.clipOutline?"Outline tool: choose Hide or Show, click corners along the scenery, then Enter.":"Edit nodes unlocks original clips. Drag a square point; Previous / Next selects overlapping shapes.";
        lines[2]=s.bypassForeground?"Preview: this clip layer is off. Click Restore clips to see your edits again.":"Purple = hide. Green = show. Gold = selected shape. Hide / Show draws a new mask.";
        lines[3]=Common::String::format("Clip layer %d of %d (Guybrush: %d). Wheel: zoom. Space + drag: pan. Shift + drag: fine. E: add point.",s.plane,s.planeCount,actorPlane);
        if(s.clipView.zoom>1)lines[2]="Wheel zooms at the pointer. Hold Space and drag to pan. 0 restores the full scene.";
        auto *ring=maskSelected(s.drag?s.preview:d->live);
        if(ring&&s.node>=0&&s.node<(int)ring->size()){auto p=(*ring)[s.node];lines[2]=Common::String::format("Point %d / %d   X %.2f  Y %.2f   Arrows: %.2f px   Shift + drag: fine   Space + drag: pan",s.node+1,(int)ring->size(),p.x,p.y,s.clipStep);}
        if(!s.planeCount)lines[2]="This room has no foreground depth planes.";
    }else{
        lines[1]="Blue shows the actual waves. Orange outlines are holes that keep the water out.";
        lines[2]=Common::String::format("Filter: %s. Click a shape, then drag a corner. E adds a node; Delete removes it.",doc.water.palette.c_str());
        lines[3]="Add area / Cut hole: click corners, then Enter. Trace water converts automatic masks.";
    }
    if(s.adding){const bool polygon=maskPolygon()||(s.animationsTab&&s.animationMaskEdit);lines[1]=Common::String::format("Click %s corners. %s Escape cancels.",polygon?"outline":"four",polygon?"Press Enter to finish.":"The fourth click finishes.");lines[2]=Common::String::format("%d corners placed. Click outside the menu to add the next corner.",(int)s.creation.size());}
    if(s.test){lines[1]="Play mode: click the scene to move Guybrush and try your changes.";lines[2]="Outlines stay visible. Click Edit or press T to return to editing.";}
    if(!s.error.empty())lines[2]=s.error.c_str();
    maskText(image,_hdFontManager,_charset,lines[0],panel.x+4,panel.y+1,panelWidth-101,15,true);
    const int detailOffset=maskDetailOffset();
    maskText(image,_hdFontManager,_charset,lines[1],panel.x+4,panel.y+67+detailOffset,panelWidth-8,14);
    maskText(image,_hdFontManager,_charset,lines[2],panel.x+4,panel.y+82+detailOffset,panelWidth-8,14,false);
    if(s.moreOptions)maskText(image,_hdFontManager,_charset,lines[3],panel.x+4,panel.y+126+detailOffset,panelWidth-8,16);

}

#include "scumm/hd_sprite_frames_editor.inc"
#include "scumm/hd_actor_head_editor.inc"
#include "scumm/hd_scene_animations_editor.inc"
#include "scumm/hd_animation_masks_editor.inc"
