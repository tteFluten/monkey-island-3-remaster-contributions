void ScummEngine::hdSpriteFrameAction(int action) {
    using namespace HdMasks;auto &s=state();auto &h=HdHead::state();
    if(s.pending){s.pending=false;if(!hdMasksApply(s.preview,true))return;}
    s.animationDrag=s.animationMaskDrag=h.drag=false;s.selected=s.node=-1;s.adding=false;s.creation.clear();s.test=false;s.error.clear();
    if(action==57)s.onion=!s.onion;
    else {
        bool &mode=s.headTab?h.frameMode:s.animationFrameMode;int &frame=s.headTab?h.frame:s.animationFrame;
        std::string group;int current=-1;
        if(s.headTab&&h.visual.valid){group="head:"+h.visual.key;current=h.visual.cel;}
        else if(!s.headTab){auto *v=selectedAnimation();if(v){group="animation:"+v->key;current=v->cel;}}
        if(group.empty()){s.error="Select a visible head or animation first";++s.uiRevision;return;}
        if(action==58){mode=!mode;if(mode&&!s.animationMaskEdit)frame=current;}
        else {if(!s.animationMaskEdit)mode=true;frame=HdSprites::next(group,frame<0?current:frame,action==59?-1:1);if(frame<0)s.error="Let the animation play to capture its frames";}
    }
    ++s.uiRevision;hdMasksRedrawActors();
}
void ScummEngine::drawHDSpriteOnion(Graphics::Surface &surface,bool head) {
    using namespace HdMasks;auto &s=state();if(s.test)return;auto &h=HdHead::state();
    std::string group;int current=-1,chosen=-1;bool frameMode=head?h.frameMode:(s.animationFrameMode||s.animationMaskEdit);
    if(head){if(!h.visual.valid)return;group="head:"+h.visual.key;current=h.visual.cel;chosen=h.frame;}
    else {auto *v=selectedAnimation();if(!v)return;group="animation:"+v->key;current=v->cel;chosen=s.animationFrame;}
    if(!frameMode)chosen=current;
    auto ids=HdSprites::cels(group);if(ids.empty())return;
    std::vector<int> show;if(s.onion&&ids.size()>1){show.push_back(HdSprites::next(group,chosen,-1));int next=HdSprites::next(group,chosen,1);if(next!=show.front())show.push_back(next);}
    if(frameMode)show.push_back(chosen);
    const int rw=MAX(1,_hdBackgroundSurface.w/MAX(1,_hdScale)),rh=MAX(1,_hdBackgroundSurface.h/MAX(1,_hdScale));
    auto project=[&](Point p){return maskView(p,false,false,rw,rh);};
    for(unsigned index=0;index<show.size();++index){auto *f=HdSprites::get(group,show[index]);if(!f||f->room!=s.room||!f->pw||!f->ph)continue;
        const bool selected=frameMode&&f->cel==chosen;Point offset;
        if(head){auto value=HdHead::poseOffset(h.visual.pack,h.visual.costume,f->cel);auto shift=HdHead::scaled(value,f->w,f->h,f->sourceW,f->sourceH,f->mirror);offset={shift.x,shift.y};}
        else offset=effectiveAnimation(s.animationSelected,f->cel);
        const unsigned char *matte=head?nullptr:spriteMaskRaster(s.animationSelected,f->cel,f->pw,f->ph,f->pw/f->w,f->ph/f->h,f->mirror,[&](int x,int y){return f->pixels[y*f->pw+x];});
        const double left=f->x+offset.x,top=f->y+offset.y;
        auto a=project({left,top}),b=project({left+f->w,top+f->h});
        int x0=MAX(0,(int)std::floor(a.x*kMaskScale)),x1=MIN((int)surface.w,(int)std::ceil(b.x*kMaskScale));
        int y0=MAX(0,(int)std::floor(a.y*kMaskScale)),y1=MIN((int)surface.h,(int)std::ceil(b.y*kMaskScale));
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x){auto p=maskView({(x+.5)/kMaskScale,(y+.5)/kMaskScale},false,true,rw,rh);
            int sx=(p.x-left)*f->pw/f->w,sy=(p.y-top)*f->ph/f->h;if(sx<0||sy<0||sx>=f->pw||sy>=f->ph)continue;
            unsigned int color=f->pixels[sy*f->pw+sx];byte alpha=(matte?matte[sy*f->pw+sx]:color>>24)*(selected?(s.animationMaskEdit?255:160):65)/255;if(!alpha)continue;
            byte red=color&255,green=(color>>8)&255,blue=(color>>16)&255;
            if(!selected){red=(red+(index?235:60))/2;green=(green+(index?110:215))/2;blue=(blue+240)/2;}
            maskPixel(surface,x,y,red,green,blue,alpha);
        }
        if(selected)maskText(surface,_hdFontManager,_charset,Common::String::format("Frame %d",f->cel),a.x,a.y-31,100,14,true,true);
    }
}
