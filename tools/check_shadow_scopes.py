#!/usr/bin/env python3
"""Check explicit global/scene shadow controls using isolated authoring files."""
import argparse
import json
import math
from pathlib import Path
from check_aspect import Check, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.context/shadow-scopes')
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=True)
    grades=out/'color-grades.json'
    grades.write_text(json.dumps({'schemaVersion':2,'global':{'shadowOffsetX':-3,'shadowOffsetY':-5,'shadowWidth':95,'shadowOpacity':22},'rooms':{'14':{'shadowOffsetY':6,'shadowWidth':120,'contrast':4},'15':{'shadowOffsetX':9,'brightness':8}}}))
    overrides={'scummvm':{'hd_film_enabled':'false'}}
    c=Check(out/'first',color_grades_path=grades,config_overrides=overrides)
    def data():return json.loads(grades.read_text())
    def room(n=14):return data()['rooms'].get(str(n),{})
    def key(n,mod=0):c.send(f'key {n} {mod}')
    def click(x,y):
        win=c.window();sw,sh=win['width'],win['height'];vw=c.state()['viewportWidth']
        # The native Look panel docks inside the visible part of the game canvas.
        fw,fh=sw,sw*9//16
        if (vw>=864 and fh<sh) or (vw<864 and fh>sh):fh=sh;fw=(sh*16+(8 if vw>=864 else 0))//9
        dw=fh*vw//480;dx=(sw-fw)//2+(fw-dw)//2;dy=(sh-fh)//2
        left=math.ceil(-dx*vw/dw) if dx<0 else 0
        right=(sw-dx)*vw//dw if dx+dw>sw else vw
        top=math.ceil(-dy*480/fh) if dy<0 else 0
        panel=max(left+8,right-308)
        c.send(f'click {round(dx+(panel+x)*dw/vw)} {round(dy+(top+8+y)*fh/480)}')
    def scope(global_):click(220 if global_ else 75,4+16+7)
    def value(row,plus=True):click(281 if plus else 255,4+(row+3)*16+7)
    def position():click(140,4+13*16+7)
    def all_global():click(140,4+14*16+7)
    def open_shadows():
        key(109);c.mask_button(45)
        assert not c.state()['maskEditor']['open'], 'Shadows must replace Scene Tools'
    def actor():return next(a for a in c.state()['actors'] if a['id']==1)
    try:
        c.jump(14);open_shadows();feet=(actor()['x'],actor()['y'])
        value(0);assert room()['shadowOffsetX']==-2 and room()['shadowOffsetY']==6
        position();assert 'shadowOffsetX' not in room() and 'shadowOffsetY' not in room()
        assert room()['shadowWidth']==120 and room()['contrast']==4
        position();assert (room()['shadowOffsetX'],room()['shadowOffsetY'])==(-3,-5)
        scope(True);value(0);value(1)
        assert (data()['global']['shadowOffsetX'],data()['global']['shadowOffsetY'])==(-2,-4)
        assert (room()['shadowOffsetX'],room()['shadowOffsetY'])==(-3,-5)
        assert room(15)=={'shadowOffsetX':9,'brightness':8}
        c.screenshot('global-shadow-default')
        scope(False);value(0);value(0);value(0)
        assert room()['shadowOffsetX']==0, 'Explicit zero must override a nonzero global default'
        c.screenshot('scene-shadow-override')
        position();assert 'shadowOffsetX' not in room() and room()['shadowWidth']==120
        value(1);assert room()['shadowOffsetY']==-3, 'Nudges must start from the inherited value'
        # Position reset leaves width, color, opacity and unrelated look values.
        value(4);assert room()['shadowOpacity']==23
        position();assert room()['shadowOpacity']==23 and room()['shadowWidth']==120
        all_global();assert room()=={'contrast':4}
        # Panel remains usable after changing rooms; each gets its own overrides.
        assert (actor()['x'],actor()['y'])==feet, 'Shadow controls must not move Guybrush'
        c.jump(15);value(0);assert room(15)['shadowOffsetX']==10 and room()=={'contrast':4}
        position();assert room(15)=={'brightness':8}
        value(1);assert room(15)['shadowOffsetY']==-3
        c.jump(14);feet=(actor()['x'],actor()['y']);value(0);assert room()['shadowOffsetX']==-1
        assert (actor()['x'],actor()['y'])==feet, 'Shadow controls must not move Guybrush'
        for w,h in ((1280,827),(1720,720)):
            c.send(f'resize {w} {h}')
            scope(True);before=data()['global']['shadowOffsetX'];value(0)
            assert data()['global']['shadowOffsetX']==before+1
            scope(False);before=room()['shadowOffsetX'];value(0)
            assert room()['shadowOffsetX']==before+1
            position();assert 'shadowOffsetX' not in room()
            position();assert room()['shadowOffsetX']==data()['global']['shadowOffsetX']
            c.screenshot(f'shadow-scopes-{w}x{h}')
        key(109);assert c.state()['maskEditor']['open'];c.mask_button(45)
        value(0);saved=data();c.close()
        c=Check(out/'restart',color_grades_path=grades,config_overrides=overrides)
        c.jump(14);open_shadows();value(0)
        assert room()['shadowOffsetX']==saved['rooms']['14']['shadowOffsetX']+1
        assert room(15)==saved['rooms']['15']
        # A failed save must preserve the external file and expose the error.
        external=grades.read_text()+'\n';grades.write_text(external)
        value(0);assert grades.read_text()==external
        c.screenshot('shadow-save-conflict')
        print('PASS: M Shadows entry, explicit global/scene scopes, partial inheritance, pin/reset position, full shadow reset, unrelated settings, room changes, input isolation, aspect ratios, restart and external-change protection',flush=True)
    finally:c.close()

if __name__=='__main__':main()
