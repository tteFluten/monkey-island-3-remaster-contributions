#!/usr/bin/env python3
"""Exercise sprite-local outline masks with isolated native-engine saves and overrides."""
import argparse, json, re, time
from pathlib import Path
from PIL import Image, ImageChops
from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'.context/sprite-mask-check')
    out = parser.parse_args().output.resolve(); out.mkdir(parents=True, exist_ok=True)
    masks = out/'masks.json'; masks.write_text('{"schemaVersion":1,"scenes":{},"unrelated":"preserved"}')
    c = Check(out/'first', config_overrides={'comi': {'hd_scene_masks_path': str(masks)}})
    def state(): return c.state()['maskEditor']
    def key(n, mod=0): c.send(f'key {n} {mod}')
    def button(n): c.mask_button(n)
    def doc(): return state()['document'].get('animationMasks', {})
    header = (ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    axes = {axis: [tuple(map(float, p)) for p in re.findall(r'\{(\d+),(\d+)\}', re.search(r'k'+axis+r'\[\] = (.*?);', header, re.S)[1])] for axis in ('X', 'Y')}
    def paint(v, axis):
        points = axes[axis]; i = next((i for i in range(1, len(points)) if v <= points[i][0]), len(points)-1); a,b = points[i-1:i+1]
        return a[1]+(b[1]-a[1])*(v-a[0])/(b[0]-a[0])
    window = {}
    def screen(x, y):
        x, y = paint(x,'X')*854/2048, paint(y,'Y')*480/1152
        z = state()['clipPrecision']
        if state()['animationMaskEdit'] and z['zoom']>1:
            x,y = (x-z['focusX'])*z['zoom']+427, (y-z['focusY'])*z['zoom']+240
        h = max(window['height'], window['width']*9/16)
        return round((window['width']-h*854/480)/2+x*h/480), round((window['height']-h)/2+y*h/480)
    def point(u,v):
        a=state()['animationMaskVisual']; u=1-u if a['mirror'] else u
        return screen(a['left']+u*a['width'],a['top']+v*a['height'])
    def outline(slot, points):
        button(slot)
        for p in points:
            x,y=point(*p);c.send(f'click {x} {y}')
        key(13);assert not state()['error'],state()['error']
    def select():
        v=next(v for v in state()['animationVisuals'] if v['actor']==33)
        x,y=screen(v['left']+v['width']/2,v['top']+v['height']/2);c.send(f'click {x} {y}')
        assert state()['animationSelected']==v['key'];return v
    try:
        c.jump(29);window=c.window();key(109);button(28);v=select()
        c.wait(lambda:len(state()['spriteFrames']['captured'])>=4,'flame frames')
        button(46);assert state()['animationMaskEdit'];button(38) # disable neighboring ghosts for pixel checks
        actors=[(a['id'],a['x'],a['y']) for a in c.state()['actors']]
        # Zoom around the sprite so even these tiny source frames have editable nodes.
        x,y=point(.5,.5);c.send(f'move {x} {y}');c.send('wheel 1');c.send('wheel 1')
        # Keep a partial canvas, then add a hole. Both are source-local and independent.
        outline(47,[(.08,.08),(.92,.08),(.92,.92),(.08,.92)])
        group=next(iter(doc()));before=json.loads(json.dumps(doc()))
        p=doc()[group]['zones'][0][0];x,y=point(p[0]/1000,p[1]/1000)
        c.send(f'down {x} {y}');c.send(f'move {x+4} {y+4}');c.send(f'up {x+4} {y+4}')
        assert doc()!=before and state()['node']==0,(doc(),state()['error'])
        button(10);assert doc()==before;button(11);assert doc()!=before
        key(1073741903);assert not state()['error'];button(10)
        # Insert halfway down the right edge and remove the new point.
        ring=doc()[group]['zones'][0];u=(ring[1][0]+ring[2][0])/2000;vv=(ring[1][1]+ring[2][1])/2000
        x,y=point(u,vv);button(53);c.send(f'click {x} {y}');assert len(doc()[group]['zones'][0])==5,state()['error']
        button(54);assert len(doc()[group]['zones'][0])==4
        outline(48,[(.35,.4),(.65,.4),(.65,.7),(.35,.7)]);assert len(doc()[group]['holes'])==1
        assert [(a['id'],a['x'],a['y']) for a in c.state()['actors']]==actors,'Mask clicks moved an actor'
        button(50);assert doc()[group]['edge']==1;c.screenshot('hard-outline')
        button(50);assert doc()[group]['edge']==2
        button(51);assert doc()[group]['feather']==2;c.screenshot('soft-outline')
        assert ImageChops.difference(Image.open(c.output/'hard-outline.png').convert('RGB'),Image.open(c.output/'soft-outline.png').convert('RGB')).getbbox()
        # Browsing previews does not change whole-animation scope; frame masks are additive.
        cel=state()['spriteFrames']['frame'];button(41)
        assert not state()['spriteFrames']['frameMode'] and state()['spriteFrames']['frame']!=cel
        button(39);assert state()['spriteFrames']['frameMode'];button(50)
        assert len(doc())==2;frame=next(k for k in doc() if k!=group);assert doc()[frame]['edge']==1
        button(52);assert frame not in doc();button(10);assert frame in doc()
        button(39);assert not state()['spriteFrames']['frameMode']
        button(4);saved=json.loads(json.dumps(doc()));assert not state()['dirty']
        assert json.loads(masks.read_text())['unrelated']=='preserved'
        button(55);assert state()['panelOpacity']==80;c.screenshot('menu-opacity')
        button(19) # collapse More
        # Move the entire sequence; its source-local mask remains unchanged.
        button(46);key(1073741903);assert doc()==saved
        button(46);key(116);assert state()['test'];button(6);assert not state()['test']
        button(4);c.save_load(1,2,29);c.save_load(2,2,29);assert doc()==saved
        c.jump(14);assert not state()['animationMaskEdit'];c.jump(29);assert doc()==saved
    finally:c.close()
    c=Check(out/'restart',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    try:
        c.jump(29);window=c.window();key(109);button(28);assert doc()==saved;select();button(46)
        button(52);assert group not in doc() and frame in doc();button(56);assert doc()==saved
        button(50);draft=doc();masks.write_text(masks.read_text()+'\n');button(4)
        assert state()['dirty'] and doc()==draft and 'externally' in state()['error']
        print('PASS: outline/hole creation, drag/nudge, insert/delete, undo/redo, hard/soft edges, frame/group scope, opacity, input isolation, movement, save/load, room changes, restart and external conflicts',flush=True)
    finally:c.close()

if __name__=='__main__':main()
