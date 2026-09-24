#!/usr/bin/env python3
"""Resumable Wonder/Topaz matting for Guybrush's walk and all cannon-room Wally cels.

Cached Wonder masters are reused. Original masks are geometry checks only;
the output keeps Topaz RGB and alpha. No legacy edge restoration is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

import numpy as np
from PIL import Image, ImageFilter
from quiver_cannon import atomic, locked
from topaz_batch import API, SETTINGS as WONDER, job_key
from topaz_cannon_removebg import SETTINGS as MATTING, validate, stopped

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/topaz-character-objectmatting'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def character_validation(result, raw, source):
    report = validate(result, raw, source)
    with Image.open(result) as im:
        alpha = im.getchannel('A'); size = im.size
    with Image.open(source) as im:
        reference = np.asarray(im.convert('RGBA').getchannel('A').resize(size, Image.Resampling.NEAREST)) >= 192
    covered = np.asarray(alpha.filter(ImageFilter.MaxFilter(17))) >= 128
    lost = float((reference & ~covered).sum() / max(1,reference.sum()))
    report.update(missing_interior_fraction=lost)
    # Thin props and existing cast shadows can shift the overall IoU even when
    # the enhanced subject is complete. Interior coverage catches truncation.
    report['passed'] = report['passed'] and lost <= .01 and report['silhouette_iou'] >= .90
    return report


def load_jobs(output):
    jobs = json.loads((output/'jobs.json').read_text())
    audit = output/'audits.json'
    if audit.exists():
        for source, value in json.loads(audit.read_text()).items():
            if source in jobs: jobs[source].update(value)
    return jobs


def recover_alpha(provider, raw):
    """Repair color-key matte errors without reading any original sprite data."""
    rgba=np.array(provider.convert('RGBA'))
    rgb=np.array(raw.convert('RGB')).astype(float)
    if not np.array_equal(rgba[:,:,:3],rgb): raise ValueError('Provider changed enhanced colors')
    spread=rgb.max(2)-rgb.min(2)
    signal=np.maximum.reduce([(spread-3)/12,(45-rgb.min(2))/25,(rgb.max(2)-175)/25])
    alpha=np.rint(np.clip(signal,0,1)*255).astype('uint8')
    matte=(spread<=8)&(rgb.min(2)>=45)&(rgb.max(2)<=175)
    alpha[matte]=0
    # Keep thin dark whip strokes, but exclude broad gray drop shadows. Local
    # contrast comes exclusively from the enhanced RGB; geometry checks below
    # independently reject any loss of gray foreground material.
    lum=rgb.mean(2).astype('uint8')
    contrast=np.array(Image.fromarray(lum).filter(ImageFilter.MaxFilter(17))).astype(float)-lum
    thin=np.rint(np.clip((contrast-15)/25,0,1)*255).astype('uint8')
    thin[rgb.max(2)>100]=0
    mask=thin>=128; visited=np.zeros(mask.shape,dtype=bool); strokes=np.zeros(mask.shape,dtype=bool)
    height,width=mask.shape
    for y,x in zip(*np.nonzero(mask)):
        if visited[y,x]: continue
        stack=[(int(y),int(x))];visited[y,x]=True;component=[]
        while stack:
            cy,cx=stack.pop();component.append((cy,cx))
            for dy,dx in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
                ny,nx=cy+dy,cx+dx
                if 0<=ny<height and 0<=nx<width and mask[ny,nx] and not visited[ny,nx]:
                    visited[ny,nx]=True;stack.append((ny,nx))
        ys,xs=zip(*component);h=max(ys)-min(ys)+1;w=max(xs)-min(xs)+1
        if h>height*.2 and h>w*2:
            for cy,cx in component:strokes[cy,cx]=True
    alpha[strokes]=np.maximum(alpha[strokes],thin[strokes])
    rgba[:,:,3]=np.maximum(rgba[:,:,3],alpha)
    rgba[matte & ~strokes,3]=0
    return Image.fromarray(rgba)


def audit(output, repair=False):
    """Audit coverage; optionally recover a truncated alpha from enhanced RGB only."""
    manifest = json.loads((output/'manifest.json').read_text())
    if repair and manifest.get('kind') == 'difficulty-knife':
        raise ValueError('Gray-matte character repairs are inappropriate for a gray knife blade')
    jobs = json.loads((output/'jobs.json').read_text())
    audits_file = output/'audits.json'
    audits = json.loads(audits_file.read_text()) if audits_file.exists() else {}
    for r in manifest['records']:
        source=r['source']; job=jobs.get(source,{})
        if job.get('state') not in ('validated','accepted','rejected') or 'validation' not in job: continue
        previous=audits.get(source,{})
        if previous.get('provider_validation_sha256') == job['validation']['sha256'] and (previous['validation']['passed'] or not repair): continue
        provider=output/'provider'/source;raw=Path(r['raw']); original=Path(manifest['source_batch'])/'cleaned'/source
        report=character_validation(provider,raw,original)
        destination=output/'4x'/source
        repaired=False
        if not report['passed'] and repair:
            candidate=output/'repaired'/source;candidate.parent.mkdir(parents=True,exist_ok=True)
            with Image.open(provider) as im, Image.open(raw) as rgb: recover_alpha(im,rgb).save(candidate)
            candidate_report=character_validation(candidate,raw,original)
            candidate_report['cleanup']=dict(type='enhanced-RGB-alpha-recovery',rgb_unchanged=True,
                original_pixels_restored=False,original_mask_applied=False,
                version=2,formula='enhanced-color alpha; neutral matte cleared except isolated tall high-contrast strokes')
            if candidate_report['passed']:
                shutil.copy2(candidate,destination);report=candidate_report;repaired=True
        if not repaired:
            shutil.copy2(provider,destination)
        audits[source]=dict(state='validated' if report['passed'] else 'rejected', validation=report,
            provider_validation_sha256=job['validation']['sha256'], repaired=repaired)
    atomic(audits_file,audits)
    print(f'Audited {len(audits)}: {sum(a["validation"]["passed"] for a in audits.values())} pass, '
          f'{sum(a.get("repaired",False) for a in audits.values())} alpha repairs.')


def prepare(output, batch):
    manifest_path = batch / 'manifest.json'
    original = json.loads(manifest_path.read_text())
    records = {r['source']: r for r in original['records']}
    extraction = batch / 'extracted-idle'
    meta = json.loads((extraction / 'extraction.json').read_text())
    unique = {r['cleaned_sha256']: r['canonical'] for r in records.values() if 'canonical' in r}
    for item in meta['records']:
        if item['costume'] != 25: continue
        source = 'costumes/' + item['source']
        if source in records: continue
        clean = extraction / 'cleaned' / item['source']
        indexed = extraction / 'indexed' / item['source']
        target = batch / 'cleaned' / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(clean, target)
        record = dict(source=source, source_file=str(indexed.resolve()), source_sha256=digest(indexed),
                      size=item['size'], cleaned_sha256=digest(clean), origin='local-game-extraction',
                      game_resource_sha256=meta['resources']['25']['sha256'])
        record['canonical'] = unique.setdefault(record['cleaned_sha256'], source)
        records[source] = record
        original['records'].append(record)
    atomic(manifest_path, original)
    walk = json.loads((batch / 'idle-walk-scope.json').read_text())['sequences']['2:2']
    sources = [f'costumes/LFLF_0001_AKOS_0002_frame_{cel}.png' for cel in walk]
    sources += [f'costumes/LFLF_0009_AKOS_0025_frame_{cel}.png' for cel in range(220)]
    result = []
    for source in sources:
        record = records[source]
        raw = output / 'raw' / source
        cached = None
        for scale in (4, 6):
            candidate = batch / 'raw' / (job_key(record, scale) + '.png')
            if candidate.exists():
                cached = dict(path=str(candidate.resolve()), sha256=digest(candidate), scale=scale)
                raw.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(candidate) as im:
                    if im.size != tuple(v * scale for v in record['size']): raise ValueError('Invalid cached dimensions')
                    im.convert('RGB').resize(tuple(v * 4 for v in record['size']), Image.Resampling.LANCZOS).save(raw)
                break
        result.append(dict(source=source, original_size=record['size'], size=[v*4 for v in record['size']],
                           raw=str(raw.resolve()), cleaned_sha256=record['cleaned_sha256'],
                           cached=cached, raw_sha256=digest(raw) if raw.exists() else None))
    value = dict(scale=4, source_batch=str(batch.resolve()), settings=MATTING, upscale_settings=WONDER,
                 original_pixels_restored=False, original_mask_applied=False, records=result)
    path = output / 'manifest.json'
    if path.exists() and json.loads(path.read_text()) != value: raise ValueError('Prepared inputs changed')
    atomic(path, value)
    print(f'Prepared {len(result)} frames; {sum(r["cached"] is not None for r in result)} cached upscales.')


def run(output, api, max_credits, sources=(), concurrency=2, require_pilots=True, stop_files=(), poll_timeout=1200):
    # One coordinator owns the journal and paired-stage budget for all slots.
    # Sixteen is a local trial ceiling, not a claim about the account's API limit.
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or not 1 <= concurrency <= 16:
        raise ValueError('Concurrency must be an integer from 1–16')
    manifest = json.loads((output / 'manifest.json').read_text())
    records = manifest['records']
    if sources:
        records = [r for r in records if r['source'] in sources]
        if len(records) != len(set(sources)): raise ValueError('Invalid selection')
    jobs_file = output / 'jobs.json'
    jobs = json.loads(jobs_file.read_text()) if jobs_file.exists() else {}
    pilot_tokens = ('AKOS_0439',) if manifest.get('kind') == 'difficulty-knife' else ('AKOS_0002', 'AKOS_0025')
    def approved(source, job):
        if job.get('state') == 'accepted': return True
        path = output/'reviews'/(source+'.json')
        return path.exists() and json.loads(path.read_text())['sha256'] == job.get('validation',{}).get('sha256')
    if require_pilots and not all(any(approved(s,j) and token in s for s,j in jobs.items()) for token in pilot_tokens):
        raise ValueError('Visually review a pilot for each selected character before the full run')
    def progress(state):
        atomic(jobs_file, jobs)
        atomic(output / 'progress.json', dict(state=state, pid=os.getpid(), updated_at=time.time(),
            total=len(manifest['records']), validated=sum(j.get('state') in ('validated','accepted') for j in jobs.values()),
            rejected=sum(j.get('state') == 'rejected' for j in jobs.values()),
            submitted_credits=spent, credit_cap=max_credits, concurrency=concurrency,
            remaining=sum(jobs.get(r['source'],{}).get('state') not in ('validated','accepted','rejected') for r in manifest['records'])))
    # Previously submitted work always resumes before any additional payment.
    pending = [r for r in records if jobs.get(r['source'],{}).get('state') not in ('validated','accepted','rejected','failed','unknown','submitting')]
    pending.sort(key=lambda r: (0 if jobs.get(r['source'],{}).get('state') == 'submitted' else 1,
                                0 if r['cached'] else 1))
    active = []
    spent = 0
    capped = False
    deferred = False
    def stopping(): return any(p.exists() for p in (output/'stop-after-current', *stop_files))
    matting_prices = {}
    def matting_price(record):
        size = tuple(record['size'])
        if size not in matting_prices:
            matting_prices[size] = api.call('/image/v1/estimate', dict(category='Matting', **MATTING,
                input_width=size[0], input_height=size[1]))['credits']
        return matting_prices[size]
    try:
        progress('running')
        while pending or active:
            while pending and len(active) < concurrency and not stopping():
                r = pending[0]; source = r['source']; job = jobs.setdefault(source, {})
                raw = Path(r['raw'])
                if job.get('state') != 'submitted':
                    if raw.exists():
                        expected_hash = r['raw_sha256'] or job.get('upscale_sha256')
                        if digest(raw) != expected_hash: raise ValueError('Wonder RGB master changed')
                        if r.get('operation') == 'upscale-only':
                            destination = output/'4x'/source
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            with Image.open(raw) as im: im.convert('RGBA').save(destination)
                            job.update(state='validated', validation=dict(passed=True, sha256=digest(destination),
                                size=r['size'], silhouette_iou=1, cleanup=dict(type='opaque-artwork', original_pixels_restored=False)))
                            pending.pop(0); progress('running'); continue
                        stage = 'matting'; size = r['size']
                        estimate = api.call('/image/v1/estimate', dict(category='Matting', **MATTING, input_width=size[0], input_height=size[1]))
                        upload = raw
                    else:
                        stage = 'upscale'; size = r['original_size']; estimate = api.estimate(size)
                        upload = output / 'inputs' / source
                        upload.parent.mkdir(parents=True, exist_ok=True)
                        clean = Path(manifest['source_batch']) / 'cleaned' / source
                        if digest(clean) != r['cleaned_sha256']: raise ValueError('Prepared source changed')
                        with Image.open(clean) as im:
                            rgba = im.convert('RGBA'); matte = Image.new('RGB', rgba.size, (127,127,127))
                            matte.paste(rgba, mask=rgba.getchannel('A')); matte.save(upload)
                    credits = estimate['credits']
                    # Reserve both stages before starting another Wally frame.
                    owed = sum(matting_price(other) for other in records if other['source'] != source
                               and other.get('operation') != 'upscale-only'
                               and (jobs.get(other['source'], {}).get('state') == 'upscaled'
                                    or (jobs.get(other['source'], {}).get('state') == 'submitted'
                                        and jobs[other['source']].get('stage') == 'upscale')))
                    reserve = credits + (matting_price(r) if stage == 'upscale' and r.get('operation') != 'upscale-only' else 0) + owed
                    if not isinstance(credits, (int, float)) or credits < 0: raise ValueError('Invalid price estimate')
                    if credits > 1 and manifest.get('kind') != 'scene': raise ValueError('Unexpected price; inspect estimate before paying')
                    if spent + reserve > max_credits or api.balance() < reserve:
                        capped = True; break
                    capped = False
                    job.update(state='submitting', stage=stage, estimate=estimate, input_sha256=digest(upload), updated_at=time.time())
                    progress('running')
                    try:
                        response = api.submit(upload, size) if stage == 'upscale' else api.call('/image/v1/matting/async', MATTING, image=upload)
                        job.update(state='submitted', process_id=response['process_id'])
                        job.setdefault('history', []).append(dict(stage=stage, process_id=response['process_id'], estimate=estimate))
                        spent += credits; progress('running')
                    except Exception as error:
                        job.update(state='unknown', error=str(error)); progress('interrupted'); raise
                    print(f'{stage}: {source} ({spent}/{max_credits} credits this run)', flush=True)
                pending.pop(0)
                active.append((r, time.monotonic() + poll_timeout))
            for r, deadline in list(active):
                source = r['source']; job = jobs[source]
                status = api.call('/image/v1/status/' + job['process_id'])['status']
                if status in ('Failed', 'Cancelled'):
                    job.update(state='failed', error=status); active.remove((r, deadline)); progress('running'); continue
                if status != 'Completed':
                    if time.monotonic() > deadline:
                        job['last_poll_timeout'] = time.time()
                        active.remove((r, deadline)); deferred = True
                        print(f'Awaiting provider: {source}; saved paid ID retained without resubmission.', flush=True)
                        progress('running')
                    continue
                raw = Path(r['raw'])
                if job['stage'] == 'upscale':
                    raw.parent.mkdir(parents=True, exist_ok=True); api.download(job['process_id'], raw)
                    with Image.open(raw) as im:
                        if list(im.size) != r['size']: raise ValueError('Wrong upscale dimensions')
                    job.update(state='upscaled', upscale_sha256=digest(raw))
                    if r.get('operation') == 'upscale-only':
                        destination = output/'4x'/source
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with Image.open(raw) as im: im.convert('RGBA').save(destination)
                        job.update(state='validated', validation=dict(passed=True, sha256=digest(destination),
                            size=r['size'], silhouette_iou=1, cleanup=dict(type='opaque-artwork', original_pixels_restored=False)))
                    else: pending.insert(0, r)
                else:
                    provider = output / 'provider' / source
                    provider.parent.mkdir(parents=True, exist_ok=True); api.download(job['process_id'], provider)
                    destination = output / '4x' / source
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # First inspect provider alpha. Character clothes can be gray;
                    # cannon's broad gray-key cleanup is intentionally not applied.
                    shutil.copy2(provider, destination)
                    check = character_validation if 'AKOS_0026' not in source else validate
                    if re.fullmatch(r'costumes/LFLF_0009_AKOS_0027_frame_\d+\.png', source):
                        from validate_rope_cutout import validate_rope
                        check = validate_rope
                    report = check(destination, raw, Path(manifest['source_batch']) / 'cleaned' / source)
                    report['cleanup'] = dict(type='provider-alpha', original_pixels_restored=False)
                    job.update(state='validated' if report['passed'] else 'rejected', validation=report)
                    print(f'{job["state"]}: {source} IoU={report["silhouette_iou"]:.3f}', flush=True)
                active.remove((r, deadline)); capped = False; progress('running')
            if stopping() and not active: break
            if capped and not active: break
            if active: time.sleep(4)
        progress('stopped' if stopping() else 'credit_cap' if capped else 'awaiting_provider' if deferred else 'awaiting_review')
    except Exception:
        progress('interrupted'); raise


def review(output, sources):
    """Record an explicit visual review separately from the running job journal."""
    jobs = load_jobs(output)
    if not sources: raise ValueError('Select the visually reviewed frames')
    for source in sources:
        job = jobs.get(source, {})
        if job.get('state') not in ('validated','accepted') or not job['validation']['passed']:
            raise ValueError('Cannot approve a rejected/unvalidated cutout')
        if digest(output / '4x' / source) != job['validation']['sha256']: raise ValueError('Cutout changed')
        atomic(output / 'reviews' / (source + '.json'), dict(sha256=job['validation']['sha256'], reviewed_at=time.time()))


def install(output, local):
    stopped(local)
    manifest = json.loads((output / 'manifest.json').read_text())
    jobs = load_jobs(output)
    batch = Path(manifest['source_batch'])
    originals = {r['source']: r for r in json.loads((batch / 'manifest.json').read_text())['records']}
    reviewed = []
    knife = manifest.get('kind') == 'difficulty-knife'
    if knife and {r['source'] for r in manifest['records']} != {f'costumes/LFLF_0087_AKOS_0439_frame_{n}.png' for n in range(4)}:
        raise ValueError('Knife scope must contain exactly its four cels')
    for r in manifest['records']:
        source = r['source']; job = jobs.get(source,{})
        pattern = r'costumes/LFLF_0087_AKOS_0439_frame_[0-3]\.png' if knife else r'costumes/LFLF_(?:0001_AKOS_0002|0009_AKOS_0025)_frame_\d+\.png'
        if not re.fullmatch(pattern, source):
            raise ValueError('Unexpected character install scope')
        approval = output / 'reviews' / (source + '.json')
        if job.get('state') != 'accepted' and not approval.exists(): continue
        master = output / '4x' / source
        if job.get('state') not in ('accepted','validated') or not job['validation']['passed']: raise ValueError('Unvalidated review')
        sha = digest(master)
        if sha != job['validation']['sha256'] or (approval.exists() and sha != json.loads(approval.read_text())['sha256']):
            raise ValueError('Reviewed cutout changed')
        with Image.open(master) as im:
            if im.mode != 'RGBA' or list(im.size) != r['size']: raise ValueError('Invalid runtime texture')
        reviewed.append((r, sha))
    if not reviewed: raise ValueError('No reviewed character cutouts')
    receipt = []
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        pending = []
        for r, sha in reviewed:
            source = r['source']; master = output / '4x' / source
            destinations = [('asset-tool', batch / '4x' / source)] + [
                (pack, local / 'hd' / pack / source.replace('_frame_', '_aframe_')) for pack in ('topaz-cannon','topaz-crisp')]
            for label, target in destinations:
                backup = output / 'previous' / label / source
                if target.exists() and not backup.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(target, backup)
                elif label == 'asset-tool' and not backup.exists() and (batch / '6x' / source).exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    with Image.open(batch / '6x' / source) as im: im.resize(tuple(r['size']), Image.Resampling.LANCZOS).save(backup)
                staged = Path(temporary) / str(len(pending)); shutil.copy2(master, staged)
                pending.append((staged, target)); receipt.append(dict(source=source, target=str(target.resolve()), sha256=sha))
        for staged, target in pending:
            target.parent.mkdir(parents=True, exist_ok=True); staged.replace(target)
    policy_file = batch / 'protected-cutouts.json'
    policy = json.loads(policy_file.read_text()) if policy_file.exists() else {}
    for r, sha in reviewed:
        policy[f"4:{r['source']}"] = dict(file=str((output / '4x' / r['source']).resolve()), sha256=sha,
            upscale_job_key=job_key(originals[r['source']],4), provenance=r['cached'] or dict(path=r['raw']))
    atomic(policy_file, policy)
    atomic(output / 'installation.json',dict(scale=4, installed_at=time.time(), files=receipt,
        original_pixels_restored=False, original_mask_applied=False))
    print(f'Installed {len(reviewed)} reviewed character cutouts in both Topaz packs and the editor.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare','pilot','run','review','install','audit'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--batch', type=Path, default=ROOT / 'output/topaz-batch')
    parser.add_argument('--source', action='append', default=[])
    parser.add_argument('--max-credits', type=int, default=2)
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--local', type=Path, default=ROOT / '.playtest')
    parser.add_argument('--repair', action='store_true', help='Recover truncated provider alpha using enhanced RGB only')
    args = parser.parse_args()
    if args.command == 'review': return review(args.output, args.source)
    if args.command == 'install': return install(args.output, args.local)
    if args.command == 'audit': return audit(args.output, args.repair)
    with locked(args.output):
        if args.command == 'prepare': prepare(args.output, args.batch)
        else:
            if args.command == 'pilot' and not args.source: parser.error('Select pilot sources explicitly')
            run(args.output, API(ROOT / '.context/secrets/topaz-api-key',4), args.max_credits,
                args.source, args.concurrency, args.command != 'pilot')


if __name__ == '__main__': main()
