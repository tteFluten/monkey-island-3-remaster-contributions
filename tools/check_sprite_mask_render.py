#!/usr/bin/env python3
"""Verify saved masks affect real PNG compositing, using disposable artwork."""
import json,re
from pathlib import Path
from PIL import Image
from check_aspect import Check,ROOT


def main():
    out=ROOT/'.context/sprite-mask-render';out.mkdir(parents=True,exist_ok=True)
    hd=out/'hd';hd.mkdir(exist_ok=True)
    for source in (ROOT/'.playtest/hd').iterdir():
        if source.name!='topaz-cannon' and not (hd/source.name).exists():(hd/source.name).symlink_to(source.resolve())
    costumes=hd/'topaz-cannon/costumes';costumes.mkdir(parents=True,exist_ok=True)
    for source in (ROOT/'.playtest/hd/topaz-cannon/costumes').iterdir():
        if not (costumes/source.name).exists():(costumes/source.name).symlink_to(source.resolve())
    # Exact source dimensions enter the same strict PNG loader as production art.
    # An opaque magenta fixture makes removed pixels unambiguous against the painting.
    for source in (ROOT/'extracted/costumes').glob('LFLF_0001_AKOS_0008_frame_*.png'):
        w,h=Image.open(source).size
        target=costumes/source.name.replace('_frame_','_aframe_')
        if target.is_symlink():target.unlink()
        Image.new('RGBA',(w*4,h*4),(255,0,255,255)).save(target)
    masks=out/'masks.json';masks.write_text('{"schemaVersion":1,"scenes":{}}')
    c=Check(out/'baseline',hd_path=hd,config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    header=(ROOT/'tools/engine/hd_voodoo_exterior.h').read_text()
    axes={axis:[tuple(map(float,p)) for p in re.findall(r'\{(\d+),(\d+)\}',re.search(r'k'+axis+r'\[\] = (.*?);',header,re.S)[1])] for axis in ('X','Y')}
    def paint(v,axis):
        ps=axes[axis];i=next((i for i in range(1,len(ps)) if v<=ps[i][0]),len(ps)-1);a,b=ps[i-1:i+1]
        return a[1]+(b[1]-a[1])*(v-a[0])/(b[0]-a[0])
    def state():return c.state()['maskEditor']
    def select():
        v=next(v for v in state()['animationVisuals'] if v['actor']==33);win=c.window();h=max(win['height'],win['width']*9/16)
        x=(win['width']-h*854/480)/2+paint(v['left']+v['width']/2,'X')/2048*h*854/480
        y=(win['height']-h)/2+paint(v['top']+v['height']/2,'Y')/1152*h
        c.send(f'click {round(x)} {round(y)}')
        assert state()['animationSelected']=='33:8'
    def magenta(path):
        im=Image.open(path).convert('RGB')
        # Covers all bounds in the animation; excludes neighboring flames and the menu.
        bounds=(paint(255,'X')/2048*im.width,paint(220,'Y')/1152*im.height,paint(285,'X')/2048*im.width,paint(260,'Y')/1152*im.height)
        return sum(r>140 and b>140 and g<60 for r,g,b in im.crop(tuple(map(round,bounds))).getdata())
    try:
        c.jump(29);c.screenshot('original');baseline=magenta(c.output/'original.png');assert baseline>20,baseline
        c.send('key 109');c.mask_button(28);select();c.send('key 1073741903');c.mask_button(4)
    finally:c.close()
    data=json.loads(masks.read_text());scene=next(iter(data['scenes'].values()))
    scene['animations']={}
    scene['animationMasks']={'topaz:33:8':{'zones':[],'holes':[[[0,0],[1000,0],[1000,1000],[0,1000]]],'edge':0,'feather':1}}
    masks.write_text(json.dumps(data))
    c=Check(out/'masked',hd_path=hd,config_overrides={'comi':{'hd_scene_masks_path':str(masks)}})
    try:
        c.jump(29);c.screenshot('masked');removed=magenta(c.output/'masked.png');assert removed==0,(baseline,removed)
        c.send('key 109');c.mask_button(28);select();c.mask_button(46);c.mask_button(52);c.send('key 109')
        c.screenshot('reset');restored=magenta(c.output/'reset.png');assert restored>20,restored
        print(f'PASS: exact PNG replacement visible ({baseline} pixels), saved polygon removes it ({removed}), Reset invalidates coverage and restores it ({restored}); source PNGs untouched',flush=True)
    finally:c.close()

if __name__=='__main__':main()
