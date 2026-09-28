#!/usr/bin/env python3
"""Native precision clipping: zoom/pick alignment, polygon edits, and input isolation."""
import argparse,json,re,time
from pathlib import Path
from PIL import Image,ImageChops,ImageStat
from check_aspect import Check,ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'.context/clipping-precision')
    out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=True)
    masks=out/'masks.json';masks.write_text('{"schemaVersion":1,"scenes":{}}')
    c=Check(out/'native',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    def state():return c.state()['maskEditor']
    def precision():return state()['clipPrecision']
    def ring():return state()['document']['foreground'][0]['zones'][0]
    def feet():
        a=next(a for a in c.state()['actors'] if a['id']==1);return a['x'],a['y']
    def key(n,mod=0):c.send(f'key {n} {mod}')
    def button(n):c.mask_button(n)
    header=(ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    axes={axis:[tuple(map(float,p)) for p in re.findall(r'\{(\d+),(\d+)\}',re.search(r'k'+axis+r'\[\] = (.*?);',header,re.S)[1])] for axis in ('X','Y')}
    def paint(v,axis):
        points=axes[axis];i=next((i for i in range(1,len(points)) if v<=points[i][0]),len(points)-1);a,b=points[i-1:i+1]
        return a[1]+(b[1]-a[1])*(v-a[0])/(b[0]-a[0])
    win={}
    def canvas():return max(854,c.state()['viewportWidth'])
    def screen(x,y):
        h=max(win['height'],win['width']*9/16)
        return round((win['width']-h*canvas()/480)/2+x*h/480),round((win['height']-h)/2+y*h/480)
    def projected(x,y):
        s=c.state();width=canvas()
        if s.get('voodooExterior'):x,y=paint(x,'X')*width/2048,paint(y,'Y')*480/1152
        else:x,y=x-s['cameraLeft']+(width-s['viewportWidth'])/2,y-s['cameraTop']
        v=precision()
        if v['zoom']>1 and not state()['test']:x,y=width/2+(x-v['focusX'])*v['zoom'],240+(y-v['focusY'])*v['zoom']
        return x,y
    def point(x,y):return screen(*projected(x,y))
    def click(p):
        x,y=projected(*p);controls=state()['controls'];dock=next(b for b in controls if b['slot']==20);first=next(b for b in controls if b['slot']==0)
        if first['x']<=x<=dock['x']+dock['width'] and dock['y']<=y<dock['y']+(194 if state()['moreOptions'] else 148):button(20)
        x,y=point(*p);c.send(f'click {x} {y}')
    def zoom_at(p):x,y=point(*p);c.send(f'move {x} {y}');c.send('wheel 1')
    try:
        c.jump(29);win=c.window();key(109);button(2);original_feet=feet()
        button(21);assert precision()['outline'];button(7)
        for q in ((280,230),(350,230),(345,350),(290,350)):click(q)
        key(13);c.wait(lambda:bool(state()['document']['foreground']),'outline created')
        assert len(ring())==4
        q=ring()[0][:];click(q);assert state()['node']==0
        key(1073741903);c.wait(lambda:abs(ring()[0][0]-q[0]-.25)<1e-5,'quarter-pixel nudge')
        button(10);assert ring()[0]==q;button(11);assert abs(ring()[0][0]-q[0]-.25)<1e-5
        a,b=ring()[:2];mid=((a[0]+b[0])/2,(a[1]+b[1])/2)
        button(25);click(mid);c.wait(lambda:len(ring())==5,'point inserted at edge');assert state()['node']==1
        button(26);c.wait(lambda:len(ring())==4,'point deleted');button(10);assert len(ring())==5
        # Shift-drag moves one tenth as far without changing the actor position.
        q=ring()[1][:];x,y=point(*q);c.send('hold 1073742049 3');c.send(f'down {x} {y}');c.send(f'move {x+10} {y}');c.send(f'up {x+10} {y}');c.send('release 1073742049 0')
        moved=ring()[1][0]-q[0];assert 0<moved<2,(q,ring()[1]);button(10)
        button(24);button(24);assert precision()['fill']==0
        target=(315,250);cx,cy=projected(*target)
        c.screenshot('precision-overview');zoom_at(target);assert precision()['zoom']==2;zoom_at(target)
        assert precision()['zoom']==4
        # Actual scene pixels must magnify with the editing geometry.
        c.screenshot('precision-zoom-4x')
        a=Image.open(c.output/'precision-overview.png').convert('RGB');b=Image.open(c.output/'precision-zoom-4x.png').convert('RGB')
        px,py=round(cx*a.width/854),round(cy*a.height/480);radius=10
        src=a.crop((px-radius,py-radius,px+radius,py+radius))
        dst=b.crop((px-radius*4,py-radius*4,px+radius*4,py+radius*4)).resize(src.size,Image.Resampling.BOX)
        error=sum(ImageStat.Stat(ImageChops.difference(src,dst)).mean)/3
        assert error<25,('Zoomed artwork must match mask coordinates',error)
        c.send('wheel -1');assert precision()['zoom']==2
        c.send('wheel 1');assert precision()['zoom']==4
        # Pick the selected upper edge at 4x, then nudge using full precision.
        q=ring()[1][:];click(q);before=ring()[1][:];key(1073741905)
        c.wait(lambda:abs(ring()[1][1]-before[1]-.25)<1e-5,'pick and nudge while zoomed');button(10)
        v=precision().copy();x,y=screen(canvas()/2,300);c.send('hold 32');c.send(f'down {x} {y}');c.send(f'move {x+24} {y+12}');c.send(f'up {x+24} {y+12}');c.send('release 32')
        c.wait(lambda:precision()['focusX']!=v['focusX'],'pan zoomed scene');assert not precision()['pan'] and feet()==original_feet
        key(116);assert state()['test'];button(6);assert not state()['test'];button(27);assert precision()['zoom']==1
        for width,height in ((1280,827),(1720,720)):
            c.send(f'resize {width} {height}');win=c.window();zoom_at(target)
            assert precision()['zoom']==2
            q=ring()[1][:];click(q);assert state()['node']==1
            key(1073741903);assert abs(ring()[1][0]-q[0]-.25)<1e-5;button(10)
            c.screenshot(f'precision-{width}x{height}');key(48);assert precision()['zoom']==1
        button(4);assert not state()['dirty'];saved=ring();assert json.loads(masks.read_text())['scenes']
        # Ordinary scrolling-room coordinates use the same zoom/pick transform.
        c.jump(14);win=c.window();button(2);button(21) if not precision()['outline'] else None;button(7)
        left=c.state()['cameraLeft'];points=((left+250,270),(left+300,270),(left+300,330),(left+250,330))
        for q in points:click(q)
        key(13);c.wait(lambda:bool(state()['document']['foreground']),'scrolling-room outline')
        zoom_at((left+275,300));q=ring()[0][:];click(q);key(1073741903);assert abs(ring()[0][0]-q[0]-.25)<1e-5
        c.jump(29);assert precision()['zoom']==1 and ring()==saved
        print('PASS: custom/scrolling-room zoom and picking, actual zoomed artwork, polygon creation, fractional nudges, fine drag, edge insertion/deletion, undo/redo, pan/input isolation, display ratios, save and room restoration',flush=True)
    finally:c.close()

if __name__=='__main__':main()
