#ifndef HD_ACTOR_HEAD_H
#define HD_ACTOR_HEAD_H
#include <algorithm>
#include <cmath>
#include <map>
#include <string>
#include <vector>
#include "hd_sprite_frames.h"

namespace HdHead {
struct Offset {
    double x=0,y=0;
    Offset()=default;
    Offset(double xx,double yy):x(xx),y(yy){}
    bool operator==(const Offset &other)const{return x==other.x&&y==other.y;}
};
using Offsets=std::map<std::string,Offset>;
// Explicit head identities from the pinned normal Guybrush costume, including
// speaking and turning poses. Never identify a head by draw order or actor ID.
inline bool headCel(int costume,int cel) {
    static const int heads[]={
        4,34,47,52,58,63,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,
        85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,
        109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,
        133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,
        157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,174,176,177,179,180,181,182,183,
        184,185,186,187,188,190,191,192,193,194,195,196,197,198,200,201,202,204,205,206,207,208,211,212,
        213,214,215,216,217,218,219,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,237,238,
        239,240,241,242,243,246,247,250,253,255,256,257,258,259,260,261,262,263,264,265,266,268,269,270,
        271,272,273,274,275,276,277,278,280,281,282,283,285,286,287,289,290,291,292,293,294,295,296,297,
        299,300,301,302,303,304,305,306,307,308,309,310,313,314,315,317,318,319,320,322,324,325,326,327,
        328,329,330,331,332,334,335,337,340,341,343,344,346,347,349,350,351,352,354,356,359,360,361,362,
        363,364,365,366,367,368,369,370,371,372,373,374,375,376,377,378,379,380,381,382,383,384,385,386,
        387,388,389,390,391,392,393,394,395,396,397,398,399,400,401,402,403,404,405,411,412,413,414,415,
        511,562,563,564,565,566,567,568,569,570,571,572,573,576,577
    };
    return costume==2&&std::binary_search(heads,heads+sizeof(heads)/sizeof(heads[0]),cel);
}
inline std::string key(const std::string &pack,int costume,int cel){return pack+":"+std::to_string(costume)+":"+std::to_string(cel);}
inline Offset get(const Offsets &values,const std::string &key){auto i=values.find(key);return i==values.end()?Offset():i->second;}
inline bool valid(Offset p){return std::isfinite(p.x)&&std::isfinite(p.y)&&std::abs(p.x)<=64&&std::abs(p.y)<=64;}
inline Offset clamp(Offset p){return {std::max(-64.0,std::min(64.0,p.x)),std::max(-64.0,std::min(64.0,p.y))};}
inline Offset scaled(Offset p,double width,double height,double sourceWidth,double sourceHeight,bool mirror){
    return sourceWidth>0&&sourceHeight>0?Offset(p.x*width/sourceWidth*(mirror?-1:1),p.y*height/sourceHeight):Offset();
}
inline Offset unscaled(Offset p,double width,double height,double sourceWidth,double sourceHeight,bool mirror){
    return width>0&&height>0?Offset(p.x*sourceWidth/width*(mirror?-1:1),p.y*sourceHeight/height):Offset();
}
struct Bounds {double x=0,y=0,w=0,h=0;};
struct Visual {
    bool valid=false,mirror=false;
    std::string key,pack;
    int costume=0,cel=-1,room=0;
    double sourceWidth=0,sourceHeight=0,anchorX=0,anchorY=0;
    Bounds head,body;
};
inline bool sameGeometry(const Visual &a,const Visual &b){
    return a.valid&&b.valid&&a.room==b.room&&a.key==b.key&&a.mirror==b.mirror&&
        a.sourceWidth==b.sourceWidth&&a.sourceHeight==b.sourceHeight&&
        a.head.x==b.head.x&&a.head.y==b.head.y&&a.head.w==b.head.w&&a.head.h==b.head.h;
}
struct State {
    Offsets live,saved;
    std::vector<Offsets> undo,redo;
    Visual visual;
    bool frameMode=false;int frame=-1;
    bool drag=false,body=true,original=false;
    std::string dragKey;
    bool dragMirror=false;
    Visual dragVisual;
    Offset dragStart,dragBefore,preview;
    double step=1;
    bool dirty()const{return live!=saved;}
    void commit(const std::string &key,Offset p){
        p=clamp(p);if(get(live,key)==p)return;
        undo.push_back(live);if(undo.size()>100)undo.erase(undo.begin());redo.clear();
        if(p==Offset())live.erase(key);else live[key]=p;
    }
    void history(bool forward){auto &src=forward?redo:undo;auto &dst=forward?undo:redo;if(src.empty())return;dst.push_back(live);live=src.back();src.pop_back();}
};
inline State &state(){static State s;return s;}
inline Offset effective(const std::string &key){auto &s=state();return s.original?Offset():s.drag&&s.dragKey==key?s.preview:get(s.live,key);}
inline Offset poseOffset(const std::string &pack,int costume,int cel){auto group=effective(key(pack,costume,-1)),frame=effective(key(pack,costume,cel));return {group.x+frame.x,group.y+frame.y};}
inline Visual editVisual(){auto &s=state();auto v=s.visual;if(!s.frameMode)return v;
    auto *f=HdSprites::get("head:"+v.key,s.frame);if(!f){s.frame=v.cel;v.key=key(v.pack,v.costume,v.cel);return v;}
    v.cel=f->cel;v.key=key(v.pack,v.costume,v.cel);v.mirror=f->mirror;v.sourceWidth=f->sourceW;v.sourceHeight=f->sourceH;
    v.head={};v.head.x=f->x;v.head.y=f->y;v.head.w=f->w;v.head.h=f->h;return v;
}
}
#endif
