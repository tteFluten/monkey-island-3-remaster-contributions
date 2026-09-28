#!/usr/bin/env python3
"""Exercise scene-local animation placement in the native engine with isolated files."""
import argparse,json,re,time
from pathlib import Path
from PIL import Image
from check_aspect import Check,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'.context/animation-check')
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=True)
    masks=out/'masks.json';masks.write_text('{"schemaVersion":1,"scenes":{},"unrelated":"preserved"}')
    c=Check(out/'first',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    def state():return c.state()['maskEditor']
    def key(n,mod=0):c.send(f'key {n} {mod}')
    def button(n):c.mask_button(n)
    def visual(actor=33):return next(v for v in state()['animationVisuals'] if v['actor']==actor)
    def offsets():return state()['document']['animations']
    header=(ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    axes={axis:[tuple(map(float,p)) for p in re.findall(r'\{(\d+),(\d+)\}',re.search(r'k'+axis+r'\[\] = (.*?);',header,re.S)[1])] for axis in ('X','Y')}
    def paint(v,axis):
        points=axes[axis];i=next((i for i in range(1,len(points)) if v<=points[i][0]),len(points)-1);a,b=points[i-1:i+1]
        return a[1]+(b[1]-a[1])*(v-a[0])/(b[0]-a[0])
    def project(x,y):return paint(x,'X')*854/2048,paint(y,'Y')*480/1152
    win={}
    def screen(x,y):
        x,y=project(x,y);h=max(win['height'],win['width']*9/16)
        return round((win['width']-h*854/480)/2+x*h/480),round((win['height']-h)/2+y*h/480)
    def center(v):return v['left']+v['x']+v['width']/2,v['top']+v['y']+v['height']/2
    def select():
        v=visual();x,y=screen(*center(v));c.send(f'click {x} {y}');assert state()['animationSelected']==v['key'];return v
    def actor_state():return [(a['id'],a['x'],a['y']) for a in c.state()['actors']]
    try:
        c.jump(29)
        (c.output/'walk-to.txt').write_text('400 340\n')
        c.wait(lambda:any(a['id']==1 and abs(a['x']-400)<=2 and abs(a['y']-340)<=2 for a in c.state()['actors']),'clear the flame comparison area',40)
        win=c.window();key(109);button(28);assert state()['animations']
        c.wait(lambda:any(v['actor']==33 for v in state()['animationVisuals']),'editable flame')
        original_actors=actor_state();v=select();ident=v['key'];assert not offsets()
        key(1073741903);c.wait(lambda:offsets().get(ident)==[.25,0],'quarter-pixel nudge')
        assert all(q['x']==q['y']==0 for q in state()['animationVisuals'] if q['key']!=ident)
        button(10);assert not offsets();button(11);assert offsets()[ident]==[.25,0]
        # Hold a drag across several animation frames; changing PNG bounds must not cancel it.
        v=visual();x,y=screen(*center(v));c.send(f'down {x} {y}');frames=set()
        for _ in range(5):frames.add(visual()['cel']);time.sleep(.2)
        assert state()['animationDrag'] and len(frames)>1,frames
        c.send(f'move {x+20} {y+10}');c.send(f'up {x+20} {y+10}')
        moved=offsets()[ident];assert moved[0]>.25 and moved[1]>0
        assert actor_state()==original_actors,'Placement changed script positions'
        button(10);assert offsets()[ident]==[.25,0]
        # Escape cancels the live preview without creating an undo entry.
        v=visual();x,y=screen(*center(v));c.send(f'down {x} {y}');c.send(f'move {x+30} {y}');key(27);c.send(f'up {x+30} {y}')
        assert offsets()[ident]==[.25,0] and not state()['animationDrag']
        # Move far enough to verify rendered pixels leave the original flame location.
        button(36);assert not offsets();key(109);c.screenshot('flame-original');key(109)
        select();button(35) # one native pixel, Shift moves five
        for _ in range(12):key(1073741903,3)
        assert offsets()[ident]==[60,0];key(109);c.screenshot('flame-moved');key(109)
        def light(name,shift):
            im=Image.open(c.output/(name+'.png')).convert('RGB');a=project(v['left']+shift-2,v['top']-3);b=project(v['left']+shift+v['width']+2,v['top']+v['height']+3)
            roi=im.crop((round(a[0]*im.width/854),round(a[1]*im.height/480),round(b[0]*im.width/854),round(b[1]*im.height/480)))
            return sum(1 for r,g,b in roi.getdata() if r>175 and g>165 and b>100)
        old_before,old_after=light('flame-original',0),light('flame-moved',0)
        new_before,new_after=light('flame-original',60),light('flame-moved',60)
        assert old_before>old_after+20 and new_after>new_before+20,(old_before,old_after,new_before,new_after)
        # The sprite remains movable even when its original location is hidden by Guybrush.
        (c.output/'walk-to.txt').write_text('273 346\n')
        c.wait(lambda:any(a['id']==1 and abs(a['x']-273)<=2 and abs(a['y']-346)<=2 for a in c.state()['actors']),'occlude original flame position',40)
        key(109);c.screenshot('flame-moved-occluded-source');key(109)
        assert light('flame-moved-occluded-source',60)>20
        select();c.screenshot('animation-editor')
        key(116);assert state()['test'];button(6);assert not state()['test']
        button(4);assert not state()['dirty'];saved=offsets().copy()
        assert json.loads(masks.read_text())['unrelated']=='preserved'
        button(36);assert not offsets();button(37);assert offsets()==saved
        # Per-scene draft retention and cancellation on a scripted room transition.
        v=visual();x,y=screen(*center(v));c.send(f'down {x} {y}');c.send(f'move {x+20} {y}');assert state()['animationDrag']
        c.jump(14);assert not state()['animationDrag'];c.jump(29);assert offsets()==saved
        # Reloading a game save must keep authoring offsets independent of actor state.
        c.save_load(1,2,29);c.save_load(2,2,29);assert offsets()==saved
        key(1073741903);c.jump(14);c.jump(29);assert offsets()==saved # no selection after room entry
    finally:c.close()
    c=Check(out/'restart',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    try:
        c.jump(29);win=c.window();key(109);button(28);assert offsets()==saved
        for width,height in ((1280,827),(1720,720)):
            c.send(f'resize {width} {height}');win=c.window();select();before=offsets()[ident][:];key(1073741905)
            assert offsets()[ident]==[before[0],before[1]+.25];button(10);assert offsets()==saved
        # External modifications report a conflict and retain the unsaved offset.
        select();key(1073741903);draft=offsets().copy();masks.write_text(masks.read_text()+'\n');button(4)
        assert offsets()==draft and state()['dirty'] and 'externally' in state()['error']
        print('PASS: animation frames keep running, independent flame instances, drag/nudge/cancel/history, actual rendered movement, input isolation, scene transitions, save/load/restart, display ratios, external conflicts',flush=True)
    finally:c.close()

if __name__=='__main__':main()
