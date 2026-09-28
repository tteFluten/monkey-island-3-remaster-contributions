#!/usr/bin/env python3
"""Exercise head artwork positioning through native input, with isolated saves."""
import argparse
import json
import re
from pathlib import Path
from PIL import Image, ImageChops
from check_aspect import Check, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.context/head-debugger-check')
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=True)
    masks=out/'masks.json';masks.write_text('{"schemaVersion":1,"scenes":{}}\n')
    header=(ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    axes={axis:[tuple(map(float,p)) for p in re.findall(r'\{(\d+),(\d+)\}',re.search(r'k'+axis+r'\[\] = (.*?);',header,re.S)[1])] for axis in ('X','Y')}
    def paint(value,axis):
        points=axes[axis];i=next((i for i in range(1,len(points)) if value<=points[i][0]),len(points)-1)
        a,b=points[i-1:i+1];return a[1]+(b[1]-a[1])*(value-a[0])/(b[0]-a[0])
    c=Check(out/'first',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    def state():return c.state().get('maskEditor',{})
    def head():return state().get('headDebug',{})
    def position():return head()['x'],head()['y']
    def key(code,mod=0):c.send(f'key {code} {mod}')
    window={}
    def screen(x,y):
        h=max(window['height'],window['width']*9/16);canvas=max(854,c.state()['viewportWidth'])
        return round((window['width']-h*canvas/480)/2+x*h/480),round((window['height']-h)/2+y*h/480)
    def native(x,y):
        s=c.state()
        if s.get('voodooExterior'):return paint(x,'X')*854/2048,paint(y,'Y')*480/1152
        return x-s['cameraLeft']+(max(854,s['viewportWidth'])-s['viewportWidth'])/2,y-s['cameraTop']
    def button(slot):c.mask_button(slot)
    def center():
        v=head();sx=v['x']*v['width']/v['sourceWidth']*(-1 if v['mirror'] else 1);sy=v['y']*v['height']/v['sourceHeight']
        x,y=native(v['left']+sx+v['width']/2,v['top']+sy+v['height']/2)
        controls=state()['controls'];dock=next(b for b in controls if b['slot']==20);first=next(b for b in controls if b['slot']==0)
        if first['x']<=x<=dock['x']+dock['width'] and dock['y']<=y<dock['y']+(170 if state()['moreOptions'] else 124):button(20)
        return screen(x,y)
    def actor():
        a=next(a for a in c.state()['actors'] if a['id']==1);return a['x'],a['y']
    try:
        c.jump(29);window=c.window();key(109);key(104)
        c.wait(lambda:state().get('head') and head().get('valid'),'Head view')
        original=head().copy();feet=actor();alignment=original['key']
        assert position()==(0,0)
        c.screenshot('head-original-guides')
        key(109);c.screenshot('actor-original');key(109)
        # Native arrow-key events move artwork, without moving the actor.
        key(1073741906,3);key(1073741906,3)
        c.wait(lambda:position()==(0,-10),'head nudge')
        assert actor()==feet and head()['key']==alignment
        key(109);c.screenshot('actor-head-raised');key(109)
        a=Image.open(c.output/'actor-original.png').convert('RGB');b=Image.open(c.output/'actor-head-raised.png').convert('RGB')
        x1,y1=native(original['left']-5,original['top']-20);x2,y2=native(original['left']+original['width']+5,original['top']+original['height']+5)
        roi=(round(x1*a.width/854),round(y1*a.height/480),round(x2*a.width/854),round(y2*a.height/480))
        diff=ImageChops.difference(a.crop(roi),b.crop(roi))
        assert sum(max(p)>30 for p in diff.getdata())>100,'Head offset must change actual rendered pixels'
        # Body pixels below the head remain in place; the simulation does too.
        x1,y1=native(original['left']-20,original['top']+original['height']+10)
        x2,y2=native(original['left']+original['width']+20,feet[1]-10)
        roi=(round(x1*a.width/854),round(y1*a.height/480),round(x2*a.width/854),round(y2*a.height/480))
        # The live shader changes individual pixels. Compare the shirt's
        # position and area instead of requiring identical brightness.
        shirt=[]
        for crop in (a.crop(roi),b.crop(roi)):
            pixels=[(i%crop.width,i//crop.width) for i,p in enumerate(crop.getdata()) if min(p)>165 and max(p)-min(p)<55]
            assert len(pixels)>50,'Body test must contain visible shirt pixels'
            shirt.append((len(pixels),*[sum(p[axis] for p in pixels)/len(pixels) for axis in (0,1)]))
        assert abs(shirt[0][0]-shirt[1][0])<shirt[0][0]*.1 and all(abs(shirt[0][axis]-shirt[1][axis])<2 for axis in (1,2)),'Body artwork must stay in place'
        button(12);c.wait(lambda:position()==(0,-5),'undo nudge')
        button(12);c.wait(lambda:position()==(0,0),'undo again')
        button(13);c.wait(lambda:position()==(0,-5),'redo')
        button(14);key(1073741903)
        expected=-.25 if head()['mirror'] else .25
        c.wait(lambda:position()==(expected,-5),'quarter-pixel nudge')
        before=position();x,y=center();c.send(f'down {x} {y}');c.send(f'move {x+9} {y+6}')
        c.wait(lambda:head()['drag'] and position()!=before,'live head drag')
        key(27);c.send(f'up {x+9} {y+6}')
        c.wait(lambda:not head()['drag'] and position()==before,'cancel head drag')
        x,y=center();c.send(f'down {x} {y}');c.send(f'move {x+9} {y+6}');c.send(f'up {x+9} {y+6}')
        c.wait(lambda:not head()['drag'] and position()!=before,'commit head drag')
        edited=position();assert actor()==feet
        button(17);c.wait(lambda:head()['original'] and position()==(0,0),'peek original')
        button(17);c.wait(lambda:not head()['original'] and position()==edited,'restore edited head')
        key(115,192);c.wait(lambda:not head()['dirty'],'save head offsets')
        saved=json.loads(masks.read_text());assert saved['characterHeads'][alignment]==list(edited) and saved['scenes']=={}
        c.screenshot('head-debugger-edited')
        c.save_load(1,2,29);c.save_load(2,2,29)
        c.wait(lambda:head().get('valid') and head()['key']==alignment,'head alignment after game save/load')
        assert position()==edited
        # A room transition cancels an unfinished drag and keeps saved offsets.
        x,y=center();c.send(f'down {x} {y}');c.send(f'move {x+12} {y+4}');c.jump(14)
        assert not head()['drag']
        c.save_load(2,2,29);c.wait(lambda:head()['key']==alignment,'return to saved alignment');assert position()==edited
        # Refuse external-file conflicts without dropping live head edits.
        key(1073741906);draft=position();external=json.loads(masks.read_text());external['externalNote']='keep';masks.write_text(json.dumps(external))
        key(115,192);c.wait(lambda:'externally' in state()['error'],'head save conflict')
        assert head()['dirty'] and position()==draft
        game_save=c.output/'saves/comi.s02'
    finally:c.close()
    c=Check(out/'restart',config_overrides={'comi':{'hd_scene_masks_path':str(masks)}},save_source=game_save.parent)
    try:
        c.jump(29)
        c.save_load(2,2,29)
        window=c.window();key(109);button(18)
        c.wait(lambda:state()['head'] and head()['valid'] and head()['key']==alignment,'head after restart')
        assert position()==edited and not head()['dirty']
        button(11);c.wait(lambda:position()==(0,0),'reset head');button(16)
        c.wait(lambda:position()==edited,'revert saved head')
        for width,height in ((1280,827),(1720,720)):
            c.send(f'resize {width} {height}');window=c.window()
            before=position();x,y=center();c.send(f'down {x} {y}');c.send(f'move {x+7} {y}');c.send(f'up {x+7} {y}')
            c.wait(lambda:position()!=before,'head drag at display ratio');button(12)
            c.wait(lambda:position()==before,'undo at display ratio');c.screenshot(f'head-editor-{width}x{height}')
        key(116);c.wait(lambda:state()['test'],'head Test mode');button(6)
        c.wait(lambda:not state()['test'],'head Select returns to editing')
        print('PASS: actual head pixels move, body/feet unchanged, drag/nudge/cancel, mirroring-aware offsets, undo/redo, fine steps, original preview, head reset, save/load/restart, external conflicts, room transitions, display ratios',flush=True)
    finally:c.close()


if __name__=='__main__':main()
