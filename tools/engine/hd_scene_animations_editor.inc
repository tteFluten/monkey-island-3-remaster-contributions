// Scene-local sprite offsets. The sequence keeps running; its actor and costume
// identify the instance, independent of the current PNG/frame and frame bounds.
void ScummEngine::hdAnimationsTick() {
    auto &s=HdMasks::state();if(!s.animationDrag&&!s.animationMaskDrag)return;
    auto *v=HdMasks::selectedAnimation();
    if(!s.open||!s.animationsTab||s.test||!hdMasksAvailable()||!v||v->anchorX!=s.animationGrab.anchorX||v->anchorY!=s.animationGrab.anchorY){
        s.animationDrag=s.animationMaskDrag=false;s.error="Animation moved or left the scene; drag cancelled";++s.uiRevision;
    }
}
void ScummEngine::hdAnimationsAction(int action) {
    using namespace HdMasks;auto &s=state();auto *d=s.draft();if(!d)return;
    s.animationDrag=s.animationMaskDrag=false;s.selected=s.node=-1;s.adding=false;s.creation.clear();s.test=false;s.error.clear();
    if(action==54)s.animationStep=s.animationStep==1?.25:1;
    else if(action==48||action==49){
        std::vector<const AnimationVisual *> visible;
        // Keep displaced instances selectable even when moved off-screen, so
        // Next + Reset can always recover a saved position.
        for(auto &v:s.animationVisuals)if(v.room==s.room&&v.w>0&&v.h>0)visible.push_back(&v);
        if(visible.empty())s.error="No editable animations are available here";
        else{int index=-1;for(unsigned i=0;i<visible.size();++i)if(visible[i]->key==s.animationSelected)index=i;
            index=index<0?(action==48?(int)visible.size()-1:0):(index+(action==48?-1:1)+visible.size())%visible.size();s.animationSelected=visible[index]->key;s.animationFrame=visible[index]->cel;}
    }else if(auto *v=selectedAnimation()){
        Document next=d->live;const auto key=animationFrameKey(v->key,s.animationFrameMode?s.animationFrame:-1);auto p=animationOffset(next,key);
        if(action==55)p={};else if(action==56)p=animationOffset(d->saved,key);
        else if(action==50)p.x-=s.animationStep;else if(action==51)p.x+=s.animationStep;
        else if(action==52)p.y-=s.animationStep;else if(action==53)p.y+=s.animationStep;
        setAnimationOffset(next,key,p);s.preview=next;s.pending=true;
    }else s.error="Click an animation outline or use Next to select one";
    ++s.uiRevision;hdMasksRedrawActors();
}
bool ScummEngine::handleHDAnimationsEvent(const Common::Event &event) {
    using namespace HdMasks;auto &s=state();auto *d=s.draft();if(!d)return true;
    hdAnimationsTick();
    if(s.animationMaskEdit)return handleHDAnimationMaskEvent(event);
    const bool key=event.type==Common::EVENT_KEYDOWN;
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    Point p=maskView({double(s.rawX),double(s.rawY)},false,true,rw,rh);
    if(event.type==Common::EVENT_LBUTTONUP&&s.animationDrag){s.animationDrag=false;s.pending=true;++s.uiRevision;hdMasksRedrawActors();return true;}
    if(event.type==Common::EVENT_LBUTTONDOWN){
        s.buttons|=1;AnimationVisual hit;double best=1e20;
        auto editable=animationEditVisual();
        for(auto original:s.animationVisuals){auto v=s.animationFrameMode&&original.key==editable.key?editable:original;auto shift=effectiveAnimation(v.key,v.cel);
            auto a=maskView({v.x+shift.x,v.y+shift.y},false,false,rw,rh),b=maskView({v.x+v.w+shift.x,v.y+v.h+shift.y},false,false,rw,rh);
            if(v.room==s.room&&s.rawX>=a.x-5&&s.rawX<=b.x+5&&s.rawY>=a.y-5&&s.rawY<=b.y+5){double area=(b.x-a.x)*(b.y-a.y);if(area<best){best=area;hit=v;}}}
        if(!hit.key.empty()){if(s.animationSelected!=hit.key||s.animationFrame<0)s.animationFrame=hit.cel;s.animationSelected=hit.key;s.animationGrab=hit;s.animationStart=p;s.animationBefore=animationOffset(d->live,animationFrameKey(hit.key,s.animationFrameMode?s.animationFrame:-1));s.preview=d->live;s.animationDrag=true;s.error.clear();}
        else{s.animationSelected.clear();s.error="Click a sprite outline, or use Next for small animations";}
        ++s.uiRevision;return true;
    }
    if(event.type==Common::EVENT_MOUSEMOVE&&s.animationDrag){
        double speed=(_system->getEventManager()->getModifierState()&Common::KBD_SHIFT)?.1:1;
        Point next(s.animationBefore.x+(p.x-s.animationStart.x)*speed,s.animationBefore.y+(p.y-s.animationStart.y)*speed);
        const auto key=animationFrameKey(s.animationSelected,s.animationFrameMode?s.animationFrame:-1);setAnimationOffset(s.preview,key,next);s.animationStart=p;s.animationBefore=animationOffset(s.preview,key);
        ++s.uiRevision;hdMasksRedrawActors();return true;
    }
    if(key){int code=event.kbd.keycode;
        if(code==Common::KEYCODE_ESCAPE){if(s.animationDrag)s.animationDrag=false;else s.open=false;hdMasksRedrawActors();}
        else if(code==Common::KEYCODE_TAB)hdAnimationsAction(event.kbd.flags&Common::KBD_SHIFT?48:49);
        else if(code==Common::KEYCODE_s&&(event.kbd.flags&Common::KBD_CTRL))hdMasksAction(12);
        else if(code==Common::KEYCODE_z&&(event.kbd.flags&Common::KBD_CTRL))hdMasksAction(event.kbd.flags&Common::KBD_SHIFT?11:10);
        else if(code==Common::KEYCODE_LEFT||code==Common::KEYCODE_RIGHT||code==Common::KEYCODE_UP||code==Common::KEYCODE_DOWN){
            double step=s.animationStep;s.animationStep*=event.kbd.flags&Common::KBD_SHIFT?5:1;
            hdAnimationsAction(code==Common::KEYCODE_LEFT?50:code==Common::KEYCODE_RIGHT?51:code==Common::KEYCODE_UP?52:53);s.animationStep=step;
        }
        ++s.uiRevision;
    }
    // Editing never forwards sprite drags or keyboard actions to gameplay.
    return true;
}
void ScummEngine::drawHDAnimations(Graphics::Surface &surface) {
    using namespace HdMasks;auto &s=state();drawHDSpriteOnion(surface,false);
    if(s.animationMaskEdit&&!s.test){drawHDAnimationMask(surface);return;}
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    auto project=[&](Point p){return maskView(p,false,false,rw,rh);};
    for(auto original:s.animationVisuals){auto v=s.animationFrameMode&&original.key==s.animationSelected?animationEditVisual():original;if(v.key.empty()||v.room!=s.room)continue;auto shift=effectiveAnimation(v.key,v.cel);bool selected=v.key==s.animationSelected;
        auto box=[&](Point offset,bool original){auto ring=rectangle({v.x+offset.x,v.y+offset.y},{v.x+v.w+offset.x,v.y+v.h+offset.y});
            for(int i=0;i<4;++i)for(int j=0;j<16;++j){if(original&&(j&1))continue;auto a=ring[i],b=ring[(i+1)%4];maskLine(surface,project({a.x+(b.x-a.x)*j/16,a.y+(b.y-a.y)*j/16}),project({a.x+(b.x-a.x)*(j+1)/16,a.y+(b.y-a.y)*(j+1)/16}),original?150:selected?255:75,original?160:selected?225:210,original?165:selected?135:235);}};
        if(selected&&!(shift==Point()))box({},true);box(shift,false);
        auto p=project({v.x+shift.x,v.y+shift.y});if(p.x< -100||p.x>=maskCanvasWidth()||p.y<0||p.y>=480)continue;
        Common::String text=Common::String::format("%s %d",v.costume==7||v.costume==8?"Flame":"Animation",v.actor);
        maskText(surface,_hdFontManager,_charset,text,p.x,p.y-16,120,14,selected,true);
    }
}
