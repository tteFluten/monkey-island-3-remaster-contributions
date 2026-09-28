#!/usr/bin/env python3
"""Exercise original clip conversion beside existing precise hide/show edits."""
import argparse
import json
import re
from pathlib import Path
from check_aspect import Check, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.context/clipping-nodes')
    parser.add_argument('--rooms-only', action='store_true')
    args=parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    masks = out / 'masks.json'
    masks.write_text('{"schemaVersion":1,"scenes":{}}')
    c = Check(out / 'native', config_overrides={'comi': {'hd_scene_masks_path': str(masks)}})
    def state(): return c.state()['maskEditor']
    def clips(): return state()['document']['foreground']
    def key(code): c.send(f'key {code}')
    def button(slot): c.mask_button(slot)
    header = (ROOT / 'tools/engine/hd_voodoo_exterior.h').read_text()
    axes = {axis: [tuple(map(float, p)) for p in re.findall(r'\{(\d+),(\d+)\}', re.search(r'k' + axis + r'\[\] = (.*?);', header, re.S)[1])] for axis in ('X', 'Y')}
    def paint(v, axis):
        ps = axes[axis]
        i = next((i for i in range(1, len(ps)) if v <= ps[i][0]), len(ps)-1)
        a, b = ps[i-1:i+1]
        return a[1] + (b[1]-a[1])*(v-a[0])/(b[0]-a[0])
    def point(p):
        scene=c.state();canvas=max(854,scene['viewportWidth'])
        if scene.get('voodooExterior'):x, y = paint(p[0], 'X') * canvas/2048, paint(p[1], 'Y') * 480/1152
        else:x,y=p[0]-scene['cameraLeft']+(canvas-scene['viewportWidth'])/2,p[1]-scene['cameraTop']
        controls = state()['controls']
        dock = next(b for b in controls if b['slot'] == 20)
        first = next(b for b in controls if b['slot'] == 0)
        if first['x'] <= x <= dock['x']+dock['width'] and dock['y'] <= y < dock['y']+(194 if state()['moreOptions'] else 148):
            button(20)
        win = c.window()
        h = max(win['height'], win['width']*9/16)
        return round((win['width']-h*canvas/480)/2+x*h/480), round((win['height']-h)/2+y*h/480)
    def click(p):
        x, y = point(p)
        c.send(f'click {x} {y}')
    def rectangle(a,b,slot):
        button(slot)
        x,y=point(a);xx,yy=point(b)
        c.send(f'down {x} {y}');c.send(f'move {xx} {yy}');c.send(f'up {xx} {yy}')
    try:
        if not args.rooms_only:
            c.jump(29);key(109);button(2)
            actor = next(a for a in c.state()['actors'] if a['id']==1)
            feet = actor['x'], actor['y']
            button(6)
            assert clips() and clips()[0]['zones'] and clips()[0]['replace'], state()['error']
            original = clips()
            assert state()['selected'] >= 0
            button(6);assert clips()==original, 'Repeated Edit nodes must not duplicate native shapes'
            button(10);assert not clips(), 'Native conversion must be one undoable edit'
            button(11);assert clips()==original
            button(17);assert not clips()
            rectangle((370,270),(415,350),7)
            q=clips()[0]['zones'][0][0]
            click(q);key(1073741903)
            assert abs(clips()[0]['zones'][0][0][0]-q[0]-.25)<1e-5
            rectangle((382,290),(402,325),8)
            authored=clips()[0]
            # Converting alongside authored work used to be rejected. Preserve the
            # exact fractional vertices, stable indices, and latest-shape priority.
            button(6);merged=clips()[0]
            assert not state()['error'], state()['error']
            assert len(merged['zones'])>len(authored['zones'])
            assert merged['zones'][:len(authored['zones'])]==authored['zones']
            assert merged['holes'][:len(authored['holes'])]==authored['holes']
            assert merged['order'][-len(authored['order']):]==authored['order']
            button(10);assert clips()==[authored]
            button(11);assert clips()==[merged]
            button(6);assert clips()==[merged]
            # All authored and original rings are reachable, including holes.
            for _ in range(len(merged['zones'])+len(merged['holes'])):button(43)
            assert state()['selected']==0
            button(42);button(43);assert state()['selected']==0
            # An unselected original corner can be grabbed directly.
            ring_id=next(i for i,r in enumerate(merged['zones'][1:],1) if any(200<paint(p[1],'Y')*480/1152<410 and 80<paint(p[0],'X')*854/2048<770 for p in r))
            p=next(p for p in merged['zones'][ring_id] if 200<paint(p[1],'Y')*480/1152<410 and 80<paint(p[0],'X')*854/2048<770)
            click(p);assert state()['node']>=0 and state()['selected']!=0
            c.screenshot('editable-original-clips')
            key(116);assert state()['test'];button(6);assert not state()['test']
            button(4);assert not state()['dirty'];saved=clips()
            actor=next(a for a in c.state()['actors'] if a['id']==1)
            assert (actor['x'],actor['y'])==feet, 'Editor clicks must not reach gameplay'
            c.jump(14);c.jump(29);assert clips()==saved
            c.close()
            c=Check(out/'restart',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
            c.jump(29);key(109);button(2);assert clips()==saved
        else:key(109)
        # Exercise every depth layer in ordinary and scrolling rooms as well.
        for room in (9,14):
            c.jump(room);button(2);converted=0
            for _ in range(state()['planes']):
                plane=state()['plane'];button(6)
                layer=next((f for f in clips() if f['plane']==plane),None)
                if layer and (layer['zones'] or layer['holes']):
                    assert not state()['error'], (room,plane,state()['error'])
                    converted+=1;before=clips();button(6);assert clips()==before
                    button(43);assert state()['selected']>=0
                else:assert 'No clipping on this layer' in state()['error'], (room,plane,state()['error'])
                button(13)
            assert converted, ('Expected native clipping in room',room)
        button(6)
        f=next(f for f in clips() if f['plane']==state()['plane'])
        scene=c.state()
        candidates=[p for r in f['zones'] for p in r if 30<p[0]-scene['cameraLeft']<scene['viewportWidth']-30 and 175<p[1]-scene['cameraTop']<415]
        assert candidates
        click(candidates[len(candidates)//2]);assert state()['node']>=0
        if state()['moreOptions']:button(19)
        c.screenshot('panorama-editable-clips')
        print('PASS: room 9 and scrolling room 14 clipping layers, repeated conversion, direct node picking, shape cycling' + ('' if args.rooms_only else '; authored precision/priority/IDs, history, input isolation, save/room/restart'),flush=True)
    finally:c.close()

if __name__=='__main__':main()
