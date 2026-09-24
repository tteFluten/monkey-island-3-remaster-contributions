#!/usr/bin/env python3
"""Finish tiny cannon particles from padded Wonder + Topaz matting masters.

Run paid processing with topaz_character_cutouts.py --output <effects> pilot.
The source alpha is input to Wonder only; it is never restored to its output.
"""
import argparse
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
from quiver_cannon import atomic, locked
from topaz_batch import SETTINGS, job_key
from topaz_cannon_removebg import SETTINGS as MATTING, validate
from topaz_character_cutouts import ROOT, digest


def prepare(output, batch):
    records = []
    prepared = output / 'prepared'
    for n in (9, 12):
        source = f'costumes/LFLF_0009_AKOS_0026_frame_{n}.png'
        with Image.open(batch / 'cleaned' / source) as im:
            rgba = im.convert('RGBA')
            sprite = rgba.resize((rgba.width*16, rgba.height*16), Image.Resampling.NEAREST)
            padded = Image.new('RGBA', (sprite.width+64, sprite.height+64))
            padded.paste(sprite, (32,32))
            target = prepared / 'cleaned' / source
            target.parent.mkdir(parents=True, exist_ok=True); padded.save(target)
            records.append(dict(source=source, original_size=list(padded.size), size=[v*4 for v in padded.size],
                raw=str((output/'raw'/source).resolve()), cleaned_sha256=digest(target), cached=None, raw_sha256=None,
                effect_crop=[128,128,128+sprite.width*4,128+sprite.height*4], runtime_size=[rgba.width*4,rgba.height*4]))
    value = dict(scale=4, source_batch=str(prepared.resolve()), settings=MATTING, upscale_settings=SETTINGS, records=records,
        preprocessing='16x nearest input with 32px padding; Wonder4x High; matting before crop and reduction')
    path = output/'manifest.json'
    if path.exists() and json.loads(path.read_text()) != value: raise ValueError('Effect inputs changed')
    atomic(path, value)


def finish(output, cannon, batch):
    effects = json.loads((output/'manifest.json').read_text())
    jobs = json.loads((output/'jobs.json').read_text())
    manifest = json.loads((cannon/'manifest.json').read_text())
    cannon_jobs = json.loads((cannon/'jobs.json').read_text())
    originals = {r['source']:r for r in json.loads((batch/'manifest.json').read_text())['records']}
    for r in effects['records']:
        source = r['source']; job = jobs[source]
        if job['stage'] != 'matting' or 'validation' not in job: raise ValueError('Effect is unfinished')
        provider = output/'provider'/source
        if digest(provider) != job['validation']['sha256']: raise ValueError('Effect master changed')
        with Image.open(provider) as image, Image.open(r['raw']) as raw:
            rgba = image.convert('RGBA'); rgb = raw.convert('RGB')
            if not np.array_equal(np.array(rgba)[:,:,:3], np.array(rgb)): raise ValueError('Provider changed Wonder RGB')
            # Apply the PROVIDER alpha to the reference only, so both resize
            # operations use identical premultiplication. No source mask is read.
            reference = rgb.convert('RGBA'); reference.putalpha(rgba.getchannel('A'))
            size = tuple(r['runtime_size'])
            result = rgba.crop(r['effect_crop']).resize(size, Image.Resampling.LANCZOS)
            reference = reference.crop(r['effect_crop']).resize(size, Image.Resampling.LANCZOS).convert('RGB')
            target = cannon/'4x'/source
            raw_target = output/'runtime-raw'/(job_key(originals[source],4)+'.png')
            raw_target.parent.mkdir(parents=True, exist_ok=True); reference.save(raw_target)
            result.save(target)
        report = validate(target, raw_target, batch/'cleaned'/source)
        if not report['passed']: raise ValueError('Runtime effect failed shape/color validation')
        report['cleanup'] = dict(type='padded-Wonder-Topaz-matting-reduced', provider_sha256=digest(provider),
            provider_rgb_unchanged=True, crop=r['effect_crop'], runtime_size=r['runtime_size'],
            interpolation='premultiplied Lanczos', original_pixels_restored=False, original_mask_applied=False)
        old = cannon_jobs.get(source,{})
        cannon_jobs[source] = dict(state='accepted', reviewed_at=time.time(), validation=report,
            effect_history=job['history'], previous_job=old)
        dest_record = next(item for item in manifest['records'] if item['source']==source)
        dest_record.setdefault('previous_raw',dest_record['raw'])
        dest_record.update(raw=str(raw_target.resolve()),raw_sha256=digest(raw_target))
    atomic(cannon/'manifest.json',manifest); atomic(cannon/'jobs.json',cannon_jobs)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('prepare','finish-reviewed'))
    p.add_argument('--output',type=Path,default=ROOT/'output/topaz-cannon-effects')
    p.add_argument('--cannon',type=Path,default=ROOT/'output/topaz-cannon-objectmatting')
    p.add_argument('--batch',type=Path,default=ROOT/'output/topaz-batch')
    a=p.parse_args()
    with locked(a.cannon):
        if a.command=='prepare': prepare(a.output,a.batch)
        else: finish(a.output,a.cannon,a.batch)
