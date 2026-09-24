#!/usr/bin/env python3
"""Extract only the four difficulty-selector knife cels; no background changes/API calls."""
import json
from pathlib import Path
import shutil

from quiver_cannon import atomic
from quiver_extract import extract
from topaz_batch import SETTINGS
from topaz_cannon_removebg import SETTINGS as MATTING
from topaz_character_cutouts import ROOT, digest


def prepare(output, batch, game):
    extraction = output/'extracted'
    meta = extract(game,extraction,[439])
    if len(meta['records']) != 4 or any(r['room'] != 87 for r in meta['records']):
        raise ValueError('Unexpected knife resource')
    path = batch/'manifest.json'; manifest=json.loads(path.read_text())
    by_source={r['source']:r for r in manifest['records']}
    selected=[]
    for item in meta['records']:
        source='costumes/'+item['source'];clean=extraction/'cleaned'/item['source']
        indexed=extraction/'indexed'/item['source'];target=batch/'cleaned'/source
        if source not in by_source:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(clean,target)
            manifest['records'].append(dict(source=source,source_file=str(indexed.resolve()),source_sha256=digest(indexed),
                size=item['size'],cleaned_sha256=digest(clean),canonical=source,origin='local-game-extraction',
                game_resource_sha256=meta['resources']['439']['sha256']))
        elif by_source[source]['cleaned_sha256'] != digest(clean): raise ValueError('Knife extraction changed')
        selected.append(dict(source=source,original_size=item['size'],size=[v*4 for v in item['size']],
            raw=str((output/'raw'/source).resolve()),cleaned_sha256=digest(clean),cached=None,raw_sha256=None))
    atomic(path,manifest)
    value=dict(kind='difficulty-knife',scale=4,source_batch=str(batch.resolve()),settings=MATTING,
        upscale_settings=SETTINGS,records=selected,original_pixels_restored=False,original_mask_applied=False)
    target=output/'manifest.json'
    if target.exists() and json.loads(target.read_text())!=value: raise ValueError('Knife inputs changed')
    atomic(target,value)
    print('Prepared only knife costume439, four animation frames; no API requests or background writes.')


if __name__=='__main__':
    prepare(ROOT/'output/topaz-difficulty-knife',ROOT/'output/topaz-batch',ROOT/'.playtest/game')
