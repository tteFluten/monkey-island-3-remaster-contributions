#!/usr/bin/env python3
"""Native room-29 geometry, walking, interactions and fallback checks; isolated saves."""
import argparse
import json
import shutil
import time
from pathlib import Path
from check_aspect import Check, ROOT

def artwork(output, wide):
    hd = output / 'hd'
    hd.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / '.playtest/hd').iterdir():
        target = hd / source.name
        if source.name in ('backgrounds', 'widescreen'):
            target.mkdir(exist_ok=True)
            for child in source.iterdir():
                if child.name.startswith('bg_0029.png'): continue
                dest = target / child.name
                if not dest.exists(): dest.symlink_to(child)
        elif not target.exists(): target.symlink_to(source)
    # The original art is reference-only. Export a local 4x fallback, leaving
    # the selected master and all installed runtime artwork untouched.
    if not wide:
        from PIL import Image
        with Image.open(ROOT / 'extracted/backgrounds/0029_voodoo-e.png') as source:
            source.convert('RGBA').resize((2560, 1920), Image.Resampling.NEAREST).save(hd / 'backgrounds/bg_0029.png')
        (hd / 'backgrounds/bg_0029.png.stamp').write_text('original-reference')
    else:
        for name in ('backgrounds/bg_0029.png', 'backgrounds/bg_0029.png.stamp', 'widescreen/bg_0029.png'):
            shutil.copyfile(ROOT / 'assets/runtime' / name, hd / name)
    return hd




# Independent correspondences measured in the 2048x1152 painting.
LANDMARKS = [('Murray', 1080, 348, 340, 130),
             ('hut', 1270, 372, 410, 140),
             ('cow-skull', 746, 159, 202, 60),
             ('map-exit', 300, 1118, 17, 449)]
WALK = [('path-bend', 1430, 777, 475, 308),
        ('bridge-far', 805, 846, 226, 334),
        ('bridge-middle', 635, 907, 150, 360),
        ('bridge-near', 514, 1052, 100, 422),
        ('stairs', 1210, 674, 385, 267)]

def point(check,x,y):
    w=check.window()
    h=max(w['height'],w['width']*9/16)
    return round((w['width']-h*16/9)/2+x*h/1152),round((w['height']-h)/2+y*h/1152)

def move(check,x,y):
    p=point(check,x,y)
    check.send(f'move {p[0]} {p[1]}')
    return check.state()

def ego(check):
    return next(a for a in check.state()['actors'] if a['id']==1)

def goodbye(check):
    check.wait(lambda:check.state()['ready'] and not check.state()['voodooExteriorInput'],
               'Murray dialogue choices',120)
    check.screenshot('murray-responses')
    # The fourth original response is the farewell. Dialogue uses ordinary
    # viewport coordinates, independently of the room's landmark registration.
    check.send('move 460 626')
    check.click_game(200,417)
    check.wait(lambda:check.state()['ready'] and check.state()['voodooCanWalk'],
               'farewell and restored walking',45)

def compatibility(out, grades):
    modes=[]
    for gpu in (True,False):
        name='water-off-'+('gpu' if gpu else 'cpu')
        c=Check(out/name,hd_path=artwork(out/name,True),color_grades_path=grades,
                config_overrides={'comi':{'hd_gpu_effects':str(gpu).lower(),'hd_water_shader':'false'}})
        try:
            c.jump(29);c.wait(lambda:c.state()['voodooExteriorInput'],'registered exterior without water')
            assert move(c,1080,348)['hoverObject']==705
            c.send('key 105');c.wait(lambda:c.state()['inventoryOpen'],'inventory opened')
            c.wait(lambda:not c.state()['voodooExteriorInput'],'ordinary inventory input')
            c.send('key 105');c.wait(lambda:not c.state()['inventoryOpen'],'inventory closed')
            c.wait(lambda:c.state()['voodooExteriorInput'],'restored exterior input')
            assert move(c,1080,348)['hoverObject']==705
            c.send('move 2 2');c.screenshot(name)
            modes.append(name)
        finally:c.close()
    return modes

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.context/voodoo-background/check')
    args=parser.parse_args(); out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    grades=out/'grades.json';shutil.copyfile(ROOT/'data/color-grades.json',grades)
    results={'hotspots':{},'walking':{},'sizes':[]}
    c=Check(out/'fallback',hd_path=artwork(out/'fallback',False),color_grades_path=grades)
    try:
        c.jump(29); assert not c.state()['voodooExterior']
        for name,_,_,x,y in LANDMARKS:
            c.send(f'move {round(160+x*1.5)} {round(y*1.5)}')
            results['hotspots'][name]=c.state()['hoverObject']
            assert results['hotspots'][name],(name,c.state())
    finally:c.close()
    c=Check(out/'wide',hd_path=artwork(out/'wide',True),color_grades_path=grades)
    try:
        c.jump(29)
        c.wait(lambda:c.state()['voodooExteriorInput'],'registered exterior')
        for w,h in ((1280,720),(1280,800),(1720,720)):
            c.send(f'resize {w} {h}')
            # The far-left exit is cropped out on ultrawide displays.
            for name,x,y,sx,sy in LANDMARKS:
                p=point(c,x,y)
                if not(0<=p[0]<w and 0<=p[1]<h):continue
                state=move(c,x,y)
                assert abs(state['mouseRoomX']-sx)<=2 and abs(state['mouseRoomY']-sy)<=2,(name,state)
                assert state['hoverObject']==results['hotspots'][name],(name,state)
            c.screenshot(f'exterior-{w}x{h}');results['sizes'].append([w,h])
        c.send('resize 1280 720')
        for name,x,y,sx,sy in WALK:
            px,py=point(c,x,y)
            arrived=lambda: abs(ego(c)['x']-sx)<=5 and abs(ego(c)['y']-sy)<=5
            for attempt in range(3):
                c.send(f'move {px} {py}')
                c.send(f'click {px} {py}')
                c.wait(lambda: arrived() or not c.state()['ready'] or not c.state()['voodooExteriorInput'],name,45)
                if arrived():break
                # Murray's first-visit greeting interrupts the first walk.
                # Let the original script finish, then repeat the request.
                goodbye(c)
            assert arrived(),(name,c.state())
            time.sleep(.5);c.screenshot(name);results['walking'][name]=ego(c)
            print('PASS walking '+name,flush=True)
        c.send('key 111');c.room(92);assert not c.state()['voodooExteriorInput']
        c.send('key 27');c.room(29);c.wait(lambda:c.state()['voodooExteriorInput'],'input after menu')
        c.send('key 117');c.wait(lambda:not c.state()['voodooExteriorInput'],'Look input')
        c.send('key 27');c.wait(lambda:c.state()['voodooExteriorInput'],'input after Look')
        # Hold over Murray, then select the original mouth region of the coin.
        px,py=point(c,1080,348);c.send(f'move {px} {py}');c.send(f'down {px} {py}')
        time.sleep(1);c.screenshot('murray-coin')
        px,py=point(c,1187,265);c.send(f'move {px} {py}');c.send(f'up {px} {py}')
        time.sleep(3);c.screenshot('murray-talk')
        goodbye(c);results['murrayConversation']=True
        # Save the completed greeting in the isolated copy, then test each
        # exit from that same story state without repeating the introduction.
        c.save_load(1,1,29)
        for name,x,y,destination in [('hut',1270,372,30),('map',300,1118,13)]:
            c.save_load(2,1,29);c.wait(lambda:c.state()['voodooExteriorInput'],'registered exterior')
            px,py=point(c,x,y);c.send(f'move {px} {py}');c.send(f'click {px} {py}')
            c.wait(lambda:c.state()['room']==destination,name+' exit',60)
            assert not c.state()['voodooExteriorInput']
            results[name+'Exit']=destination;print('PASS exit '+name,flush=True)
        results['gameplayPassed']=True
    finally:
        c.close();(out/'result.json').write_text(json.dumps(results,indent=2)+'\n')
    results['renderModes']=compatibility(out,grades)
    results['passed']=True
    (out/'result.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
