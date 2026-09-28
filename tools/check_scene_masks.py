#!/usr/bin/env python3
"""Exercise live mask authoring with isolated saves/config and engine-local input."""
import argparse
import json
import time
from pathlib import Path
from check_aspect import Check, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.context/mask-editor-check')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    masks=out/'scene-masks.json';masks.write_text('{"schemaVersion":1,"scenes":{}}\n')
    c=Check(out/'first',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    def state():return c.state().get('maskEditor',{})
    def screen(x,y):
        # Same cover geometry as the engine: the centered visible viewport.
        status=c.state();win=c.window();vw=status['viewportWidth'];canvas=max(854,vw)
        h=max(win['height'],win['width']*9/16);width=h*canvas/480
        return round((win['width']-width)/2+x*h/480),round((win['height']-h)/2+y*h/480)
    def click(x,y):
        px,py=screen(x,y);c.send(f'click {px} {py}')
    def button(action):
        tail=[21,22,15,23,13,24] if state().get('foreground') else [2,3,15,16,13,14] if state().get('water') else [20,25,3,19,13,14]
        slots=[0,1,18,4,12,5,6,27 if state().get('foreground') else 7,28 if state().get('foreground') else 8 if state().get('water') else 17,9,10,11]+tail
        c.wait(lambda:state().get('visible'),'editor ready for toolbar')
        playing=state().get('test')
        slot=slots.index(action);c.mask_button(slot)
        if action==4:c.wait(lambda:state()['test']!=playing,'Test mode changed')
    def key(code,mod=0):c.send(f'key {code} {mod}')
    try:
        c.jump(14);key(109);c.wait(lambda:state().get('visible'),'editor visible')
        c.screenshot('walkable-editor')
        doc=state()['document'];assert doc['walkboxes'] and doc['water']['zones']
        ego=next(a for a in c.state()['actors'] if a['id']==1)
        # Editing pointer input must not cause walking.
        click(480,410);time.sleep(.5)
        after=next(a for a in c.state()['actors'] if a['id']==1)
        assert (after['x'],after['y'])==(ego['x'],ego['y'])
        # Reshape a shared boundary and exercise native routing without moving actors.
        def native_point(x,y):
            return screen(x-c.state()['cameraLeft'],y-c.state()['cameraTop'])
        before_walk=state()['document']['walkboxes']
        px,py=native_point(344,430)
        c.send(f'click {px} {py}')
        c.send(f'down {px} {py}');c.send(f'move {px+6} {py}');c.send(f'up {px+6} {py}')
        c.wait(lambda:state()['document']['walkboxes']!=before_walk,'walkbox drag')
        button(10);c.wait(lambda:state()['document']['walkboxes']==before_walk,'walkbox undo')
        # New boxes inherit the selected box and keep stable IDs when deleted.
        px,py=native_point(246,367);c.send(f'click {px} {py}')
        c.wait(lambda:state()['selected']==12,'select source walkbox')
        button(7)
        for x,y in ((200,367),(246,367),(246,370),(200,370)):
            px,py=native_point(x,y);c.send(f'click {px} {py}')
        c.wait(lambda:len(state()['document']['walkboxes'])==len(before_walk)+1,'add walkbox')
        added=state()['document']['walkboxes'][-1]
        assert added['id']==len(before_walk) and added['parent']==12
        def actor():return next(a for a in c.state()['actors'] if a['id']==1)
        def walk(x,y):
            (c.output/'walk-to.txt').write_text(f'{x} {y}\n')
            c.wait(lambda:abs(actor()['x']-x)<=2 and abs(actor()['y']-y)<=2,'walk through edited navigation',40)
        button(4);walk(210,368);button(4)
        button(9);c.wait(lambda:'actor' in state()['error'],'reject disabling occupied walkbox')
        assert not state()['document']['walkboxes'][-1]['disabled']
        button(4);walk(433,368);button(4)
        # Re-select the new area after the rejected delete clears selection.
        px,py=native_point(210,368);c.send(f'click {px} {py}')
        button(9);c.wait(lambda:state()['document']['walkboxes'][-1]['disabled'],'disable walkbox')
        assert len(state()['document']['walkboxes'])==len(before_walk)+1
        button(10);c.wait(lambda:not state()['document']['walkboxes'][-1]['disabled'],'restore walkbox')
        button(12);c.wait(lambda:not state()['dirty'],'save walkboxes')
        c.save_load(1,1,14);c.save_load(2,1,14)
        c.wait(lambda:state()['visible'],'editor after savegame load')
        assert len(state()['document']['walkboxes'])==len(before_walk)+1
        button(14);c.wait(lambda:state()['document']['walkboxes']==before_walk,'reset walkboxes')
        button(1);c.wait(lambda:state()['water'],'Water tab')
        original=state()['document']['water']
        # Pick a visible water node below the toolbar in full-room coordinates.
        roomw=c.state()['width']/4;roomh=c.state()['height']/4;camera=c.state()['cameraLeft']
        idx,p=next((i,p) for i,p in enumerate(original['zones'][0]) if 30<p[0]*roomw/1000-camera<800 and p[1]*roomh/1000>170)
        px,py=screen(p[0]*roomw/1000-camera,p[1]*roomh/1000)
        c.send(f'down {px} {py}');c.send(f'move {px+5} {py}');c.send(f'up {px+5} {py}')
        c.wait(lambda:state()['dirty'],'water drag applied')
        assert state()['document']['water']!=original,state()
        button(10);c.wait(lambda:state()['document']['water']==original,'undo')
        button(11);c.wait(lambda:state()['document']['water']!=original,'redo')
        edited=state()['document']['water']
        # Add and remove an exclusion polygon, then return to the dragged mask.
        holes=len(edited['holes']);button(8)
        for x,y in ((300,240),(330,240),(315,260)):click(x,y)
        key(13);c.wait(lambda:len(state()['document']['water']['holes'])==holes+1,'add water hole')
        button(9);c.wait(lambda:len(state()['document']['water']['holes'])==holes,'delete water hole')
        assert state()['document']['water']==edited
        button(12)
        c.wait(lambda:not state()['dirty'],'save');assert len(json.loads(masks.read_text())['scenes'])==1
        c.screenshot('water-editor')
        # Closing/reopening and a room round trip retain the draft.
        key(109);c.wait(lambda:not state()['open'],'close')
        c.jump(13);key(109);c.wait(lambda:state()['visible'],'map editor')
        c.screenshot('map-editor');key(109)
        c.jump(29);key(109);c.wait(lambda:state()['visible'],'voodoo editor')
        c.screenshot('voodoo-editor');key(109)
        c.jump(11);key(109);c.wait(lambda:state()['visible'],'automatic water editor')
        button(1);assert not state()['document']['water']['authored']
        button(15);c.wait(lambda:state()['document']['water']['authored'],'convert automatic coverage')
        assert state()['document']['water']['zones']
        # A new polygon can use the widescreen side painting, outside the original 640px center.
        button(7)
        for x,y in ((20,300),(80,300),(80,380),(20,380)):click(x,y)
        key(13);c.wait(lambda:state()['selected']>=0,'add side water zone')
        newest=state()['document']['water']['zones'][-1]
        assert min(p[0] for p in newest)<50,newest
        c.screenshot('automatic-water-and-side-zone')
        button(14);c.wait(lambda:not state()['document']['water']['authored'],'reset automatic coverage');key(109)
        c.jump(14);key(109);c.wait(lambda:state()['visible'],'return to edited room')
        assert state()['document']['water']==edited
        button(4);c.wait(lambda:state()['test'],'Test mode');key(116);c.wait(lambda:not state()['test'],'T returns to editing')
        # Refuse overwriting external edits while retaining the live draft.
        external=json.loads(masks.read_text());external['externalNote']='preserve me';masks.write_text(json.dumps(external))
        button(12);c.wait(lambda:'externally' in state()['error'],'external conflict')
        assert json.loads(masks.read_text())['externalNote']=='preserve me'
    finally:c.close()
    c=Check(out/'restart',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    try:
        c.jump(14);key(109);c.wait(lambda:state()['visible'],'editor after restart')
        assert state()['document']['water']==edited
        button(14);c.wait(lambda:state()['document']['water']==original,'reset original');button(13)
        c.wait(lambda:state()['document']['water']==edited,'revert saved')
        button(12);assert json.loads(masks.read_text())['externalNote']=='preserve me'
        for width,height in ((1280,800),(1720,720)):
            c.send(f'resize {width} {height}');c.screenshot(f'editor-{width}x{height}')
        print('PASS: native overlay, walkbox drag/add/disable, water drag/holes, input isolation, undo/redo, save/reload, reset, scene transitions, Test mode, external conflicts, display ratios',flush=True)
    finally:c.close()

if __name__=='__main__':main()
