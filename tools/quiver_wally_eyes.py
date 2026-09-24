#!/usr/bin/env python3
"""Apply reviewed dot pupils to Wally's forward-facing detached heads.

Profile heads hide the visible eye behind the patch. Closed-eye lines, crying
full-body poses, the patch itself and mouths are deliberately not converted.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import quiver_cannon as q
import quiver_walk as w
from quiver_eye_review import clusters


def source_eye(image):
    a = np.array(image.convert('RGBA'))
    if image.size != (59,78): return None
    dark = (a[:,:,3] > 192) & (a[:,:,:3].max(2) < 65)
    candidates = []
    for c in clusters(dark,1):
        x,y = c['center']; x0,y0,x1,y1 = c['box']
        if 1 <= c['area'] <= 25 and 59*.45 < x < 59*.8 and 78*.45 < y < 78*.7:
            # Keep a closed eyelid as an eyelid, including its expression.
            if x1-x0 <= 2.5*max(1,y1-y0) and x1-x0 <= 8 and y1-y0 <= 8:
                candidates.append(c)
    return min(candidates,key=lambda c:abs(c['center'][1]-46)) if candidates else None


def prepare(output):
    manifest=json.loads((output/'manifest.json').read_text())
    file=output/'repairs.json';repairs=json.loads(file.read_text()) if file.exists() else {}
    changed=[];reports=[]
    for r in manifest['records']:
        if r['sprite_role']!='standing_head':continue
        eye=source_eye(Image.open(output/'cleaned'/r['source']))
        if not eye:continue
        key=r['artwork_sha256'];rawfile=output/'raw'/(key+'.json')
        if not rawfile.exists():continue
        raw=json.loads(rawfile.read_text())['data'][0]['svg'];root=ET.fromstring(raw)
        for i,n in enumerate(root.iter()):n.set('id',str(i))
        with tempfile.TemporaryDirectory(prefix='wally-eyes-') as tmp:
            source=Path(tmp)/'source.svg';source.write_text(w.registered_svg(ET.tostring(root,encoding='unicode'),r))
            shapes=json.loads(subprocess.check_output([str(q.ROOT/'.context/quiver-native-render'),'--shapes',str(source)]))
        ex,ey=eye['center'];candidates=[]
        for shape in shapes:
            if shape['fill_type']!=1:continue
            rgb=[(shape['fill_color']>>(8*i))&255 for i in range(3)]
            x0,y0,x1,y1=[v/6 for v in shape['bounds']];cx,cy=(x0+x1)/2,(y0+y1)/2
            if max(rgb)<100 and 0<x1-x0<9 and 0<y1-y0<9 and abs(cx-ex)<3 and abs(cy-ey)<3:
                candidates.append(((cx-ex)**2+(cy-ey)**2,shape['id']))
        if not candidates:
            reports.append(dict(cel=r['cel'],status='manual_review_needed',source_eye=eye));continue
        _,index=min(candidates)
        entry=repairs.setdefault(key,dict(raw_sha256=q.sha(raw.encode()),reason=''))
        if entry['raw_sha256']!=q.sha(raw.encode()):raise ValueError('Review changed response before applying eyes')
        entry['remove_elements']=sorted(set(entry.get('remove_elements',[]))|{index})
        # These detached heads have no prior source-coordinate overlays.
        if entry.get('overlays_original') and entry.get('eye_style')!='solid-dark-dot':
            raise ValueError('Review existing eye overlays before replacing')
        entry['overlays_original']=[dict(cx=str(ex),cy=str(ey),r='.65',fill='#30231b')]
        entry['eye_style']='solid-dark-dot';entry['eye_centers_original']=[[ex,ey]]
        entry['reason']='Preserve Wally source eye center with solid dark dot pupil; retain patch, closed-eye frames and tear shapes. '+entry.get('reason','')
        changed.append(key);reports.append(dict(cel=r['cel'],status='prepared',source_eye=eye,removed_element=index))
    q.atomic(file,repairs);q.atomic(output/'eye-style-review.json',reports)
    print(f'Prepared dot pupils for {len(changed)} Wally heads')
    return changed


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=q.OUTPUT/'wally-vectorized')
    args=parser.parse_args()
    with q.locked(args.output):prepare(args.output)
