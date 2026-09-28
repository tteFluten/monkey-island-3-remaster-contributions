#ifndef HD_SPRITE_FRAMES_H
#define HD_SPRITE_FRAMES_H
#include <algorithm>
#include <cmath>
#include <string>
#include <vector>
#include <utility>
namespace HdSprites {
// Read-only snapshots for onion skins; never serialized as artwork or game state.
struct Frame {
    std::string group;int cel=-1,room=-1,pw=0,ph=0;
    double x=0,y=0,w=0,h=0,sourceW=0,sourceH=0,anchorX=0,anchorY=0;
    bool mirror=false;
    std::vector<unsigned int> pixels;
};
inline Frame make(const std::string &group,int cel,int room,double x,double y,double w,double h){
    Frame f;f.group=group;f.cel=cel;f.room=room;f.x=x;f.y=y;f.w=w;f.h=h;
    if(w>0&&h>0){double scale=std::min(4.0,256.0/std::max(w,h));f.pw=std::max(1,(int)std::ceil(w*scale));f.ph=std::max(1,(int)std::ceil(h*scale));f.pixels.resize(f.pw*f.ph);}
    return f;
}
template<class Sample> inline void paint(Frame &f,double x,double y,double w,double h,Sample sample){
    if(!f.pw||!f.ph||w<=0||h<=0)return;
    int l=std::max(0,(int)std::floor((x-f.x)*f.pw/f.w)),r=std::min(f.pw,(int)std::ceil((x+w-f.x)*f.pw/f.w));
    int t=std::max(0,(int)std::floor((y-f.y)*f.ph/f.h)),b=std::min(f.ph,(int)std::ceil((y+h-f.y)*f.ph/f.h));
    for(int yy=t;yy<b;++yy)for(int xx=l;xx<r;++xx){double u=(f.x+(xx+.5)*f.w/f.pw-x)/w,v=(f.y+(yy+.5)*f.h/f.ph-y)/h;
        if(u>=0&&u<1&&v>=0&&v<1)f.pixels[yy*f.pw+xx]=sample(u,v);}
}
inline std::vector<Frame> &cache(){static std::vector<Frame> frames;return frames;}
inline void remember(Frame frame){
    if(frame.pixels.empty())return;auto &frames=cache();
    for(auto &f:frames)if(f.group==frame.group&&(f.room!=frame.room||f.anchorX!=frame.anchorX||f.anchorY!=frame.anchorY)){
        const std::string group=frame.group;frames.erase(std::remove_if(frames.begin(),frames.end(),[&](const Frame &item){return item.group==group;}),frames.end());break;}
    for(auto &f:frames)if(f.group==frame.group&&f.cel==frame.cel){f=std::move(frame);return;}
    // Bound editor memory even when visiting hundreds of character poses.
    unsigned count=0;for(auto &f:frames)if(f.group==frame.group)++count;
    if(count>=64)for(auto i=frames.begin();i!=frames.end();++i)if(i->group==frame.group){frames.erase(i);break;}
    if(frames.size()>=192)frames.erase(frames.begin());frames.push_back(std::move(frame));
}
inline const Frame *get(const std::string &group,int cel){for(auto &f:cache())if(f.group==group&&f.cel==cel)return &f;return nullptr;}
inline std::vector<int> cels(const std::string &group){std::vector<int> ids;for(auto &f:cache())if(f.group==group)ids.push_back(f.cel);std::sort(ids.begin(),ids.end());return ids;}
inline int next(const std::string &group,int cel,int direction){auto ids=cels(group);if(ids.empty())return -1;auto it=std::find(ids.begin(),ids.end(),cel);int n=it==ids.end()?0:(int)(it-ids.begin());return ids[(n+direction+ids.size())%ids.size()];}
}
#endif
