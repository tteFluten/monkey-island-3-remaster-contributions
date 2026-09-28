#!/usr/bin/env python3
"""Check the real map -> swamp entrance against the painted bottom edge."""
import argparse
import json
import shutil
from pathlib import Path
from PIL import Image
from check_aspect import Check,ROOT
from check_plunder_map import screen_point
from check_voodoo_exterior import point,ego


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.context/voodoo-entrance-check')
    out=parser.parse_args().output.resolve()
    c=Check(out)
    def capture(name):
        before=set(out.glob('scummvm*.png'));c.send('screenshot')
        c.wait(lambda:bool(set(out.glob('scummvm*.png'))-before),'entry screenshot')
        source=next(iter(set(out.glob('scummvm*.png'))-before))
        shutil.copyfile(source,out/(name+'.png'))
    try:
        c.jump(13);px,py=screen_point(c,355,587)
        c.send(f'move {px} {py}');c.send(f'click {px} {py}')
        c.wait(lambda:c.state().get('room')==29 and c.state().get('voodooExterior'),'registered swamp entrance',30)
        samples=[]
        for i in range(4):
            samples.append(ego(c));capture(f'entering-{i}')
        c.wait(lambda:abs(ego(c)['x']-103)<=2 and abs(ego(c)['y']-420)<=2,'original entry destination',30)
        c.screenshot('arrived')
        # Previously the upper body popped into this interior patch on the
        # first frame. It must now rise into view through the bottom edge.
        im=Image.open(out/'entering-0.png').convert('RGB');w,h=im.size
        roi=im.crop((round(230*w/2048),round(700*h/1152),round(470*w/2048),round(1000*h/1152)))
        light=sum(min(p)>165 for p in roi.getdata())
        assert light<300,('actor still appears inside the painting',light,samples)
        assert samples[0]['x']<60,samples
        # Reverse traversal still reaches the original map exit script.
        c.wait(lambda:c.state().get('voodooCanWalk'),'walk input restored')
        px,py=point(c,300,1118);c.send(f'move {px} {py}');c.send(f'click {px} {py}')
        c.wait(lambda:c.state().get('room')==13,'map exit',40)
        (out/'result.json').write_text(json.dumps({'passed':True,'entry':samples,'interiorWhitePixels':light},indent=2))
        print('PASS: enters from bottom edge, reaches original destination, exits to map',flush=True)
    finally:c.close()

if __name__=='__main__':main()
