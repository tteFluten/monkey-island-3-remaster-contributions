// Sprite-local polygons: normalized unmirrored PNG coordinates, never room clips.
namespace {
std::string editedSpriteMaskKey(){auto &s=HdMasks::state();return HdMasks::spriteMaskKey(s.animationSelected,s.animationFrameMode?s.animationFrame:-1);}
const HdSprites::Frame *editedSpriteFrame(){auto &s=HdMasks::state();return HdSprites::get("animation:"+s.animationSelected,s.animationFrame);}
HdMasks::Point spriteMaskPoint(HdMasks::Point p,bool inverse){
    using namespace HdMasks;auto &s=state();auto v=animationEditVisual();if(v.key.empty()||v.w<=0||v.h<=0)return {};
    auto shift=effectiveAnimation(v.key,v.cel);auto *f=editedSpriteFrame();bool mirror=f&&f->mirror;
    if(inverse){p={(p.x-v.x-shift.x)*1000/v.w,(p.y-v.y-shift.y)*1000/v.h};if(mirror)p.x=1000-p.x;return p;}
    if(mirror)p.x=1000-p.x;return {v.x+shift.x+p.x*v.w/1000,v.y+shift.y+p.y*v.h/1000};
}
HdMasks::Ring *selectedSpriteRing(HdMasks::Document &doc){
    auto &s=HdMasks::state();auto it=doc.animationMasks.find(editedSpriteMaskKey());if(it==doc.animationMasks.end()||s.selected<0)return nullptr;
    auto &rings=s.hole?it->second.holes:it->second.zones;return s.selected<(int)rings.size()?&rings[s.selected]:nullptr;
}
}
void ScummEngine::hdAnimationMaskAction(int action){
    using namespace HdMasks;auto &s=state();auto *d=s.draft();if(!d)return;
    if(s.pending){s.pending=false;if(!hdMasksApply(s.preview,true))return;}
    s.animationMaskDrag=s.animationDrag=false;s.test=false;s.error.clear();s.creation.clear();s.adding=false;
    if(action==65){
        if(s.animationMaskEdit){s.animationMaskEdit=false;s.animationMaskInsert=false;}
        else{auto *v=selectedAnimation();if(!v){s.error="Select an animation first";return;}
            if(!s.animationFrameMode||s.animationFrame<0)s.animationFrame=v->cel;
            if(!editedSpriteFrame()){s.error="Let the animation play to capture its PNG frames";return;}
            s.animationMaskEdit=true;s.clipView=EditView();}
        s.selected=s.node=-1;
    }else if(!selectedAnimation()){s.error="Select an animation first";}
    else if(action==66||action==67){s.adding=true;s.addHole=action==67;s.selected=s.node=-1;s.animationMaskInsert=false;}
    else if(action==72)s.animationMaskInsert=!s.animationMaskInsert;
    else{
        Document next=d->live;const auto key=editedSpriteMaskKey();
        if(action==71)next.animationMasks.erase(key);
        else if(action==75){auto *saved=spriteMask(d->saved,key);if(saved)next.animationMasks[key]=*saved;else next.animationMasks.erase(key);}
        else if(action==69){auto &m=next.animationMasks[key];m.edge=m.edge<0?1:m.edge==1?2:m.edge==2?0:1;}
        else if(action==70){auto &m=next.animationMasks[key];m.feather=m.feather>=8?.25:m.feather*2;m.edge=2;}
        else if(action==68){auto *ring=selectedSpriteRing(next);if(!ring){s.error="Select an outline to delete";return;}
            auto &m=next.animationMasks[key];auto &rings=s.hole?m.holes:m.zones;rings.erase(rings.begin()+s.selected);s.selected=s.node=-1;}
        else if(action==73){auto *ring=selectedSpriteRing(next);if(!ring||s.node<0||s.node>=(int)ring->size()||ring->size()<=3){s.error="Select a point; keep at least three points";return;}ring->erase(ring->begin()+s.node);s.node=-1;}
        s.preview=next;s.pending=true;
    }
    ++s.uiRevision;hdMasksRedrawActors();
}
bool ScummEngine::handleHDAnimationMaskEvent(const Common::Event &event){
    using namespace HdMasks;auto &s=state();auto *d=s.draft();if(!d)return true;
    if(!selectedAnimation()||!editedSpriteFrame()){s.animationMaskDrag=false;s.error="Select an animation and let its frames load";return true;}
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    auto project=[&](Point p){return maskView(spriteMaskPoint(p,false),false,false,rw,rh);};
    auto p=spriteMaskPoint(maskView({double(s.rawX),double(s.rawY)},false,true,rw,rh),true);
    auto clamp=[](Point p){return Point(std::max(0.0,std::min(1000.0,p.x)),std::max(0.0,std::min(1000.0,p.y)));};
    if(event.type==Common::EVENT_LBUTTONUP&&s.animationMaskDrag){s.animationMaskDrag=false;s.pending=hdMasksAvailable();++s.uiRevision;return true;}
    if(event.type==Common::EVENT_MOUSEMOVE&&s.animationMaskDrag){
        auto *ring=selectedSpriteRing(s.preview);if(ring&&s.node>=0&&s.node<(int)ring->size()){
            double speed=(_system->getEventManager()->getModifierState()&Common::KBD_SHIFT)?.1:1;
            (*ring)[s.node]=clamp({(*ring)[s.node].x+(p.x-s.dragStart.x)*speed,(*ring)[s.node].y+(p.y-s.dragStart.y)*speed});s.dragStart=p;}
        ++s.uiRevision;hdMasksRedrawActors();return true;
    }
    auto insert=[&](){
        Document next=d->live;auto *m=spriteMask(next,editedSpriteMaskKey());if(!m){s.error="Draw a mask outline first";return;}
        double best=10;int shape=-1,node=-1;bool hole=false;Point chosen;
        for(bool cut:{false,true}){const auto &rings=cut?m->holes:m->zones;for(unsigned k=0;k<rings.size();++k){const auto &ring=rings[k];
            for(unsigned i=0;i<ring.size();++i)for(int j=0;j<32;++j){auto a=ring[i],b=ring[(i+1)%ring.size()];Point aa(a.x+(b.x-a.x)*j/32,a.y+(b.y-a.y)*j/32),bb(a.x+(b.x-a.x)*(j+1)/32,a.y+(b.y-a.y)*(j+1)/32);
                auto x=project(aa),y=project(bb);double dx=y.x-x.x,dy=y.y-x.y,len=dx*dx+dy*dy;
                double t=len?std::max(0.0,std::min(1.0,((s.rawX-x.x)*dx+(s.rawY-x.y)*dy)/len)):0;
                double dist=distance({double(s.rawX),double(s.rawY)},{x.x+t*dx,x.y+t*dy});if(dist<best){best=dist;shape=k;node=i;hole=cut;chosen={aa.x+t*(bb.x-aa.x),aa.y+t*(bb.y-aa.y)};}
            }
        }}
        if(shape<0){s.error="Point at an outline edge to insert a node";return;}
        s.selected=shape;s.hole=hole;auto *ring=selectedSpriteRing(next);if(distance(chosen,(*ring)[node])<.01||distance(chosen,(*ring)[(node+1)%ring->size()])<.01){s.error="Choose a spot between existing nodes";return;}
        ring->insert(ring->begin()+node+1,chosen);s.node=node+1;s.preview=next;s.pending=true;s.animationMaskInsert=false;s.error.clear();
    };
    if(event.type==Common::EVENT_LBUTTONDOWN){
        s.buttons|=1;if(s.adding){if(p.x<0||p.x>1000||p.y<0||p.y>1000){s.error="Place points inside the sprite canvas";return true;}s.creation.push_back(p);s.error.clear();++s.uiRevision;return true;}
        if(s.animationMaskInsert){insert();return true;}
        auto *m=spriteMask(d->live,editedSpriteMaskKey());double best=8;int shape=-1,node=-1;bool hole=false;
        if(m)for(bool cut:{false,true}){const auto &rings=cut?m->holes:m->zones;for(unsigned k=0;k<rings.size();++k)for(unsigned i=0;i<rings[k].size();++i){double dist=distance(project(rings[k][i]),{double(s.rawX),double(s.rawY)});if(dist<best){best=dist;shape=k;node=i;hole=cut;}}}
        s.selected=shape;s.node=node;s.hole=hole;
        if(node>=0){s.animationMaskDrag=true;s.animationGrab=*selectedAnimation();s.preview=d->live;s.dragStart=p;s.error.clear();}
        else if(m){for(bool cut:{false,true}){const auto &rings=cut?m->holes:m->zones;for(unsigned i=0;i<rings.size();++i)if(inside(rings[i],p)){s.selected=i;s.hole=cut;}}}
        ++s.uiRevision;return true;
    }
    if(event.type==Common::EVENT_KEYDOWN){int code=event.kbd.keycode;
        if(code==Common::KEYCODE_ESCAPE){if(s.animationMaskDrag||s.adding||s.animationMaskInsert){s.animationMaskDrag=s.adding=s.animationMaskInsert=false;s.creation.clear();}else s.animationMaskEdit=false;}
        else if(code==Common::KEYCODE_RETURN&&s.adding){Document next=d->live;auto &m=next.animationMasks[editedSpriteMaskKey()];auto &rings=s.addHole?m.holes:m.zones;
            if(!simple(s.creation)){s.error="Place at least three points without crossing the outline";return true;}
            rings.push_back(s.creation);s.selected=rings.size()-1;s.hole=s.addHole;s.node=-1;s.preview=next;s.pending=true;s.adding=false;s.creation.clear();s.error.clear();}
        else if(code==Common::KEYCODE_e||code==Common::KEYCODE_INSERT)insert();
        else if(code==Common::KEYCODE_DELETE||code==Common::KEYCODE_BACKSPACE)hdAnimationMaskAction(s.node>=0?73:68);
        else if(code==Common::KEYCODE_s&&(event.kbd.flags&Common::KBD_CTRL))hdMasksAction(12);
        else if(code==Common::KEYCODE_z&&(event.kbd.flags&Common::KBD_CTRL))hdMasksAction(event.kbd.flags&Common::KBD_SHIFT?11:10);
        else if(code==Common::KEYCODE_0)hdMasksAction(46);
        else if(code==Common::KEYCODE_LEFT||code==Common::KEYCODE_RIGHT||code==Common::KEYCODE_UP||code==Common::KEYCODE_DOWN){Document next=d->live;auto *ring=selectedSpriteRing(next);auto v=animationEditVisual();
            if(ring&&s.node>=0&&s.node<(int)ring->size()&&v.w>0&&v.h>0){auto q=(*ring)[s.node];double step=s.clipStep*(event.kbd.flags&Common::KBD_SHIFT?5:1);auto *f=editedSpriteFrame();double direction=f&&f->mirror?-1:1;
                q.x+=(code==Common::KEYCODE_LEFT?-step:code==Common::KEYCODE_RIGHT?step:0)*1000/v.w*direction;
                q.y+=(code==Common::KEYCODE_UP?-step:code==Common::KEYCODE_DOWN?step:0)*1000/v.h;(*ring)[s.node]=clamp(q);s.preview=next;s.pending=true;}
        }
        ++s.uiRevision;hdMasksRedrawActors();
    }
    return true;
}
void ScummEngine::drawHDAnimationMask(Graphics::Surface &surface){
    using namespace HdMasks;auto &s=state();auto *d=s.draft();if(!d||!selectedAnimation()||!editedSpriteFrame())return;
    const auto &doc=s.animationMaskDrag?s.preview:d->live;auto *m=spriteMask(doc,editedSpriteMaskKey());
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    auto project=[&](Point p){return maskView(spriteMaskPoint(p,false),false,false,rw,rh);};
    auto line=[&](Point a,Point b,int r,int g,int blue){for(int j=0;j<32;++j)maskLine(surface,project({a.x+(b.x-a.x)*j/32,a.y+(b.y-a.y)*j/32}),project({a.x+(b.x-a.x)*(j+1)/32,a.y+(b.y-a.y)*(j+1)/32}),r,g,blue);};
    auto canvas=rectangle({0,0},{1000,1000});for(int i=0;i<4;++i)line(canvas[i],canvas[(i+1)%4],130,150,165);
    if(m)for(bool cut:{false,true}){const auto &rings=cut?m->holes:m->zones;for(unsigned k=0;k<rings.size();++k){auto &ring=rings[k];bool chosen=s.selected==(int)k&&s.hole==cut;
        for(unsigned i=0;i<ring.size();++i){line(ring[i],ring[(i+1)%ring.size()],chosen?255:cut?255:85,chosen?225:cut?125:230,chosen?130:cut?110:205);auto p=project(ring[i]);
            for(int y=-3;y<=3;++y)for(int x=-3;x<=3;++x)for(int sy=0;sy<kMaskScale;++sy)for(int sx=0;sx<kMaskScale;++sx)maskPixel(surface,(int(p.x)+x)*kMaskScale+sx,(int(p.y)+y)*kMaskScale+sy,255,chosen?225:160,130,255);
            if(chosen&&(int)i==s.node)maskText(surface,_hdFontManager,_charset,Common::String::format("%d",i+1),p.x+6,p.y-14,40,14,true,true);
        }
    }}
    if(s.adding){for(unsigned i=1;i<s.creation.size();++i)line(s.creation[i-1],s.creation[i],255,235,170);if(!s.creation.empty())maskLine(surface,project(s.creation.back()),{double(s.rawX),double(s.rawY)},255,235,170);}
}
