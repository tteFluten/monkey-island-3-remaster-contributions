#ifndef HD_SCENE_MASKS_H
#define HD_SCENE_MASKS_H
// Portable authoring model. No game resources, renderer, or savegame ownership.
#include <vector>
#include <map>
#include <string>
#include <algorithm>
#include <cmath>
#include "hd_actor_head.h"
namespace HdMasks {
struct Point {
    double x = 0, y = 0;
    Point() = default;
    Point(double a, double b): x(a), y(b) {}
    bool operator==(const Point &p) const { return x == p.x && y == p.y; }
};
using Ring = std::vector<Point>;
struct EditView {
    double zoom=1;
    Point focus;
    Point map(Point p,double width,bool inverse=false)const{
        if(zoom==1)return p;
        Point middle(width/2,240);
        return inverse?Point(focus.x+(p.x-middle.x)/zoom,focus.y+(p.y-middle.y)/zoom):Point(middle.x+(p.x-focus.x)*zoom,middle.y+(p.y-focus.y)*zoom);
    }
    void constrain(double width){focus.x=std::max(width/(2*zoom),std::min(width-width/(2*zoom),focus.x));focus.y=std::max(240/zoom,std::min(480-240/zoom,focus.y));}
    void at(Point anchor,double value,double width){Point before=map(anchor,width,true);zoom=value;focus={before.x-(anchor.x-width/2)/zoom,before.y-(anchor.y-240)/zoom};constrain(width);}
};
struct Box { int id = 0, parent = 0; bool disabled = false; Ring points; };
struct Water { bool authored = false; std::string palette = "blue"; std::vector<Ring> zones, holes; };
// Native room coordinates. Replacement scopes are explicit snapshots of the
// visible plane; untouched parts of a scrolling room keep their live masks.
// Positive order entries hide with zones[index-1]; negative entries reveal
// with holes[-index-1]. Empty order preserves legacy zones-then-holes behavior.
struct Foreground { int plane=1; std::vector<Ring> zones,holes,replace; std::vector<int> order; };
struct SpriteMask {
    std::vector<Ring> zones,holes;
    int edge=-1; // -1 inherits, 0 preserves PNG alpha, 1 hard, 2 soft inward feather.
    double feather=1;
    bool operator==(const SpriteMask &m)const{return zones==m.zones&&holes==m.holes&&edge==m.edge&&feather==m.feather;}
};
struct Document { std::vector<Box> boxes; Water water; std::vector<Foreground> foreground; std::map<std::string,Point> animations; std::map<std::string,SpriteMask> animationMasks; };
// Instance identity intentionally excludes the changing animation cel.
inline std::string animationKey(int actor,int costume){return std::to_string(actor)+":"+std::to_string(costume);}
inline std::string animationFrameKey(const std::string &key,int cel){return cel<0?key:key+":"+std::to_string(cel);}
inline Point animationOffset(const Document &d,const std::string &key){auto it=d.animations.find(key);return it==d.animations.end()?Point():it->second;}
inline Point animationClamp(Point p){return {std::max(-2048.0,std::min(2048.0,p.x)),std::max(-2048.0,std::min(2048.0,p.y))};}
inline void setAnimationOffset(Document &d,const std::string &key,Point p){if(p==Point())d.animations.erase(key);else d.animations[key]=animationClamp(p);}
struct AnimationVisual {
    std::string key;int actor=0,costume=0,cel=0,room=0;
    double x=0,y=0,w=0,h=0,anchorX=0,anchorY=0;
};
inline double cross(Point a, Point b, Point c) { return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x); }
inline double distance(Point a, Point b) { return std::hypot(a.x-b.x,a.y-b.y); }
inline bool onSegment(Point p, Point a, Point b) {
    return std::abs(cross(a,b,p)) < 1e-6 && p.x >= std::min(a.x,b.x)-1e-6 && p.x <= std::max(a.x,b.x)+1e-6 && p.y >= std::min(a.y,b.y)-1e-6 && p.y <= std::max(a.y,b.y)+1e-6;
}
inline bool inside(const Ring &r, Point p) {
    if (r.size()<3) return false;
    bool yes=false;
    for (unsigned i=0,j=r.size()-1;i<r.size();j=i++) {
        if (onSegment(p,r[j],r[i])) return true;
        if ((r[i].y>p.y)!=(r[j].y>p.y) && p.x<(r[j].x-r[i].x)*(p.y-r[i].y)/(r[j].y-r[i].y)+r[i].x) yes=!yes;
    }
    return yes;
}
inline bool simple(const Ring &r, bool convex=false) {
    if (r.size()<3 || r.size()>4096) return false;
    double area=0, sign=0;
    for (unsigned i=0;i<r.size();++i) {
        Point a=r[i],b=r[(i+1)%r.size()],c=r[(i+2)%r.size()];
        if (!std::isfinite(a.x)||!std::isfinite(a.y)||distance(a,b)<1e-6) return false;
        area+=a.x*b.y-b.x*a.y;
        double turn=cross(a,b,c);
        if (convex && std::abs(turn)>1e-6) { if (sign*turn<0) return false; sign=turn; }
        for (unsigned j=i+1;j<r.size();++j) {
            if (j==i+1 || (i==0&&j==r.size()-1)) continue;
            Point u=r[j],v=r[(j+1)%r.size()];
            double p=cross(a,b,u),q=cross(a,b,v),s=cross(u,v,a),t=cross(u,v,b);
            if ((p*q<0&&s*t<0)||onSegment(u,a,b)||onSegment(v,a,b)||onSegment(a,u,v)||onSegment(b,u,v)) return false;
        }
    }
    return std::abs(area)>1e-6;
}
inline void simplifyPath(const Ring &path,unsigned begin,unsigned end,double tolerance,Ring &out){
    Point a=path[begin],b=path[end];double length=(b.x-a.x)*(b.x-a.x)+(b.y-a.y)*(b.y-a.y),best=tolerance;unsigned split=begin;
    for(unsigned i=begin+1;i<end;++i){auto p=path[i];double t=length?std::max(0.0,std::min(1.0,((p.x-a.x)*(b.x-a.x)+(p.y-a.y)*(b.y-a.y))/length)):0;
        double dist=distance(p,{a.x+t*(b.x-a.x),a.y+t*(b.y-a.y)});if(dist>best){best=dist;split=i;}}
    if(split!=begin){simplifyPath(path,begin,split,tolerance,out);simplifyPath(path,split,end,tolerance,out);}else out.push_back(a);
}
inline Ring simplifyRing(const Ring &ring,double tolerance=1.0){
    if(ring.size()<4)return ring;
    unsigned opposite=1;for(unsigned i=2;i<ring.size();++i)if(distance(ring[0],ring[i])>distance(ring[0],ring[opposite]))opposite=i;
    Ring closed=ring,out;closed.push_back(ring[0]);simplifyPath(closed,0,opposite,tolerance,out);simplifyPath(closed,opposite,ring.size(),tolerance,out);
    return simple(out)?out:ring;
}
inline bool validWalk(const Ring &r, const Ring *original=nullptr) {
    if(r.size()!=4)return false;
    Ring compact;for(auto p:r)if(compact.empty()||!(compact.back()==p))compact.push_back(p);
    if(compact.size()>1&&compact.front()==compact.back())compact.pop_back();
    if(compact.size()>=3)return simple(compact,true);
    if(!original||compact.size()!=2)return false;
    Ring old;for(auto p:*original)if(old.empty()||!(old.back()==p))old.push_back(p);
    if(old.size()>1&&old.front()==old.back())old.pop_back();
    return old.size()==2&&distance(compact[0],compact[1])>0;
}
inline bool touching(const Ring &a,const Ring &b) {
    for(auto p:a)if(inside(b,p))return true;
    for(auto p:b)if(inside(a,p))return true;
    for(unsigned i=0;i<a.size();++i)for(unsigned j=0;j<b.size();++j){auto p=a[i],q=a[(i+1)%a.size()],u=b[j],v=b[(j+1)%b.size()];if(cross(p,q,u)*cross(p,q,v)<0&&cross(u,v,p)*cross(u,v,q)<0)return true;}
    return false;
}
inline bool adjacent(const Ring &a,const Ring &b) {
    // Match SCUMM's navigable horizontal/vertical portals; a point contact is not a portal.
    for (unsigned i=0;i<a.size();++i) for(unsigned j=0;j<b.size();++j) {
        Point p=a[i],q=a[(i+1)%a.size()],u=b[j],v=b[(j+1)%b.size()];
        if(p.x==q.x&&u.x==v.x&&p.x==u.x&&std::min(std::max(p.y,q.y),std::max(u.y,v.y))>std::max(std::min(p.y,q.y),std::min(u.y,v.y))) return true;
        if(p.y==q.y&&u.y==v.y&&p.y==u.y&&std::min(std::max(p.x,q.x),std::max(u.x,v.x))>std::max(std::min(p.x,q.x),std::min(u.x,v.x))) return true;
    }
    return false;
}
inline const Box *find(const Document &d,int id) { for(const auto &b:d.boxes) if(b.id==id)return &b;return nullptr; }
inline Box *find(Document &d,int id) { for(auto &b:d.boxes) if(b.id==id)return &b;return nullptr; }
inline void moveShared(Document &d,int id,int corner,Point p) {
    auto *box=find(d,id); if(!box||corner<0||corner>=4)return;
    Point old=box->points[corner];
    // A portal may occupy only part of an edge. Moving either end of that
    // edge must carry the whole boundary, even if the corner is outside the
    // overlap. Follow adjoining portals too, so T junctions remain navigable.
    struct Portal {Point u,v,s,t;bool vertical,active;};
    std::vector<Portal> candidates;
    for(unsigned i=0;i<d.boxes.size();++i) for(unsigned j=i+1;j<d.boxes.size();++j)
        for(int a=0;a<4;++a) for(int b=0;b<4;++b) {
            Point u=d.boxes[i].points[a],v=d.boxes[i].points[(a+1)%4],s=d.boxes[j].points[b],t=d.boxes[j].points[(b+1)%4];
            bool vertical=u.x==v.x&&s.x==t.x&&u.x==s.x&&std::min(std::max(u.y,v.y),std::max(s.y,t.y))>std::max(std::min(u.y,v.y),std::min(s.y,t.y));
            bool horizontal=u.y==v.y&&s.y==t.y&&u.y==s.y&&std::min(std::max(u.x,v.x),std::max(s.x,t.x))>std::max(std::min(u.x,v.x),std::min(s.x,t.x));
            if(vertical||horizontal)candidates.push_back({u,v,s,t,vertical,onSegment(old,u,v)||onSegment(old,s,t)});
        }
    bool expanded;
    do {expanded=false;for(auto &edge:candidates)if(!edge.active)for(const auto &active:candidates)if(active.active&&active.vertical==edge.vertical){
        for(auto q:{active.u,active.v,active.s,active.t})if(onSegment(q,edge.u,edge.v)||onSegment(q,edge.s,edge.t)){edge.active=true;expanded=true;break;}
        if(edge.active)break;
    }}while(expanded);
    std::vector<std::pair<Point,Point>> portals;
    for(const auto &edge:candidates)if(edge.active){portals.push_back({edge.u,edge.v});portals.push_back({edge.s,edge.t});}
    for(auto &b:d.boxes) for(auto &v:b.points) {
        Point before=v;
        if(before==old) v=p;
        else {
            bool mx=false,my=false;
            for(auto edge:portals) {
                if(onSegment(before,edge.first,edge.second)) {
                    mx=mx||edge.first.x==edge.second.x; my=my||edge.first.y==edge.second.y;
                }
            }
            if(mx)v.x+=p.x-old.x;
            if(my)v.y+=p.y-old.y;
        }
    }
}
inline bool color(const std::string &palette,unsigned r,unsigned g,unsigned b) {
    if(palette=="any")return true;
    if(palette=="voodoo")return b>35&&b*100>r*115&&b*100>g*103;
    if(palette=="teal")return g>6&&b>6&&g*4>r*5&&b*4>r*5&&b*10>g*7;
    bool blue=b>6&&b*100>r*112&&b*100>g*70;
    return blue&&(palette!="navy"||b*100>g*145);
}
inline bool covered(const Water &w,Point p,unsigned r,unsigned g,unsigned b) {
    if(!color(w.palette,r,g,b))return false;
    bool yes=false;for(const auto &ring:w.zones)if(inside(ring,p)){yes=true;break;}
    if(yes)for(const auto &ring:w.holes)if(inside(ring,p))return false;
    return yes;
}
inline const Foreground *foreground(const Document &d,int plane) {
    for(auto &f:d.foreground)if(f.plane==plane)return &f;return nullptr;
}
inline Foreground &foreground(Document &d,int plane) {
    for(auto &f:d.foreground)if(f.plane==plane)return f;
    Foreground f;f.plane=plane;d.foreground.push_back(f);return d.foreground.back();
}
template<class Visit> inline void eachForeground(const Foreground &f,Visit visit) {
    if(f.order.empty()){for(auto &r:f.zones)visit(r,false);for(auto &r:f.holes)visit(r,true);}
    else for(int index:f.order)visit(index>0?f.zones[index-1]:f.holes[-index-1],index<0);
}
inline void addForegroundRing(Foreground &f,const Ring &ring,bool hole) {
    if(f.order.empty()){for(unsigned i=0;i<f.zones.size();++i)f.order.push_back(i+1);for(unsigned i=0;i<f.holes.size();++i)f.order.push_back(-int(i)-1);}
    auto &rings=hole?f.holes:f.zones;rings.push_back(ring);f.order.push_back(hole?-int(rings.size()):int(rings.size()));
}
inline void deleteForegroundRing(Foreground &f,int index,bool hole) {
    auto &rings=hole?f.holes:f.zones;if(index<0||index>=(int)rings.size())return;
    rings.erase(rings.begin()+index);int item=hole?-index-1:index+1;
    f.order.erase(std::remove(f.order.begin(),f.order.end(),item),f.order.end());
    for(int &value:f.order){if(hole&&value<item)++value;else if(!hole&&value>item)--value;}
}
inline Ring rectangle(Point a,Point b) {
    double left=std::min(a.x,b.x),right=std::max(a.x,b.x),top=std::min(a.y,b.y),bottom=std::max(a.y,b.y);
    return {{left,top},{right,top},{right,bottom},{left,bottom}};
}
inline bool foregroundAt(const Foreground *f,Point p,bool native) {
    if(!f)return native;
    for(auto &r:f->replace)if(inside(r,p)){native=false;break;}
    eachForeground(*f,[&](const Ring &r,bool hole){if(inside(r,p))native=!hole;});
    return native;
}
// Scanline rasterization keeps complex traced outlines out of the per-pixel
// actor compositor. -1 delegates to live native coverage, 0 reveals, 1 hides.
inline void rasterRing(std::vector<signed char> &pixels,int w,int h,const Ring &ring,
                       double left,double top,double scale,signed char value) {
    if(ring.size()<3)return;
    double low=h,high=0;
    for(auto p:ring){low=std::min(low,(p.y-top)*scale);high=std::max(high,(p.y-top)*scale);}
    std::vector<double> cuts;
    for(int y=std::max(0,(int)std::ceil(low-.5));y<std::min(h,(int)std::ceil(high-.5));++y){
        double py=top+(y+.5)/scale;cuts.clear();
        for(unsigned i=0,j=ring.size()-1;i<ring.size();j=i++){
            auto a=ring[j],b=ring[i];if((a.y>py)!=(b.y>py))cuts.push_back((a.x+(py-a.y)*(b.x-a.x)/(b.y-a.y)-left)*scale);
        }
        std::sort(cuts.begin(),cuts.end());
        for(unsigned i=0;i+1<cuts.size();i+=2){int a=std::max(0,(int)std::ceil(cuts[i]-.5)),b=std::min(w,(int)std::ceil(cuts[i+1]-.5));
            if(a<b)std::fill(pixels.begin()+y*w+a,pixels.begin()+y*w+b,value);}
    }
}
inline void rasterForeground(std::vector<signed char> &pixels,int w,int h,const Foreground *f,double left,double top,double scale){
    pixels.assign(w*h,-1);if(!f)return;
    for(auto &r:f->replace)rasterRing(pixels,w,h,r,left,top,scale,0);
    eachForeground(*f,[&](const Ring &r,bool hole){rasterRing(pixels,w,h,r,left,top,scale,hole?0:1);});
}
inline bool validate(const Document &d,std::string &error) {
    if(d.animationMasks.size()>256){error="Too many sprite masks";return false;}
    for(auto &entry:d.animationMasks){const auto &m=entry.second;
        if(entry.first.empty()||entry.first.size()>128||m.edge< -1||m.edge>2||!std::isfinite(m.feather)||m.feather<.25||m.feather>8){error="Invalid sprite mask settings";return false;}
        for(auto *rings:{&m.zones,&m.holes}){if(rings->size()>64){error="Too many sprite outlines";return false;}
            for(const auto &ring:*rings){if(!simple(ring)){error="Sprite outlines must not cross themselves";return false;}
                for(auto p:ring)if(p.x<0||p.x>1000||p.y<0||p.y>1000){error="Keep mask points inside the sprite canvas";return false;}}}
    }
    if(d.animations.size()>256){error="Too many animation offsets";return false;}
    for(auto &entry:d.animations){auto p=entry.second;auto colon=entry.first.find(':');
        if(colon==std::string::npos||colon==0||colon+1==entry.first.size()||entry.first.size()>24||entry.first.find_first_not_of("0123456789:")!=std::string::npos||(std::count(entry.first.begin(),entry.first.end(),':')>2||entry.first.back()==':'||entry.first.find("::")!=std::string::npos)||!std::isfinite(p.x)||!std::isfinite(p.y)||std::abs(p.x)>2048||std::abs(p.y)>2048){error="Invalid animation offset";return false;}}
    int last=-1;
    for(const auto &b:d.boxes) {
        if(b.id<=last||b.id>=255||b.parent<0||b.parent>=255||b.points.size()!=4){error="Invalid walkbox ID or corner count";return false;} last=b.id;
        for(auto p:b.points)if(!std::isfinite(p.x)||!std::isfinite(p.y)||p.x < -32768||p.x>32767||p.y < -32768||p.y>32767||p.x!=std::floor(p.x)||p.y!=std::floor(p.y)){error="Walkbox coordinates must be native integers";return false;}
        // Some original SCUMM boxes are degenerate. New/changed shapes are checked at edit time.
    }
    if(d.water.palette!="blue"&&d.water.palette!="navy"&&d.water.palette!="any"&&d.water.palette!="voodoo"&&d.water.palette!="teal"){error="Unknown water color filter";return false;}
    for(const auto *rings:{&d.water.zones,&d.water.holes}) {
        if(rings->size()>1024){error="Too many water contours";return false;}
        for(const auto &r:*rings){if(!simple(r)){error="Water outlines must not cross themselves";return false;}
            for(auto p:r)if(p.x<0||p.x>1000||p.y<0||p.y>1000){error="Water node is outside the painting";return false;}}
    }
    bool planes[8]={};
    for(auto &f:d.foreground){
        if(f.plane<1||f.plane>7||planes[f.plane]){error="Invalid or duplicate foreground depth plane";return false;}planes[f.plane]=true;
        for(auto *rings:{&f.zones,&f.holes,&f.replace}){
            if(rings->size()>1024){error="Too many foreground outlines";return false;}
            for(auto &r:*rings){if(!simple(r)){error="Foreground outlines must not cross themselves";return false;}
                for(auto p:r)if(p.x<0||p.x>32767||p.y<0||p.y>32767){error="Foreground node is outside room coordinates";return false;}}
        }
        if(!f.order.empty()){
            if(f.order.size()!=f.zones.size()+f.holes.size()){error="Invalid clipping order";return false;}
            std::vector<bool> zones(f.zones.size()),holes(f.holes.size());
            for(int index:f.order){
                if(index>0&&index<=(int)zones.size()){if(zones[index-1]){error="Duplicate clipping shape";return false;}zones[index-1]=true;}
                else if(index<0&&index>=-int(holes.size())){if(holes[-index-1]){error="Duplicate clipping shape";return false;}holes[-index-1]=true;}
                else{error="Invalid clipping shape reference";return false;}
            }
        }
    }
    return true;
}
struct Draft {
    Document base, saved, live;
    std::vector<Document> undo,redo;
    bool initialized=false,dirty=false,walkChanged=false,waterChanged=false;
    void commit(const Document &d) { undo.push_back(live);if(undo.size()>100)undo.erase(undo.begin());redo.clear();live=d;dirty=true; }
    bool history(bool forward) {auto &src=forward?redo:undo;auto &dst=forward?undo:redo;if(src.empty())return false;dst.push_back(live);live=src.back();src.pop_back();dirty=true;return true;}
};
// Trace exact pixel boundary edges, preserving holes and disconnected components.
inline Water contours(const unsigned char *pixels,int width,int height,int pitch) {
    Water w;w.authored=true;w.palette="any";
    using Vertex=std::pair<int,int>;std::multimap<Vertex,Vertex> edges;
    auto wet=[&](int x,int y){return x>=0&&y>=0&&x<width&&y<height&&pixels[y*pitch+x]!=0;};
    for(int y=0;y<height;++y)for(int x=0;x<width;++x)if(wet(x,y)) {
        if(!wet(x,y-1))edges.emplace(Vertex{x,y},Vertex{x+1,y});
        if(!wet(x+1,y))edges.emplace(Vertex{x+1,y},Vertex{x+1,y+1});
        if(!wet(x,y+1))edges.emplace(Vertex{x+1,y+1},Vertex{x,y+1});
        if(!wet(x-1,y))edges.emplace(Vertex{x,y+1},Vertex{x,y});
    }
    while(!edges.empty()) {
        Vertex start=edges.begin()->first,at=start,previous{start.first-1,start.second};Ring ring;
        do {
            ring.push_back(Point(at.first*1000.0/width,at.second*1000.0/height));
            auto range=edges.equal_range(at);if(range.first==range.second){ring.clear();break;}
            auto chosen=range.first;
            // Turn right at a diagonal pixel contact, keeping components separate.
            for(auto it=range.first;it!=range.second;++it) {
                int dx=at.first-previous.first,dy=at.second-previous.second;
                int nx=it->second.first-at.first,ny=it->second.second-at.second;
                if(dx*ny-dy*nx>0){chosen=it;break;}
            }
            previous=at;at=chosen->second;edges.erase(chosen);
        }while(at!=start);
        if(ring.size()<3)continue;
        // A hole can touch its enclosing boundary at one pixel corner. The
        // edge walk then revisits that vertex; split it into simple loops
        // without moving or simplifying the original pixel boundary.
        Ring path;std::map<std::pair<double,double>,unsigned> seen;
        ring.push_back(ring.front());
        for(auto p:ring){
            auto key=std::make_pair(p.x,p.y);auto found=seen.find(key);
            if(found==seen.end()){seen[key]=path.size();path.push_back(p);continue;}
            unsigned start=found->second;Ring loop(path.begin()+start,path.end()),reduced;
            for(unsigned i=0;i<loop.size();++i)if(std::abs(cross(loop[(i+loop.size()-1)%loop.size()],loop[i],loop[(i+1)%loop.size()]))>1e-8)reduced.push_back(loop[i]);
            double area=0;for(unsigned i=0;i<reduced.size();++i){auto a=reduced[i],b=reduced[(i+1)%reduced.size()];area+=a.x*b.y-b.x*a.y;}
            if(reduced.size()>=3)(area>0?w.zones:w.holes).push_back(reduced);
            for(unsigned i=start+1;i<path.size();++i)seen.erase({path[i].x,path[i].y});
            path.resize(start+1);
        }
    }
    return w;
}
struct Control {int slot,x,y,w,h;};
struct State {
    bool animationMaskEdit=false,animationMaskDrag=false,animationMaskInsert=false;
    int panelOpacity=65;
    std::string animationPack="unknown";
    bool onion=true,animationFrameMode=false;int animationFrame=-1;
    bool animationsTab=false,animationDrag=false;
    std::string animationSelected;
    std::vector<AnimationVisual> animationVisuals;
    AnimationVisual animationGrab;
    Point animationStart,animationBefore;
    double animationStep=.25;
    EditView clipView;
    bool clipOutline=false,clipInsert=false,clipPan=false;
    double clipStep=.25;
    int clipFill=80;
    Point panStart,panFocus;
    bool moreOptions=false;
    bool menuBottom=false;
    std::vector<Control> controls;
    std::map<std::string,Draft> drafts;
    std::string key,source,path,fileText,error;
    int room=-1,revision=0,uiRevision=0;
    bool widePainting=false;
    bool loaded=false,writable=true,open=false,test=false,waterTab=false,showWalk=true,showWater=false;
    bool foregroundTab=false,headTab=false,showForeground=false,showConnections=false,showBlocked=false,bypassForeground=false;
    int plane=1,planeCount=1;
    bool pending=false,drag=false,adding=false,addHole=false,hole=false,rectangleDrag=false;
    int clipTool=0; // 0 selects, 1 draws Hide actor, 2 draws Show actor.
    int selected=-1,node=-1,rawX=0,rawY=0;
    Point dragStart,dragNode;
    unsigned buttons=0; bool keys[512]={};
    Document preview; Ring creation;
    Draft *draft(){auto it=drafts.find(key);return it==drafts.end()?nullptr:&it->second;}
};
inline State &state(){static State s;return s;}
inline Point effectiveAnimation(const std::string &key,int cel=-1){auto &s=state();auto *d=s.draft();if(!d)return {};const auto &doc=s.animationDrag?s.preview:d->live;
    auto group=animationOffset(doc,key),frame=cel<0?Point():animationOffset(doc,animationFrameKey(key,cel));return {group.x+frame.x,group.y+frame.y};}
inline const AnimationVisual *selectedAnimation(){auto &s=state();for(auto &v:s.animationVisuals)if(v.key==s.animationSelected&&v.room==s.room)return &v;return nullptr;}
inline AnimationVisual animationEditVisual(){auto &s=state();auto *v=selectedAnimation();if(!v)return {};auto copy=*v;
    if(s.animationFrameMode||s.animationMaskEdit){auto *f=HdSprites::get("animation:"+v->key,s.animationFrame);if(!f){s.animationFrame=copy.cel;return copy;}copy.cel=f->cel;copy.x=f->x;copy.y=f->y;copy.w=f->w;copy.h=f->h;}
    return copy;
}
inline bool sameWalk(const Document &a,const Document &b) {
    if(a.boxes.size()!=b.boxes.size())return false;
    for(unsigned i=0;i<a.boxes.size();++i){auto &x=a.boxes[i];auto &y=b.boxes[i];if(x.id!=y.id||x.parent!=y.parent||x.disabled!=y.disabled||x.points!=y.points)return false;}return true;
}
inline bool sameWater(const Water &a,const Water &b){return a.authored==b.authored&&a.palette==b.palette&&a.zones==b.zones&&a.holes==b.holes;}
inline bool sameForeground(const Document &a,const Document &b){
    if(a.foreground.size()!=b.foreground.size())return false;
    for(unsigned i=0;i<a.foreground.size();++i){auto &x=a.foreground[i];auto &y=b.foreground[i];if(x.plane!=y.plane||x.zones!=y.zones||x.holes!=y.holes||x.replace!=y.replace||x.order!=y.order)return false;}return true;
}
inline void changed(Draft &d){d.walkChanged=!sameWalk(d.live,d.base);d.waterChanged=!sameWater(d.live.water,d.base.water);d.dirty=!sameWalk(d.live,d.saved)||!sameWater(d.live.water,d.saved.water)||!sameForeground(d.live,d.saved)||d.live.animations!=d.saved.animations||d.live.animationMasks!=d.saved.animationMasks;++state().revision;}
inline std::string spriteMaskKey(const std::string &key,int cel=-1){return state().animationPack+":"+animationFrameKey(key,cel);}
inline const SpriteMask *spriteMask(const Document &d,const std::string &key){auto it=d.animationMasks.find(key);return it==d.animationMasks.end()?nullptr:&it->second;}
inline const Document *spriteMaskDocument(){auto &s=state();auto *d=s.draft();return d?(s.animationMaskDrag?&s.preview:&d->live):nullptr;}
inline bool hasSpriteMask(const std::string &key,int cel){auto *d=spriteMaskDocument();return d&&(spriteMask(*d,spriteMaskKey(key))||spriteMask(*d,spriteMaskKey(key,cel)));}
inline bool spriteMaskPreview(const std::string &key){auto &s=state();return s.open&&s.animationsTab&&s.animationMaskEdit&&!s.test&&s.animationSelected==key&&!animationEditVisual().key.empty();}
inline std::vector<unsigned char> spriteMaskAlpha(const SpriteMask *group,const SpriteMask *frame,int w,int h,const std::vector<unsigned char> &source,double scaleX,double scaleY,bool mirror){
    std::vector<unsigned char> alpha=source;
    for(auto *m:{group,frame})if(m){
        std::vector<signed char> coverage(w*h,m->zones.empty()?1:0);
        auto paint=[&](const Ring &ring,int value){Ring r;for(auto p:ring)r.push_back({(mirror?1000-p.x:p.x)*w/1000,p.y*h/1000});rasterRing(coverage,w,h,r,0,0,1,value);};
        for(const auto &r:m->zones)paint(r,1);for(const auto &r:m->holes)paint(r,0);
        for(unsigned i=0;i<alpha.size();++i)if(!coverage[i])alpha[i]=0;
    }
    const SpriteMask *edge=frame&&frame->edge>=0?frame:group;
    if(edge&&edge->edge==1)for(auto &a:alpha)a=a>=128?255:0;
    if(edge&&edge->edge==2){
        int rx=std::max(1,(int)std::ceil(edge->feather*scaleX)),ry=std::max(1,(int)std::ceil(edge->feather*scaleY));
        std::vector<unsigned char> temp(w*h),blur(w*h);
        for(int y=0;y<h;++y){int sum=0;for(int x=0;x<=rx&&x<w;++x)sum+=alpha[y*w+x];for(int x=0;x<w;++x){temp[y*w+x]=sum/(2*rx+1);if(x-rx>=0)sum-=alpha[y*w+x-rx];if(x+rx+1<w)sum+=alpha[y*w+x+rx+1];}}
        for(int x=0;x<w;++x){int sum=0;for(int y=0;y<=ry&&y<h;++y)sum+=temp[y*w+x];for(int y=0;y<h;++y){blur[y*w+x]=sum/(2*ry+1);if(y-ry>=0)sum-=temp[(y-ry)*w+x];if(y+ry+1<h)sum+=temp[(y+ry+1)*w+x];}}
        // Feather inward: never reveal transparent matte RGB or create halos.
        for(unsigned i=0;i<alpha.size();++i)alpha[i]=std::min(alpha[i],blur[i]);
    }
    return alpha;
}
struct SpriteMaskCache {std::string scope;std::map<std::string,std::vector<unsigned char>> entries;size_t bytes=0;};
inline SpriteMaskCache &spriteMaskCache(){static SpriteMaskCache c;return c;}
template<class Sample> inline const unsigned char *spriteMaskRaster(const std::string &key,int cel,int w,int h,double scaleX,double scaleY,bool mirror,Sample sample){
    auto &s=state();auto *d=spriteMaskDocument();if(!d||w<=0||h<=0)return nullptr;
    auto *group=spriteMask(*d,spriteMaskKey(key)),*frame=spriteMask(*d,spriteMaskKey(key,cel));if(!group&&!frame)return nullptr;
    auto &c=spriteMaskCache();std::string scope=s.key+":"+s.animationPack+":"+std::to_string(s.revision)+":"+std::to_string(s.animationMaskDrag?s.uiRevision:0);
    if(c.scope!=scope){c.entries.clear();c.bytes=0;c.scope=scope;}
    std::string id=animationFrameKey(key,cel)+":"+std::to_string(w)+":"+std::to_string(h)+":"+std::to_string(scaleX)+":"+std::to_string(scaleY)+(mirror?":m":":n");
    auto found=c.entries.find(id);if(found!=c.entries.end())return found->second.data();
    if(c.entries.size()>=64||c.bytes+(size_t)w*h>16*1024*1024){c.entries.clear();c.bytes=0;}
    std::vector<unsigned char> source(w*h);for(int y=0;y<h;++y)for(int x=0;x<w;++x)source[y*w+x]=sample(x,y)>>24;
    auto &alpha=c.entries[id];alpha=spriteMaskAlpha(group,frame,w,h,source,scaleX,scaleY,mirror);c.bytes+=alpha.size();return alpha.data();
}
inline bool waterOverride(int room){auto &s=state();auto *d=s.draft();return s.room==room&&d&&d->waterChanged&&d->live.water.authored;}
inline bool waterAt(int room,double x,double y,unsigned r,unsigned g,unsigned b){auto &s=state();auto *d=s.draft();return s.room==room&&d&&covered(d->live.water,{x,y},r,g,b);}
}
#endif
