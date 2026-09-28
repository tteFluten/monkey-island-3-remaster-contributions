"""Head-only offsets, costume/pack isolation, scaling, mirroring, and edit history."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ActorHeadTests(unittest.TestCase):
    def test_offsets_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.cpp').write_text(r'''
#include "hd_actor_head.h"
#include <cassert>
#include <limits>
using namespace HdHead;
int main(){
    for(int cel:{4,34,47,52,58,63,67,172,200,511})assert(headCel(2,cel));
    for(int cel:{0,8,31,173,561,687})assert(!headCel(2,cel));
    assert(!headCel(3,58));
    Visual a;a.valid=true;a.room=29;a.key=key("topaz",2,-1);a.head.w=19;a.head.h=29;a.cel=58;
    Visual b=a;b.cel=363;assert(sameGeometry(a,b)); // Speech/blinks keep dragging.
    b.head.x+=1;assert(!sameGeometry(a,b));b=a;b.mirror=true;assert(!sameGeometry(a,b));
    b=a;b.room=14;assert(!sameGeometry(a,b));b=a;b.sourceWidth+=1;assert(!sameGeometry(a,b));
    for(bool mirror:{false,true})for(double scale:{.25,.5,1.0,1.75}){
        Offset p(2.5,-1.25);auto moved=scaled(p,43*scale,64*scale,43,64,mirror);
        assert(moved==Offset(p.x*scale*(mirror?-1:1),p.y*scale));
        auto back=unscaled(moved,43*scale,64*scale,43,64,mirror);
        assert(std::abs(back.x-p.x)<1e-8&&std::abs(back.y-p.y)<1e-8);
    }
    assert(valid({64,-64})&&!valid({65,0})&&!valid({std::numeric_limits<double>::quiet_NaN(),0}));
    auto &s=state();auto pose=key("topaz",2,-1),otherCostume=key("topaz",3,-1),otherPack=key("quiver",2,-1);
    s.commit(pose,{2,-3});assert(s.dirty()&&get(s.live,pose)==Offset(2,-3));
    assert(get(s.live,otherCostume)==Offset()&&get(s.live,otherPack)==Offset());
    s.saved=s.live;assert(!s.dirty());s.commit(pose,{3,-4});assert(s.dirty());
    s.history(false);assert(!s.dirty());s.history(true);assert(get(s.live,pose)==Offset(3,-4));
    s.drag=true;s.dragKey=pose;s.preview={5,6};assert(effective(pose)==Offset(5,6));
    assert(get(s.live,pose)==Offset(3,-4)&&effective(otherCostume)==Offset());
    s.original=true;assert(effective(pose)==Offset());s.original=s.drag=false;
    s.live.clear();s.commit(key("topaz",2,-1),{3,4});s.commit(key("topaz",2,58),{.25,-2});
    assert(poseOffset("topaz",2,58)==Offset(3.25,2));assert(poseOffset("topaz",2,63)==Offset(3,4));
    s.commit(key("topaz",2,-1),{5,6});assert(poseOffset("topaz",2,58)==Offset(5.25,4));
    s.commit(key("topaz",2,58),{});assert(poseOffset("topaz",2,58)==Offset(5,6));
    auto f=HdSprites::make("head:test",58,29,10,20,5,8);f.anchorX=100;HdSprites::paint(f,10,20,5,8,[](double,double){return 0xffabcdefu;});
    HdSprites::remember(f);assert(HdSprites::get("head:test",58)->pixels[0]==0xffabcdefu);
    f.cel=63;HdSprites::remember(f);assert(HdSprites::next("head:test",58,1)==63&&HdSprites::next("head:test",58,-1)==63);
    f.anchorX=110;HdSprites::remember(f);assert(HdSprites::cels("head:test").size()==1);HdSprites::cache().clear();

    s.commit(pose,{});assert(s.live.empty());s.history(false);assert(get(s.live,pose)==Offset(5,6));
    s.commit(otherCostume,{1,1});assert(get(s.live,pose)==Offset(5,6));
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(ROOT/'tools/engine'), str(root/'test.cpp'), '-o', str(root/'test')], check=True)
            subprocess.run([str(root/'test')], check=True)


if __name__ == '__main__': unittest.main()
