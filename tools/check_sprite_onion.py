#!/usr/bin/env python3
"""Native onion skins and additive frame/sequence alignment for heads and props."""
import argparse,json,re,time
from pathlib import Path
from check_aspect import Check,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'.context/sprite-onion-check')
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=True);masks=out/'masks.json';masks.write_text('{"schemaVersion":1,"scenes":{}}')
    c=Check(out/'first',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    def state():return c.state()['maskEditor']
    def frames():return state()['spriteFrames']
    def key(n,mod=0):c.send(f'key {n} {mod}')
    def button(n):c.mask_button(n)
    def offsets():return state()['document']['animations']
    def flame():return next(v for v in state()['animationVisuals'] if v['actor']==33)
    header=(ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    axes={axis:[tuple(map(float,p)) for p in re.findall(r'\{(\d+),(\d+)\}',re.search(r'k'+axis+r'\[\] = (.*?);',header,re.S)[1])] for axis in ('X','Y')}
    def paint(v,axis):
        points=axes[axis];i=next((i for i in range(1,len(points)) if v<=points[i][0]),len(points)-1);a,b=points[i-1:i+1]
        return a[1]+(b[1]-a[1])*(v-a[0])/(b[0]-a[0])
    def screen(x,y):
        w=c.window();h=max(w['height'],w['width']*9/16)
        return round((w['width']-h*854/480)/2+paint(x,'X')*854/2048*h/480),round((w['height']-h)/2+paint(y,'Y')/1152*h)
    try:
        c.jump(29);key(109);button(28);v=flame();x,y=screen(v['left']+v['width']/2,v['top']+v['height']/2);c.send(f'click {x} {y}')
        c.wait(lambda:len(frames()['captured'])>=4,'capture flame neighbors')
        button(39);assert frames()['frameMode'];frame=frames()['frame'];single=frames()['frameKey'];group=v['key']
        key(1073741903);assert offsets()=={single:[.25,0]}
        # Status samples at 10 Hz while flames advance at 20 Hz. Two adjacent
        # corrections guarantee a positive observation regardless of sampling
        # phase, while the remaining frames must retain zero correction.
        button(41);neighbor=frames()['frame'];neighbor_key=frames()['frameKey']
        key(1073741903);key(1073741903);assert offsets()[neighbor_key]==[.5,0]
        seen=set();end=time.monotonic()+4
        while time.monotonic()<end:
            live=flame();seen.add(live['cel']);expected=.25 if live['cel']==frame else .5 if live['cel']==neighbor else 0
            assert abs(live['x']-expected)<1e-5;time.sleep(.073)
        assert seen.intersection({frame,neighbor}) and len(seen)>2,seen
        button(10);button(10);assert offsets()=={single:[.25,0]}
        button(39);assert not frames()['frameMode'];key(1073741906)
        assert offsets()[group]==[0,-.25] and offsets()[single]==[.25,0]
        button(41);assert frames()['frameMode'] and frames()['frame']!=frame;second=frames()['frameKey'];key(1073741905)
        assert offsets()[second]==[0,.25];button(10);assert second not in offsets();button(11);assert offsets()[second]==[0,.25]
        c.screenshot('flame-onion');button(38);assert not frames()['onion'];c.screenshot('flame-no-neighbors');button(38)
        button(4);saved_animations=offsets().copy();assert not state()['dirty']
        # Head snapshots use the same controls, with source-space offsets and mirroring.
        key(104);c.wait(lambda:bool(frames()['captured']) and state()['headDebug']['valid'],'head capture')
        button(39);assert frames()['frameMode'];head_frame=frames()['frameKey'];head_cel=frames()['frame'];key(1073741906)
        assert frames()['y']==-1;button(4)
        doc=json.loads(masks.read_text());assert doc['characterHeads'][head_frame]==[0,-1]
        button(39);assert not frames()['frameMode'];key(1073741906);button(4)
        head_group=state()['headDebug']['key'];doc=json.loads(masks.read_text());assert doc['characterHeads'][head_group]==[0,-1] and doc['characterHeads'][head_frame]==[0,-1]
        h=state()['headDebug'];assert h['y']==-1+(-1 if h['cel']==head_cel else 0)
        button(12);h=state()['headDebug'];assert h['y']==(-1 if h['cel']==head_cel else 0)
        button(13);h=state()['headDebug'];assert h['y']==-1+(-1 if h['cel']==head_cel else 0)
        button(39);assert frames()['frameMode']
        for _ in range(64):
            if frames()['frame']==head_cel:break
            button(41)
        assert frames()['frame']==head_cel;c.screenshot('head-onion')
        # The selected PNG preview can be dragged independently of its sequence offset.
        h=state()['headDebug'];x,y=screen(h['left']+h['width']/2,h['top']+h['height']/2+h['y']*h['height']/h['sourceHeight'])
        c.send(f'down {x} {y}');c.send(f'move {x+8} {y}');c.send(f'up {x+8} {y}')
        assert frames()['x']!=0;button(12);assert frames()['x']==0 and state()['headDebug']['y']==-2
        button(4);saved_heads=json.loads(masks.read_text())['characterHeads'];assert saved_heads[head_group]==[0,-1]
        key(116);assert state()['test'];button(6);assert not state()['test']
        c.jump(14);c.jump(29);assert offsets()==saved_animations
    finally:c.close()
    c=Check(out/'restart',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    try:
        c.jump(29);key(109);button(28);assert offsets()==saved_animations
        key(104);c.wait(lambda:state()['headDebug']['valid'],'head restart')
        assert json.loads(masks.read_text())['characterHeads']==saved_heads
        h=state()['headDebug'];assert h['y']==-1+(-1 if h['cel']==head_cel else 0)
        print('PASS: captured onion frames, individual versus whole-sequence edits, additive offsets, live frame isolation, head PNG preview drag, undo/redo, Play mode, save and restart',flush=True)
    finally:c.close()

if __name__=='__main__':main()
