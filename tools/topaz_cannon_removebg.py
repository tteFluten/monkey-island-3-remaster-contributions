#!/usr/bin/env python3
"""Remove cannon backgrounds with Topaz; never restore source pixels or masks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import tempfile
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import numpy as np
from PIL import Image, ImageFilter
from topaz_batch import API, job_key
from quiver_cannon import atomic, locked

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/topaz-cannon-objectmatting'
# Object Matting is the verified working extraction model for these cannon cels.
SETTINGS = dict(model='Object', mode='segmentation', output_format='png')


def stopped(local):
    """Do not replace textures while the workspace game is using them."""
    process = local / 'process.json'
    if not process.exists(): return
    pid = json.loads(process.read_text())['pid']
    if not isinstance(pid, int) or pid <= 0: raise ValueError('Invalid game process record')
    try: os.kill(pid, 0)
    except ProcessLookupError: return
    raise RuntimeError('Stop the game before installing reviewed textures')


def prepare(output, batch):
    scope = json.loads((batch / 'cannon-sprites-scope.json').read_text())['sources']
    records = {r['source']: r for r in json.loads((batch / 'manifest.json').read_text())['records']}
    selected = []
    for source in scope:
        r = records[source]
        raw = batch / 'raw' / (job_key(r, 4) + '.png')
        size = [v * 4 for v in r['size']]
        with Image.open(raw) as im:
            if list(im.size) != size: raise ValueError('Cached Wonder dimensions changed')
        selected.append(dict(source=source, size=size, raw=str(raw.resolve()), raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest()))
    value = dict(settings=SETTINGS, scale=4, records=selected, source_batch=str(batch.resolve()))
    path = output / 'manifest.json'
    if path.exists() and json.loads(path.read_text()) != value: raise ValueError('Inputs changed; choose a new output directory')
    atomic(path, value)


def validate(result, raw, source):
    with Image.open(result) as im:
        if im.mode != 'RGBA': raise ValueError(f'Topaz did not return RGBA: {im.mode}')
        a = np.array(im); size = im.size
    with Image.open(raw) as im:
        if im.size != size: raise ValueError('Topaz cropped/resized the sprite; cannot install')
        rgb = np.array(im.convert('RGB'))
    # Original mask is used only to detect missing parts/background leakage.
    # It is NEVER applied to the output. Provider file is copied byte-for-byte.
    with Image.open(source) as im:
        original = im.convert('RGBA').resize(size, Image.Resampling.NEAREST).getchannel('A')
    reference = np.array(original) >= 192
    mask = a[:, :, 3] >= 192
    union = int((reference | mask).sum())
    iou = float((reference & mask).sum() / max(1, union))
    opaque = a[:, :, 3] >= 250
    delta = np.abs(a[:, :, :3].astype(float) - rgb.astype(float))
    rgb_delta = float(delta[opaque].max()) if opaque.any() else 255
    allowed = np.array(original.filter(ImageFilter.MaxFilter(17))) > 0
    outside = float((mask & ~allowed).sum() / max(1, mask.sum()))
    return dict(passed=bool(iou >= .85 and outside <= .01 and (a[:, :, 3] == 0).any() and opaque.any() and rgb_delta <= 1),
                size=list(size), silhouette_iou=iou, outside_fraction=outside,
                opaque_rgb_max_change=rgb_delta,
                original_pixels_restored=False, original_mask_applied=False,
                sha256=hashlib.sha256(result.read_bytes()).hexdigest())


def remove_matte_residue(provider, destination):
    """Only adjust alpha of neutral gray matte; never read original sprite data."""
    with Image.open(provider) as im:
        if im.mode != 'RGBA': raise ValueError('Expected a Topaz RGBA cutout')
        rgba = np.array(im)
    rgb = rgba[:, :, :3].astype(int)
    matte = (rgb.max(2) - rgb.min(2) <= 5) & (rgb.min(2) >= 90) & (rgb.max(2) <= 175)
    removed = int((matte & (rgba[:, :, 3] > 0)).sum())
    rgba[matte, 3] = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba).save(destination)
    return dict(type='neutral-gray-residue-alpha-only', pixels=removed,
                max_channel_spread=5, channel_range=[90, 175], rgb_unchanged=True,
                provider_sha256=hashlib.sha256(provider.read_bytes()).hexdigest())


def run(output, api, pilot=False, sources=()):
    manifest = json.loads((output / 'manifest.json').read_text())
    settings = manifest['settings']
    records = manifest['records'][:1] if pilot else manifest['records']
    if sources:
        records = [r for r in records if r['source'] in sources]
        if len(records) != len(set(sources)): raise ValueError('Unknown or repeated selected source')
    jobs_file = output / 'jobs.json'
    jobs = json.loads(jobs_file.read_text()) if jobs_file.exists() else {}
    if not pilot and jobs.get(manifest['records'][0]['source'], {}).get('state') != 'accepted':
        raise ValueError('Visually review the pilot before the rest of the batch')
    for r in records:
        if jobs.get(r['source'], {}).get('state') in ('submitting', 'unknown', 'failed', 'rejected'):
            raise ValueError('Stopped job requires inspection; no automatic paid retries')
    journal_lock = threading.Lock()
    def save():
        with journal_lock: atomic(jobs_file, json.loads(json.dumps(jobs)))
    def process(r):
        source = r['source']; raw = Path(r['raw']); job = jobs.get(source, {})
        if job.get('state') in ('accepted', 'validated'): return
        if hashlib.sha256(raw.read_bytes()).hexdigest() != r['raw_sha256']: raise ValueError('Wonder master changed')
        if not job:
            estimate = api.call('/image/v1/estimate', dict(category='Matting', **settings, input_width=r['size'][0], input_height=r['size'][1]))
            if estimate['credits'] > 1: raise ValueError('Unexpected price: expected one credit per cannon frame')
            if api.balance() < estimate['credits']: raise ValueError('Insufficient credits')
            job = dict(state='submitting', settings=settings, input_sha256=r['raw_sha256'], estimate=estimate, created_at=time.time())
            jobs[source] = job; save()
            print(f'{settings["model"]}: {source}', flush=True)
            try:
                response = api.call('/image/v1/matting/async', settings, image=raw)
                job.update(state='submitted', response=response, process_id=response['process_id']); save()
            except Exception as error:
                job.update(state='unknown', error=str(error)[:500]); save(); raise
        deadline = time.monotonic() + 600
        while True:
            status = api.call('/image/v1/status/' + job['process_id'])
            if status['status'] == 'Completed': break
            if status['status'] in ('Failed', 'Cancelled'):
                job.update(state='failed', error=status['status']); save(); raise RuntimeError(status['status'])
            if time.monotonic() > deadline: raise TimeoutError('Resume polling existing job; do not resubmit')
            time.sleep(3)
        destination = output / '4x' / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        provider = output / 'provider' / source
        provider.parent.mkdir(parents=True, exist_ok=True)
        api.download(job['process_id'], provider)
        cleanup = remove_matte_residue(provider, destination)
        try:
            report = validate(destination, raw, Path(manifest['source_batch']) / 'cleaned' / source)
            report['cleanup'] = cleanup
        except Exception as error:
            job.update(state='rejected', error=str(error)); save(); raise
        job.update(state='validated' if report['passed'] else 'rejected', validation=report)
        save(); print(json.dumps(dict(source=source, **report)), flush=True)
        if not report['passed']: raise ValueError('Cutout rejected; paid batch paused for inspection')


    failure = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {}; index = 0
        while pending or (index < len(records) and failure is None):
            while len(pending) < 2 and index < len(records) and failure is None:
                future = pool.submit(process, records[index]); pending[future] = records[index]['source']; index += 1
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                try: future.result()
                except Exception as error:
                    if failure is None: failure = error
        if failure: raise failure


def install(output, local, completed_only=False):
    stopped(local)
    manifest = json.loads((output / 'manifest.json').read_text())
    records = manifest['records']
    pattern = r'costumes/LFLF_0009_AKOS_0026_frame_(\d+)\.png'
    if len(records) != 14 or any(not re.fullmatch(pattern, r['source']) for r in records):
        raise ValueError('Install scope must contain the 14 cannon frames only')
    if {int(re.fullmatch(pattern, r['source']).group(1)) for r in records} != set(range(14)):
        raise ValueError('Cannon sequence is incomplete')
    jobs = json.loads((output / 'jobs.json').read_text())
    if completed_only:
        records = [r for r in records if jobs.get(r['source'], {}).get('state') == 'accepted']
        if not records: raise ValueError('No reviewed cutouts to install')
    batch = Path(manifest['source_batch'])
    for r in records:
        job = jobs.get(r['source'], {})
        path = output / '4x' / r['source']
        if job.get('state') != 'accepted': raise ValueError('All 14 cutouts require visual review')
        if hashlib.sha256(path.read_bytes()).hexdigest() != job['validation']['sha256']:
            raise ValueError('Reviewed cutout changed')
        with Image.open(path) as im:
            if im.mode != 'RGBA' or list(im.size) != r['size']: raise ValueError('Invalid cutout')
    receipt = []
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        pending = []
        for r in records:
            source = r['source']; provider = output / '4x' / source
            destinations = [('asset-tool', batch / '4x' / source)] + [
                (pack, local / 'hd' / pack / source.replace('_frame_', '_aframe_'))
                for pack in ('topaz-cannon', 'topaz-crisp')]
            for label, target in destinations:
                backup = output / 'previous' / label / source
                if target.exists() and not backup.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                staged = Path(temporary) / str(len(pending))
                shutil.copy2(provider, staged)
                pending.append((staged, target))
                receipt.append(dict(target=str(target.resolve()), provider=str(provider.resolve()), sha256=jobs[source]['validation']['sha256']))
        for staged, target in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
    policy_file = batch / 'protected-cutouts.json'
    policy = json.loads(policy_file.read_text()) if policy_file.exists() else {}
    for r in records:
        policy[f"4:{r['source']}"] = dict(file=str((output / '4x' / r['source']).resolve()),
            sha256=jobs[r['source']]['validation']['sha256'], upscale_job_key=Path(r['raw']).stem)
    atomic(policy_file, policy)
    atomic(output / 'installation.json', dict(installed_at=time.time(), scale=4, original_pixels_restored=False, original_mask_applied=False, files=receipt))
    print(f'Installed {len(records)} reviewed Topaz cutouts in both Topaz packs and the asset tool; previous copies backed up.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'pilot', 'run', 'install'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--batch', type=Path, default=ROOT / 'output/topaz-batch')
    parser.add_argument('--completed-only', action='store_true', help='Install only visually reviewed completed cels, preserving every other installed frame')
    parser.add_argument('--source', action='append', default=[], help='Process a selected source without retrying other rejected cels')
    parser.add_argument('--model', choices=('RemoveBG', 'Object'), default='Object')
    parser.add_argument('--local', type=Path, default=ROOT / '.playtest')
    args = parser.parse_args()
    if args.model == 'RemoveBG':
        SETTINGS.update(model='RemoveBG')
        SETTINGS.pop('output_format', None)
    with locked(args.output):
        if args.command == 'prepare': prepare(args.output, args.batch)
        elif args.command == 'install': install(args.output, args.local, args.completed_only)
        else: run(args.output, API(ROOT / '.context/secrets/topaz-api-key', 4), args.command == 'pilot', args.source)

if __name__ == '__main__': main()
