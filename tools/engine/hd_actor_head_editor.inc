// Included after the shared native authoring overlay helpers.
void ScummEngine::hdHeadTick() {
    auto &m=HdMasks::state();auto &h=HdHead::state();auto &v=h.visual;
    if(!m.open||!m.headTab||!hdMasksAvailable()){h.drag=h.original=false;return;}
    if(h.drag&&(!v.valid||v.room!=_currentRoom||v.pack!=h.dragVisual.pack||v.costume!=h.dragVisual.costume||v.anchorX!=h.dragVisual.anchorX||v.anchorY!=h.dragVisual.anchorY)){
        h.drag=false;m.error="Guybrush moved or changed costume; drag cancelled.";
    }
}
void ScummEngine::hdHeadAction(int action) {
    auto &m=HdMasks::state();auto &h=HdHead::state();auto v=HdHead::editVisual();
    h.drag=false;m.test=false;m.error.clear();
    if(action==37)h.original=!h.original;
    else{
        h.original=false;
        if(action==10||action==11)h.history(action==11);
        else if(action==35)h.step=h.step==1?.25:1;
        else if(action==36)h.body=!h.body;
        else if(action!=6){
            if(!v.valid||v.room!=_currentRoom){m.error="This pose has no separate HD head to adjust";return;}
            auto value=HdHead::get(h.live,v.key);
            if(action==13)value=HdHead::get(h.saved,v.key);
            else if(action==34)value=HdHead::Offset();
            else if(action==30||action==31)value.x+=(action==30?-h.step:h.step)*(v.mirror?-1:1);
            else if(action==32||action==33)value.y+=action==32?-h.step:h.step;
            h.commit(v.key,value);
        }
    }
    ++m.uiRevision;hdMasksRedrawActors();
}
bool ScummEngine::handleHDHeadEvent(const Common::Event &event) {
    hdHeadTick();auto &m=HdMasks::state();auto &h=HdHead::state();auto v=h.drag?h.dragVisual:HdHead::editVisual();
    const bool key=event.type==Common::EVENT_KEYDOWN,up=event.type==Common::EVENT_LBUTTONUP;
    const bool valid=v.valid&&v.room==_currentRoom;
    if(up&&h.drag){
        if(valid&&HdHead::sameGeometry(h.dragVisual,v))h.commit(h.dragKey,h.preview);
        else m.error="Head pose changed; drag cancelled";
        h.drag=false;++m.uiRevision;hdMasksRedrawActors();return true;
    }
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    auto p=maskView({double(m.rawX),double(m.rawY)},false,true,rw,rh);
    if(event.type==Common::EVENT_LBUTTONDOWN){
        m.buttons|=1;
        if(valid){
            auto offset=HdHead::scaled(HdHead::poseOffset(v.pack,v.costume,v.cel),v.head.w,v.head.h,v.sourceWidth,v.sourceHeight,v.mirror);
            if(p.x>=v.head.x+offset.x-3&&p.x<=v.head.x+offset.x+v.head.w+3&&p.y>=v.head.y+offset.y-3&&p.y<=v.head.y+offset.y+v.head.h+3){
                h.original=false;h.drag=true;h.dragKey=v.key;h.dragMirror=v.mirror;h.dragVisual=v;
                h.dragStart={p.x,p.y};h.dragBefore=h.preview=HdHead::get(h.live,v.key);m.error.clear();
            }
        }
        return true;
    }
    if(event.type==Common::EVENT_RBUTTONDOWN){m.buttons|=2;return true;}
    if(event.type==Common::EVENT_MBUTTONDOWN){m.buttons|=4;return true;}
    if(event.type==Common::EVENT_X1BUTTONDOWN){m.buttons|=8;return true;}
    if(event.type==Common::EVENT_X2BUTTONDOWN){m.buttons|=16;return true;}
    if(event.type==Common::EVENT_MOUSEMOVE&&h.drag){
        if(!valid||!HdHead::sameGeometry(h.dragVisual,v)){h.drag=false;m.error="Head pose changed; drag cancelled";return true;}
        auto delta=HdHead::unscaled({p.x-h.dragStart.x,p.y-h.dragStart.y},v.head.w,v.head.h,v.sourceWidth,v.sourceHeight,v.mirror);
        h.preview=HdHead::clamp({std::round((h.dragBefore.x+delta.x)*4)/4,std::round((h.dragBefore.y+delta.y)*4)/4});
        ++m.uiRevision;hdMasksRedrawActors();return true;
    }
    if(key){
        const int code=event.kbd.keycode;
        if(code==Common::KEYCODE_ESCAPE){if(h.drag||h.original){h.drag=h.original=false;m.error.clear();}else{m.open=false;h.original=false;}}
        else if(code==Common::KEYCODE_TAB)hdMasksAction(0);
        else if(code==Common::KEYCODE_s&&(event.kbd.flags&Common::KBD_CTRL))hdMasksAction(12);
        else if(code==Common::KEYCODE_z&&(event.kbd.flags&Common::KBD_CTRL))hdHeadAction(event.kbd.flags&Common::KBD_SHIFT?11:10);
        else if(valid&&(code==Common::KEYCODE_LEFT||code==Common::KEYCODE_RIGHT||code==Common::KEYCODE_UP||code==Common::KEYCODE_DOWN)){
            double before=h.step;h.step*=event.kbd.flags&Common::KBD_SHIFT?5:1;
            hdHeadAction(code==Common::KEYCODE_LEFT?30:code==Common::KEYCODE_RIGHT?31:code==Common::KEYCODE_UP?32:33);h.step=before;
        }
        ++m.uiRevision;hdMasksRedrawActors();return true;
    }
    return event.type==Common::EVENT_KEYUP||event.type==Common::EVENT_MOUSEMOVE||up||event.type==Common::EVENT_RBUTTONUP||event.type==Common::EVENT_MBUTTONUP||event.type==Common::EVENT_X1BUTTONUP||event.type==Common::EVENT_X2BUTTONUP||event.type==Common::EVENT_WHEELUP||event.type==Common::EVENT_WHEELDOWN||event.type==Common::EVENT_CUSTOM_ENGINE_ACTION_START||event.type==Common::EVENT_CUSTOM_ENGINE_ACTION_END;
}
void ScummEngine::drawHDHead(Graphics::Surface &surface) {
    auto &h=HdHead::state();auto v=HdHead::editVisual();drawHDSpriteOnion(surface,true);if(!v.valid||v.room!=_currentRoom)return;
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    auto project=[&](HdMasks::Point p){return maskView(p,false,false,rw,rh);};
    auto box=[&](HdHead::Bounds b,byte red,byte green,byte blue,bool dashed){
        auto ring=HdMasks::rectangle({b.x,b.y},{b.x+b.w,b.y+b.h});
        for(unsigned i=0;i<4;++i){auto a=ring[i],b=ring[(i+1)%4];for(int j=0;j<16;++j){if(dashed&&(j&1))continue;
            maskLine(surface,project({a.x+(b.x-a.x)*j/16,a.y+(b.y-a.y)*j/16}),project({a.x+(b.x-a.x)*(j+1)/16,a.y+(b.y-a.y)*(j+1)/16}),red,green,blue);
        }}
    };
    if(h.body&&v.body.w>0&&v.body.h>0)box(v.body,75,200,235,false);
    box(v.head,175,180,185,true);
    auto shift=HdHead::scaled(HdHead::poseOffset(v.pack,v.costume,v.cel),v.head.w,v.head.h,v.sourceWidth,v.sourceHeight,v.mirror);
    auto moved=v.head;moved.x+=shift.x;moved.y+=shift.y;box(moved,255,225,135,false);
    auto originalJoin=project({v.head.x+v.head.w/2,v.head.y+v.head.h});
    auto join=project({moved.x+moved.w/2,moved.y+moved.h});
    maskLine(surface,originalJoin,join,255,225,135);
    maskLine(surface,{join.x-5,join.y},{join.x+5,join.y},255,225,135);maskLine(surface,{join.x,join.y-5},{join.x,join.y+5},255,225,135);
    auto center=project({moved.x+moved.w/2,moved.y+moved.h/2});
    maskLine(surface,{center.x-5,center.y},{center.x+5,center.y},255,240,170);maskLine(surface,{center.x,center.y-5},{center.x,center.y+5},255,240,170);
    auto label=project({moved.x,moved.y});
    maskText(surface,_hdFontManager,_charset,Common::String::format("Head %d",v.cel),label.x,label.y-16,100,14,true,true);
}
