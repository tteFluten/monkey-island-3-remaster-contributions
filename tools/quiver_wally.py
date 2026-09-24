#!/usr/bin/env python3
"""Wally cannon-room Arrow 2 SVGs, sharing the reviewed walking pipeline."""
import json
from pathlib import Path
import shutil
import sys

from PIL import Image
import quiver_cannon as q
import quiver_walk as w

OUTPUT = q.OUTPUT / 'wally-vectorized'


def prepare(output=OUTPUT, sources=q.OUTPUT):
    original = json.loads((sources / 'manifest.json').read_text())
    all_records = [dict(r) for r in original['records'] if r['character'] == 'Wally']
    # Costume 28 cel 1 is only a whip, with no Wally artwork. Standalone props
    # are outside the requested character redraw; retain its original resource.
    excluded = [r for r in all_records if (r['costume'],r['cel']) == (28,1)]
    records = [r for r in all_records if r not in excluded]
    if {r['costume'] for r in records} != {25,28}:
        raise ValueError('Inspect changed Wally archive resource selection')
    if len(records) != 221:
        raise ValueError('Wally archive cel count changed; inspect before generation')
    for directory in ('cleaned','references'): (output / directory).mkdir(parents=True,exist_ok=True)
    for r in records:
        source = sources/'cleaned'/r['source']; shutil.copy2(source,output/'cleaned'/r['source'])
        width,height = r['size']; side = max(width,height)+16
        x,y = (side-width)//2,(side-height)//2
        r['reference_canvas'] = dict(side=side,x=x,y=y)
        # Small detached head cels have no ground shadow; alpha at the neck is
        # an edge marker, not a shadow to be restored behind the head.
        r['sprite_role'] = 'standing_head' if width <= 65 and height <= 110 else 'character_part'
        square = Image.new('RGBA',(side,side)); square.paste(Image.open(source).convert('RGBA'),(x,y))
        square.resize((side*4,side*4),Image.Resampling.NEAREST).save(output/'references'/r['source'])
    pilots = {(25,3),(25,5),(25,100),(28,0)}
    q.atomic(output/'manifest.json',dict(original,records=records,operation='vectorization',
        pilot_keys=[r['artwork_sha256'] for r in records if (r['costume'],r['cel']) in pilots],
        scope=dict(character='Wally',costumes=[25,28],mapping_count=221,
                   excluded_props=excluded,
                   provenance='Archive character metadata; cannon Wally artwork, including separate head/body parts. Prop-only whip retains original artwork.')))
    if not (output/'brush-style.json').exists():
        q.atomic(output/'brush-style.json',dict(width=1.0,style='subtle pressure brush',version=1))
    print(f'Prepared {len(records)} Wally cels from archive metadata')


def install_combined(wally=OUTPUT, walking=q.OUTPUT/'walking-vectorized', hd=q.ROOT/'.playtest/hd'):
    output=q.OUTPUT/'combined-character-pack'
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    with q.locked(output):
        db=q.journal(output)
        for pack in (walking,wally):
            manifest=json.loads((pack/'manifest.json').read_text()); source_db=q.journal(pack)
            for r in manifest['records']:
                key=r['artwork_sha256']; state,details=q.job(source_db,key)
                if state!='accepted': raise ValueError(f'Complete and review {pack.name} before combining')
                for relative,digest in details['validation']['output_hashes'].items():
                    src=pack/relative
                    if q.sha(src.read_bytes())!=digest: raise ValueError('Reviewed output hash changed')
                    dst=output/relative; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
                q.save_job(db,key,state,**details); records.append(r)
            source_db.close()
        db.close()
        q.atomic(output/'manifest.json',dict(records=records,scope=dict(characters=['Guybrush walking/idle','Wally cannon'],room=9)))
        q.install(output,hd)


if __name__=='__main__':
    command=sys.argv[1] if len(sys.argv)>1 else 'status'
    if command=='prepare':
        with q.locked(OUTPUT): prepare()
    elif command=='install': install_combined()
    else:
        if '--output' not in sys.argv: sys.argv += ['--output',str(OUTPUT)]
        w.main()
