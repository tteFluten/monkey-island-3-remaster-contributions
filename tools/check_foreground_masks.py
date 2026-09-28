#!/usr/bin/env python3
"""Exercise actual foreground clipping, authoring and persistence using isolated saves."""
import argparse
import json
import re
import time
from pathlib import Path
from PIL import Image, ImageChops
from check_aspect import Check, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.context/foreground-check')
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=True)
    masks=out/'scene-masks.json';masks.write_text('{"schemaVersion":1,"scenes":{}}\n')
    c=Check(out/'first',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    def state():return c.state().get('maskEditor',{})
    def key(code,mod=0):c.send(f'key {code} {mod}')
    def screen(x,y):
        w=c.window();h=max(w['height'],w['width']*9/16);width=h*max(854,c.state()['viewportWidth'])/480
        return round((w['width']-width)/2+x*h/480),round((w['height']-h)/2+y*h/480)
    def click(x,y):
        px,py=screen(x,y);c.send(f'click {px} {py}')
    def slot(n):c.mask_button(n)
    header=(ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    maps=[]
    for axis in ('X','Y'):
        body=re.search(r'k'+axis+r'\[\] = \{(.*?)\};',header,re.S).group(1)
        maps.append([(float(a),float(b)) for a,b in re.findall(r'\{([\d.]+),([\d.]+)\}',body)])
    def interpolate(points,x):
        a,b=next(((a,b) for a,b in zip(points,points[1:]) if x<=b[0]),points[-2:])
        return a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0])
    def native(x,y):return interpolate(maps[0],x)*854/2048,interpolate(maps[1],y)*480/1152
    def actor():return next(a for a in c.state()['actors'] if a['id']==1)
    def polygon(points,button):
        slot(button);key(112)
        for x,y in points:click(*native(x,y))
        key(13)
    def rectangle(a,b,button):
        slot(button)
        x,y=screen(*native(*a));xx,yy=screen(*native(*b))
        feet=(actor()['x'],actor()['y'])
        c.send(f'down {x} {y}');c.send(f'move {xx} {yy}');c.send(f'up {xx} {yy}')
        assert (actor()['x'],actor()['y'])==feet,'Clipping gesture reached gameplay'
    try:
        c.jump(29);key(109);c.wait(lambda:state().get('visible'),'editor visible')
        assert not state()['water'] and not state()['foreground'] and not state()['connections']
        click(*native(405,337));c.screenshot('walkable-selected')
        slot(12);c.wait(lambda:state()['connections'],'connections on');slot(12)
        key(116);c.wait(lambda:state()['test'],'test walking')
        (c.output/'walk-to.txt').write_text('300 354\n')
        c.wait(lambda:abs(actor()['x']-300)<=2 and abs(actor()['y']-354)<=2,'walk behind post',40)
        key(116);c.wait(lambda:not state()['test'],'T restores editor')
        slot(2);c.wait(lambda:state()['foreground'],'foreground tab')
        assert state()['planes']>0
        plane=state()['plane'];c.screenshot('foreground-clipping-on')
        slot(15);c.wait(lambda:state()['bypass'],'clipping bypass')
        c.screenshot('foreground-clipping-off')
        # The actor overlaps the post here. Comparing only that region avoids
        # the changing toolbar and animated water elsewhere in the scene.
        a=Image.open(c.output/'foreground-clipping-on.png').convert('RGB')
        b=Image.open(c.output/'foreground-clipping-off.png').convert('RGB')
        x1,y1=native(270,210);x2,y2=native(340,365)
        roi=(round(x1*a.width/854),round(y1*a.height/480),round(x2*a.width/854),round(y2*a.height/480))
        diff=ImageChops.difference(a.crop(roi),b.crop(roi))
        assert sum(1 for p in diff.getdata() if max(p)>30)>100,'Bypass must change actual actor clipping'
        slot(15);c.wait(lambda:not state()['bypass'],'clipping restored')
        slot(6);c.wait(lambda:bool(state()['document']['foreground']),'trace visible',40)
        traced=state()['document']['foreground'];f=next(f for f in traced if f['plane']==plane)
        assert f['replace'] and f['zones']
        # Select a visible corner of the largest outline, then simplify it.
        index=max(range(len(f['zones'])),key=lambda i:len(f['zones'][i]))
        p=next(p for p in f['zones'][index] if 185<native(*p)[1]<420 and 30<native(*p)[0]<800)
        click(*native(*p));c.wait(lambda:state()['selected']==index,'select foreground outline')
        key(115);c.wait(lambda:len(state()['document']['foreground'][0]['zones'][index])<len(f['zones'][index]),'simplify traced mask')
        simplified=state()['document']['foreground'];slot(10)
        c.wait(lambda:state()['document']['foreground']==traced,'undo simplify');slot(11)
        c.wait(lambda:state()['document']['foreground']==simplified,'redo simplify')
        c.screenshot('foreground-editable')
        # Reset only this plane, then add a small mask over the actor and a
        # reveal cutout. This exercises authored hide/show in both compositors.
        slot(17);c.wait(lambda:not state()['document']['foreground'],'reset plane')
        key(109);c.screenshot('actor-original');key(109)
        def light_pixels(name):
            im=Image.open(c.output/(name+'.png')).convert('RGB').crop(roi)
            return sum(1 for r,g,b in im.getdata() if min(r,g,b)>165)
        original_light=light_pixels('actor-original')
        # Clicks and cancelled drags must not leave degenerate clipping masks.
        slot(7);click(*native(270,210));assert not state()['document']['foreground']
        px,py=screen(*native(270,210));xx,yy=screen(*native(340,365))
        c.send(f'down {px} {py}');c.send(f'move {xx} {yy}');key(27);c.send(f'up {xx} {yy}')
        assert not state()['document']['foreground']
        rectangle((270,210),(340,365),7)
        c.wait(lambda:bool(state()['document']['foreground']),'add foreground')
        key(109);c.screenshot('actor-hidden');key(109)
        hidden_light=light_pixels('actor-hidden')
        assert original_light>50 and hidden_light<original_light*.4,('authored mask hides actor',original_light,hidden_light)
        rectangle((325,310),(285,230),8) # Reverse-direction drawing works too.
        c.wait(lambda:len(state()['document']['foreground'][0]['holes'])==1,'reveal cutout')
        key(109);c.screenshot('actor-revealed');key(109)
        assert light_pixels('actor-revealed')>hidden_light+50,'Reveal cutout restores the actor pixels'
        revealed=state()['document']['foreground']
        rectangle((285,230),(325,310),7)
        key(109);c.screenshot('actor-hidden-again');key(109)
        assert light_pixels('actor-hidden-again')<original_light*.4,'Hide must override an earlier Show'
        slot(10);c.wait(lambda:state()['document']['foreground']==revealed,'undo last clip')
        # Keep click-to-draw outlines available as an optional detailed tool.
        polygon(((80,340),(100,340),(90,360)),7)
        assert len(state()['document']['foreground'][0]['zones'])==2
        slot(9);c.wait(lambda:state()['document']['foreground']==revealed,'delete custom outline')
        c.screenshot('simple-clipping-tools')
        before=state()['document']['foreground'];p=before[0]['holes'][0][0]
        px,py=screen(*native(*p));c.send(f'down {px} {py}');c.send(f'move {px+8} {py}');c.send(f'up {px+8} {py}')
        c.wait(lambda:state()['document']['foreground']!=before,'drag foreground node')
        edited=state()['document']['foreground'];key(115,192)
        c.wait(lambda:not state()['dirty'],'save foreground')
        key(109);c.wait(lambda:not state()['open'],'close')
        c.jump(14);c.jump(29);key(109);c.wait(lambda:state()['visible'],'return to scene')
        assert state()['document']['foreground']==edited and not state()['bypass']
        c.save_load(1,2,29);c.save_load(2,2,29)
        c.wait(lambda:state()['visible'],'savegame restored')
        assert state()['document']['foreground']==edited
        # Switching layers or rooms must cancel the unsaved bypass preview.
        slot(15);c.wait(lambda:state()['bypass'],'bypass again');slot(0)
        assert not state()['bypass'];slot(2)
        slot(15);c.jump(14);c.wait(lambda:state()['visible'],'panorama transition')
        assert not state()['bypass'];c.screenshot('panorama-foreground')
        slot(0);c.screenshot('panorama-walkable')
    finally:c.close()
    c=Check(out/'restart',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    try:
        c.jump(29);key(109);c.wait(lambda:state()['visible'],'editor after restart');slot(2)
        assert state()['document']['foreground']==edited and not state()['bypass']
        slot(17);c.wait(lambda:not state()['document']['foreground'],'reset restored plane')
        slot(16);c.wait(lambda:state()['document']['foreground']==edited,'revert saved')
        for width,height in ((1280,800),(1720,720)):
            c.send(f'resize {width} {height}');c.screenshot(f'foreground-{width}x{height}')
        print('PASS: clipping bypass changes actor pixels, trace, simplify, drag, hide/reveal, undo/redo, scene transitions, Test shortcut, save/load, restart, reset/revert, display ratios',flush=True)
    finally:c.close()

if __name__=='__main__':main()
