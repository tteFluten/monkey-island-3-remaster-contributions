"""Portable mask geometry and editing tests; no game data required."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from engine.scene_masks_defaults import header

ROOT = Path(__file__).resolve().parents[1]

class SceneMasksTests(unittest.TestCase):
    def test_native_json_persistence(self):
        source=ROOT/'.playtest/engine/source';build=ROOT/'.playtest/engine/build'
        objects=[build/'common'/name for name in ('formats/json.o','str.o','str-base.o','memorypool.o')]
        if not all(p.exists() for p in objects):
            self.skipTest('Build the native engine to exercise its JSON implementation')
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            # Always test current authoring headers, not a possibly older generated copy.
            (out/'common').mkdir()
            for name in ('hd_sprite_frames.h','hd_actor_head.h','hd_scene_masks.h','hd_scene_masks_io.h'):
                shutil.copy(ROOT/'tools/engine'/name,out/'common'/name)
            subprocess.run(['c++','-std=c++11','-fsanitize=address,undefined','-DHAVE_CONFIG_H',
                            '-I',str(out),'-I',str(build),'-I',str(source),str(ROOT/'tools/test_scene_masks_io.cpp'),
                            *map(str,objects),'-o',str(out/'test')],check=True)
            subprocess.run([str(out/'test'),str(out/'masks.json')],check=True)

    def test_geometry_history_and_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'common').mkdir()
            shutil.copy(ROOT/'tools/engine/hd_scene_masks.h',root/'common/hd_scene_masks.h')
            shutil.copy(ROOT/'tools/engine/hd_actor_head.h',root/'common/hd_actor_head.h')
            shutil.copy(ROOT/'tools/engine/hd_sprite_frames.h',root/'common/hd_sprite_frames.h')
            (root/'defaults.h').write_text(header())
            (root/'test.cpp').write_text(r'''
#include "common/hd_scene_masks.h"
#include "defaults.h"
#include <cassert>
using namespace HdMasks;
int main(){
    for(double width:{854.0,864.0}){
        EditView view;Point anchor(width*.6,300),p(230,350);
        view.at(anchor,2,width);assert(distance(view.map(anchor,width),anchor)<1e-9);
        auto displayed=view.map(p,width);assert(distance(view.map(displayed,width,true),p)<1e-9);
        Point under=view.map(anchor,width,true);view.at(anchor,4,width);assert(distance(view.map(anchor,width,true),under)<1e-9);
        view.focus={-100,1000};view.constrain(width);assert(view.focus==Point(width/8,420));
        view.at(anchor,1,width);assert(view.map(p,width)==p);
    }
    Foreground precise;precise.plane=1;precise.zones={rectangle({1.25,1.25},{3.25,3.25})};
    std::vector<signed char> fine;rasterForeground(fine,20,20,&precise,0,0,4);
    assert(fine[5*20+4]==-1&&fine[5*20+5]==1&&fine[5*20+12]==1&&fine[5*20+13]==-1);
    SpriteMask mask;mask.zones={rectangle({0,0},{500,1000})};
    std::vector<unsigned char> opaque(16*16,255);
    auto alpha=spriteMaskAlpha(&mask,nullptr,16,16,opaque,1,1,false);
    assert(alpha[8*16+3]==255&&alpha[8*16+12]==0);
    auto mirrored=spriteMaskAlpha(&mask,nullptr,16,16,opaque,1,1,true);
    assert(mirrored[8*16+3]==0&&mirrored[8*16+12]==255);
    mask.holes={rectangle({125,125},{250,250})};
    alpha=spriteMaskAlpha(&mask,nullptr,16,16,opaque,1,1,false);
    assert(alpha[2*16+2]==0&&alpha[8*16+3]==255);
    SpriteMask frame;frame.zones={rectangle({0,0},{1000,500})};
    alpha=spriteMaskAlpha(&mask,&frame,16,16,opaque,1,1,false);
    assert(alpha[10*16+3]==0&&alpha[5*16+3]==255);
    mask.edge=2;mask.feather=1;
    alpha=spriteMaskAlpha(&mask,nullptr,16,16,opaque,1,1,false);
    assert(alpha[8*16+7]>0&&alpha[8*16+7]<255&&alpha[8*16+8]==0);
    assert(alpha[8*16+3]==255); // Inward feather never exposes transparent matte RGB.
    frame=SpriteMask();frame.edge=1;std::vector<unsigned char> fractional(16*16,127);fractional[3*16+3]=128;
    alpha=spriteMaskAlpha(nullptr,&frame,16,16,fractional,1,1,false);
    assert(alpha[3*16+3]==255&&alpha[5*16+3]==0&&fractional[3*16+3]==128);
    Document spriteDoc;std::string spriteError;spriteDoc.animationMasks["topaz:33:8"]=mask;assert(validate(spriteDoc,spriteError));
    spriteDoc.animationMasks["topaz:33:8"].zones={{{0,0},{1000,1000},{0,1000},{1000,0}}};assert(!validate(spriteDoc,spriteError));
    Ring a={{0,0},{10,0},{10,10},{0,10}},b={{10,0},{20,0},{20,10},{10,10}};
    assert(simple(a,true)&&inside(a,{5,5})&&inside(a,{10,5})&&!inside(a,{11,5}));
    assert(adjacent(a,b));assert(!adjacent(a,{{10,10},{20,10},{20,20},{10,20}}));
    assert(!simple({{0,0},{10,10},{0,10},{10,0}},true));
    Document d;Box x;x.id=1;x.parent=1;x.points=a;d.boxes.push_back(x);x.id=2;x.points=b;d.boxes.push_back(x);
    moveShared(d,1,1,{12,0});assert(d.boxes[0].points[1]==Point(12,0));assert(d.boxes[1].points[0]==Point(12,0));
    assert(adjacent(d.boxes[0].points,d.boxes[1].points));
    // Scene 29's entrance shares only the right part of its top edge.
    // Grabbing its far-left corner must keep that portal horizontal.
    Document partial;Box entrance;entrance.id=1;entrance.parent=1;
    entrance.points={{0,429},{104,429},{80,480},{0,480}};partial.boxes.push_back(entrance);
    entrance.id=11;entrance.points={{76,414},{112,414},{104,429},{52,429}};partial.boxes.push_back(entrance);
    moveShared(partial,1,0,{4,432});
    assert(partial.boxes[0].points[0]==Point(4,432));
    assert(partial.boxes[0].points[1]==Point(104,432));
    assert(partial.boxes[1].points[2]==Point(104,432));
    assert(partial.boxes[1].points[3]==Point(52,432));
    assert(adjacent(partial.boxes[0].points,partial.boxes[1].points));
    for(const auto &box:partial.boxes)assert(validWalk(box.points));
    // Continue through multiple partial portals, but leave a disjoint edge alone.
    Document chain;int id=0;
    for(auto ring:std::vector<Ring>{{{0,0},{20,0},{20,10},{0,10}},{{10,10},{30,10},{30,20},{10,20}},{{25,0},{40,0},{40,10},{25,10}},{{50,0},{60,0},{60,10},{50,10}}}){
        Box box;box.id=++id;box.points=ring;chain.boxes.push_back(box);}
    moveShared(chain,1,3,{0,12});
    assert(adjacent(chain.boxes[0].points,chain.boxes[1].points));
    assert(adjacent(chain.boxes[1].points,chain.boxes[2].points));
    assert(chain.boxes[2].points[2]==Point(40,12));
    assert(chain.boxes[3].points[2]==Point(60,10));
    for(auto &box:chain.boxes)for(auto &point:box.points)std::swap(point.x,point.y);
    moveShared(chain,1,3,{15,0});
    assert(adjacent(chain.boxes[0].points,chain.boxes[1].points));
    assert(adjacent(chain.boxes[1].points,chain.boxes[2].points));
    assert(chain.boxes[2].points[2]==Point(15,40));
    Draft draft;draft.live=d;Document edit=d;edit.boxes[1].disabled=true;draft.commit(edit);assert(draft.live.boxes[1].disabled);assert(draft.history(false));assert(!draft.live.boxes[1].disabled);assert(draft.history(true));assert(draft.live.boxes[1].disabled);
    Water w;w.authored=true;w.palette="any";w.zones={{{0,0},{1000,0},{1000,1000},{0,1000}}};w.holes={{{200,200},{400,200},{400,400},{200,400}}};
    assert(covered(w,{50,50},0,0,0));assert(!covered(w,{300,300},0,0,255));
    w.palette="blue";assert(!covered(w,{50,50},255,0,0));assert(covered(w,{50,50},0,0,255));
    unsigned char pixels[25]={0,0,0,0,0,0,1,1,1,0,0,1,0,1,0,0,1,1,1,0,0,0,0,0,0};
    auto traced=contours(pixels,5,5,5);assert(traced.zones.size()==1&&traced.holes.size()==1);
    for(int y=0;y<5;++y)for(int x=0;x<5;++x)assert(covered(traced,{(x+.5)*200,(y+.5)*200},0,0,0)==bool(pixels[y*5+x]));
    unsigned char diagonal[]={1,0,0,1};auto islands=contours(diagonal,2,2,2);assert(islands.zones.size()==2);
    // Pixel-corner contacts must split into simple editable contours. Check
    // every 4x4 mask, including holes touching an outer boundary at a corner.
    for(unsigned bits=1;bits<65536;++bits){
        unsigned char pixels[16];for(int i=0;i<16;++i)pixels[i]=(bits>>i)&1;
        auto traced=contours(pixels,4,4,4);Foreground f;f.zones=traced.zones;f.holes=traced.holes;
        for(auto *rings:{&f.zones,&f.holes})for(auto &ring:*rings)assert(simple(ring));
        for(int y=0;y<4;++y)for(int x=0;x<4;++x)assert(foregroundAt(&f,{(x+.5)*250,(y+.5)*250},false)==bool(pixels[y*4+x]));
    }

    std::string error;Document bad=d;bad.water.zones={{{0,0},{100,100},{0,100},{100,0}}};assert(!validate(bad,error));
    bad=d;bad.boxes[1].id=255;assert(!validate(bad,error));
    auto original=defaults(29,"original");assert(original.authored&&!original.holes.empty());
    auto voodoo=defaults(29,"77d0b9f10c76ae10f230f9386c8d032669535b838be69971e66e00f4443f5cb6");assert(voodoo.palette=="voodoo"&&voodoo.holes.size()==3);
    assert(!defaults(10,"original").authored);
    // Foreground replaces only explicit scopes; untouched native masks stay live.
    Foreground fg;fg.plane=2;fg.replace={{{10,10},{90,10},{90,90},{10,90}}};
    fg.zones={{{20,20},{80,20},{80,80},{20,80}}};fg.holes={{{40,40},{60,40},{60,60},{40,60}}};
    assert(foregroundAt(&fg,{5,5},true));assert(!foregroundAt(&fg,{5,5},false));
    assert(!foregroundAt(&fg,{15,15},true));assert(foregroundAt(&fg,{30,30},false));assert(!foregroundAt(&fg,{50,50},true));
    Foreground paint=fg;
    addForegroundRing(paint,rectangle({45,45},{55,55}),false);
    assert(foregroundAt(&paint,{50,50},false)); // Hide over an existing reveal.
    addForegroundRing(paint,rectangle({52,52},{48,48}),true);
    assert(!foregroundAt(&paint,{50,50},true)); // Show wins when applied last.
    std::vector<signed char> painted;rasterForeground(painted,100,100,&paint,0,0,1);
    for(int y=0;y<100;++y)for(int x=0;x<100;++x)for(bool native:{false,true}){
        int v=painted[y*100+x];assert((v<0?native:v!=0)==foregroundAt(&paint,{x+.5,y+.5},native));}
    Document painting;painting.foreground={paint};assert(validate(painting,error));
    auto malformed=painting;malformed.foreground[0].order[0]=0;assert(!validate(malformed,error));
    malformed=painting;malformed.foreground[0].order[0]=-1024;assert(!validate(malformed,error));
    malformed=painting;malformed.foreground[0].order[0]=malformed.foreground[0].order[1];assert(!validate(malformed,error));
    deleteForegroundRing(paint,1,true);assert(foregroundAt(&paint,{50,50},false));
    deleteForegroundRing(paint,0,false);assert(foregroundAt(&paint,{50,50},false));
    painting.foreground={paint};assert(validate(painting,error));
    deleteForegroundRing(paint,0,false);assert(!foregroundAt(&paint,{50,50},true));
    painting.foreground={paint};assert(validate(painting,error));
    std::vector<signed char> raster;rasterForeground(raster,200,200,&fg,0,0,2);
    for(int y=0;y<200;++y)for(int x=0;x<200;++x)for(bool native:{false,true}){
        int v=raster[y*200+x];assert((v<0?native:v!=0)==foregroundAt(&fg,{(x+.5)/2,(y+.5)/2},native));}
    // Scrolled view uses native room coordinates and preserves the same shape.
    rasterForeground(raster,60,60,&fg,30,30,2);
    for(int y=0;y<60;++y)for(int x=0;x<60;++x)assert((raster[y*60+x]!=0)==foregroundAt(&fg,{30+(x+.5)/2,30+(y+.5)/2},true));
    d.foreground={fg};assert(validate(d,error));bad=d;bad.foreground.push_back(fg);assert(!validate(bad,error));
    bad=d;bad.foreground[0].plane=0;assert(!validate(bad,error));
    bad=d;bad.foreground[0].holes={{{0,0},{100,100},{0,100},{100,0}}};assert(!validate(bad,error));
    draft.base=draft.saved=draft.live=d;changed(draft);assert(!draft.dirty);
    edit=d;edit.foreground[0].zones.clear();draft.commit(edit);changed(draft);assert(draft.dirty);
    assert(draft.history(false));changed(draft);assert(!draft.dirty&&sameForeground(draft.live,d));
    Ring stair={{0,0},{4,.1},{10,0},{10,10},{5,9.9},{0,10}};auto reduced=simplifyRing(stair);assert(reduced.size()==4&&simple(reduced));
    Ring line={{0,0},{0,0},{10,10},{10,10}},moved={{0,0},{0,0},{12,12},{12,12}};
    assert(validWalk(moved,&line));assert(!validWalk(moved));
    for(int room=1;room<=94;++room){Document defaultsDoc;defaultsDoc.water=defaults(room,"original");assert(validate(defaultsDoc,error));}

}
''')
            subprocess.run(['c++','-std=c++11','-fsanitize=address,undefined','-I',str(root),str(root/'test.cpp'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

if __name__=='__main__':unittest.main()
