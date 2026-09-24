#!/usr/bin/env python3
"""Resumable Wonder 3.5 High batch at 4x or 6x. Never retries a submission."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

BASE = 'https://api.topazlabs.com'
SETTINGS = {'model': 'Wonder 3.5', 'enhancementStrength': 'high', 'output_format': 'png',
            'crop_to_fill': 'false', 'grain': 'false'}


class API:
    def __init__(self, key_file, scale=6):
        if scale not in (4, 6):
            raise ValueError('Topaz batch scale must be 4 or 6')
        self.scale = scale
        self.key = key_file.read_text().strip()
        if not self.key or any(c in self.key for c in '\r\n"\\'):
            raise ValueError('Invalid API key file')

    def call(self, route, fields=None, image=None):
        # Header travels on stdin, never argv, logs, manifests or source code.
        command = ['curl', '-sS', '--connect-timeout', '15', '--max-time', '180', '--config', '-', '-w', '\n%{http_code}', BASE + route]
        if fields is None or route in ('/image/v1/estimate-gen', '/image/v1/estimate'):
            # Reads and estimates are safe to retry; a paid submission is not.
            command += ['--retry', '3', '--retry-delay', '2', '--retry-all-errors']
        if fields is not None:
            command += ['-X', 'POST']
            for key, value in fields.items():
                command += ['--form-string', f'{key}={value}']
        if image:
            command += ['-F', f'image=@{image};type=image/png']
        result = subprocess.run(command, input=f'header = "X-API-KEY: {self.key}"\n',
                                text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(f'Topaz connection failed (curl {result.returncode}); check saved job before retrying')
        body, code = result.stdout.rsplit('\n', 1)
        if int(code) >= 400:
            raise RuntimeError(f'Topaz HTTP {code}: {body[:600].replace(self.key, "[redacted]")}')
        return json.loads(body)

    def balance(self):
        return self.call('/account/v1/credits/balance')['available_credits']

    def estimate(self, size):
        w, h = size
        return self.call('/image/v1/estimate-gen', {**SETTINGS, 'input_width': w, 'input_height': h,
                         'output_width': w * self.scale, 'output_height': h * self.scale})

    def submit(self, path, size):
        w, h = size
        return self.call('/image/v1/enhance-gen/async', {**SETTINGS, 'output_width': w * self.scale,
                         'output_height': h * self.scale}, image=path)

    def download(self, job, destination):
        response = self.call('/image/v1/download/' + job)
        url = response.get('download_url') or response.get('url', '')
        if not url.startswith('https://') or any(c in url for c in '\r\n"\\'):
            raise ValueError('Invalid download URL')
        # No API key is passed to the signed storage URL.
        temporary = destination.with_suffix('.download')
        result = subprocess.run(['curl', '-fsS', '--proto', '=https', '--connect-timeout', '15',
                                 '--max-time', '60', '--retry', '3', '--retry-delay', '2', '--retry-all-errors',
                                 '--config', '-', '-o', str(temporary)],
                                input=f'url = "{url}"\n', text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError('Output download failed; saved job can be resumed')
        temporary.replace(destination)


def atomic_image(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    im.save(tmp, format='PNG')
    tmp.replace(path)


def restore_alpha(raw, original, scale=6):
    expected = (original.width * scale, original.height * scale)
    if raw.size != expected:
        raise ValueError(f'Topaz returned {raw.size}, expected {expected}; output quarantined')
    reference = original.resize(expected, Image.Resampling.LANCZOS)
    alpha = reference.getchannel('A')
    rgb = np.array(raw.convert('RGB'))
    # Wonder may invent colors on the matte. Use the source's premultiplied
    # color at partial coverage/shadows instead of amplifying matte noise by
    # dividing by near-zero alpha. Opaque interiors retain the AI enhancement.
    edge = np.asarray(alpha) < 255
    rgb[edge] = np.asarray(reference.convert('RGB'))[edge]
    rgba = np.concatenate((rgb, np.asarray(alpha)[..., None]), axis=2)
    rgba[np.asarray(alpha) == 0] = 0
    return Image.fromarray(rgba)


def database(root):
    db = sqlite3.connect(root / 'jobs.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, source TEXT, state TEXT, process_id TEXT, credits INTEGER, error TEXT)')
    db.commit()
    return db


def job_key(record, scale=6):
    return hashlib.sha256((record['cleaned_sha256'] + json.dumps(SETTINGS, sort_keys=True) + f':{scale}:alpha-v1').encode()).hexdigest()


def preserve_cutout(root, record, scale):
    """Retain reviewed external matting; never rebuild its original-mask edges."""
    policy = root / 'protected-cutouts.json'
    if not policy.exists(): return False
    entry = json.loads(policy.read_text()).get(f"{scale}:{record['source']}")
    if not entry: return False
    if entry['upscale_job_key'] != job_key(record, scale):
        raise ValueError('Protected cutout source/settings changed; review matting again')
    source = Path(entry['file'])
    if hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Protected cutout changed; refusing original-edge fallback')
    destination = root / f'{scale}x' / record['source']
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    shutil.copyfile(source, temporary)
    temporary.replace(destination)
    return True


def run(root, api, limit, max_credits, only=(), timeout=1800, priority_prefixes=(), defer_downloads=False, scale=6):
    if scale not in (4, 6) or getattr(api, 'scale', scale) != scale:
        raise ValueError('API and batch scale must agree (4 or 6)')
    manifest = json.loads((root / 'manifest.json').read_text())
    records = [r for r in manifest['records'] if 'derived_from' not in r and r['source'] == r['canonical']]
    if only:
        records = [r for r in records if r['source'] in only]
        if len(records) != len(set(only)):
            raise ValueError('Requested sample is missing or a duplicate; select its canonical input')
    if priority_prefixes:
        def order(record):
            source = record['source']
            priority = next((i for i, prefix in enumerate(priority_prefixes) if source.startswith(prefix)), len(priority_prefixes))
            natural = tuple(int(part) if part.isdigit() else part for part in re.split(r'(\d+)', source))
            return priority, natural
        records.sort(key=order)
    db = database(root)
    spent, completed = 0, 0
    consecutive_download_errors = 0
    available = api.balance()
    def progress(state, source=None):
        counts = dict(db.execute('SELECT state, COUNT(*) FROM jobs GROUP BY state').fetchall())
        value = {'state': state, 'pid': os.getpid(), 'updated_at': time.time(), 'current_source': source,
                 'run_completed': completed, 'run_estimated_credits': spent, 'run_credit_cap': max_credits,
                 'job_counts': counts, 'model': SETTINGS['model'], 'enhancement': 'high', 'scale': scale}
        tmp = root / 'progress.json.tmp'
        tmp.write_text(json.dumps(value, indent=2))
        tmp.replace(root / 'progress.json')
    progress('running')
    print(f'Available credits: {available}; this run cap: {max_credits}; image cap: {limit}', flush=True)
    estimates = {}
    for record in records:
        if preserve_cutout(root, record, scale): continue
        key = job_key(record, scale)
        path = root / 'cleaned' / record['source']
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['cleaned_sha256']:
            raise ValueError(f'Prepared input changed: {record["source"]}')
        row = db.execute('SELECT state, process_id, credits FROM jobs WHERE key=?', (key,)).fetchone()
        destination = root / f'{scale}x' / record['source']
        if row and row[0] == 'complete' and destination.exists():
            continue
        if row and row[0] == 'download_pending' and defer_downloads:
            print(f'Download pending, preserving paid job: {record["source"]}', flush=True)
            continue
        if completed >= limit:
            break
        progress('running', record['source'])
        if row and row[0] in ('submitting', 'failed'):
            raise RuntimeError(f'{record["source"]}: saved state {row[0]}; inspect jobs.sqlite before resubmitting')
        original = Image.open(path).convert('RGBA')
        with tempfile.TemporaryDirectory(dir=root) as temp:
            temp = Path(temp)
            if not row:
                size = tuple(record['size'])
                if size not in estimates:
                    estimates[size] = api.estimate(size)
                credits = estimates[size]['credits']
                available = api.balance()
                if spent + credits > max_credits or credits > available:
                    print('Credit cap reached; remaining jobs kept pending.', flush=True)
                    break
                matte = Image.new('RGB', original.size, (127, 127, 127))
                matte.paste(original, mask=original.getchannel('A'))
                matte.save(temp / 'input.png')
                db.execute('INSERT INTO jobs VALUES (?, ?, ?, NULL, ?, NULL)',
                           (key, record['source'], 'submitting', credits))
                db.commit()
                response = api.submit(temp / 'input.png', original.size)
                pid = response['process_id']
                db.execute('UPDATE jobs SET state=?, process_id=? WHERE key=?', ('submitted', pid, key))
                db.commit()
                spent += credits
                available -= credits
                print(f'Submitted {record["source"]}: estimated {credits} credit(s)', flush=True)
                progress('processing', record['source'])
            else:
                pid = row[1]
                if not pid:
                    raise RuntimeError('Saved job has no process ID')
            deadline = time.monotonic() + timeout
            while True:
                status = api.call('/image/v1/status/' + pid)
                if status['status'] == 'Completed':
                    break
                if status['status'] in ('Failed', 'Cancelled'):
                    db.execute('UPDATE jobs SET state=?,error=? WHERE key=?', ('failed', status['status'], key))
                    db.commit()
                    raise RuntimeError(f'Topaz job {status["status"]}: {record["source"]}')
                if time.monotonic() > deadline:
                    raise TimeoutError('Topaz job timed out; resume to poll the existing job without resubmitting')
                time.sleep(5)
            raw = root / 'raw' / (key + '.png')
            raw.parent.mkdir(exist_ok=True)
            try:
                api.download(pid, raw)
                with Image.open(raw) as result:
                    result.load()
                    atomic_image(restore_alpha(result, original, scale), destination)
            except (RuntimeError, OSError) as error:
                if not defer_downloads:
                    raise
                db.execute('UPDATE jobs SET state=?,error=? WHERE key=?', ('download_pending', str(error), key))
                db.commit()
                consecutive_download_errors += 1
                print(f'Download deferred for {record["source"]}; paid job preserved.', flush=True)
                progress('running', record['source'])
                if consecutive_download_errors >= 3:
                    raise RuntimeError('Three consecutive download failures; stopping new paid submissions until storage recovers')
                continue
            consecutive_download_errors = 0
            db.execute('UPDATE jobs SET state=?,error=NULL WHERE key=?', ('complete', key))
            db.commit()
            completed += 1
            materialize(root, manifest, {record['source']}, scale)
            print(f'Completed {record["source"]} at {original.width * scale} x {original.height * scale}', flush=True)
            progress('running', record['source'])
    materialize(root, manifest, scale=scale)
    has_pending = db.execute("SELECT 1 FROM jobs WHERE state='download_pending' LIMIT 1").fetchone()
    progress('downloads_pending' if has_pending else 'stopped')
    db.close()
    print(f'Finished this run: {completed} images, {spent} estimated credits submitted.', flush=True)


def materialize(root, manifest, completed_sources=None, scale=6):
    # Duplicate inputs share the same paid result. Layer canvases reuse object
    # pixels at the exact extracted position, including negative clipped offsets.
    for record in manifest['records']:
        source = record.get('derived_from', record.get('canonical'))
        if source == record['source']:
            continue
        if completed_sources is not None and source not in completed_sources:
            continue
        if preserve_cutout(root, record, scale):
            if completed_sources is not None: completed_sources.add(record['source'])
            continue
        result = root / f'{scale}x' / source
        target = root / f'{scale}x' / record['source']
        if not result.exists():
            continue
        if 'derived_from' in record:
            w, h = record['size']
            canvas = Image.new('RGBA', (w * scale, h * scale))
            with Image.open(result) as obj:
                canvas.paste(obj, tuple(v * scale for v in record['offset']))
            atomic_image(canvas, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.tmp')
            shutil.copyfile(result, temporary)
            temporary.replace(target)
        if completed_sources is not None:
            completed_sources.add(record['source'])


def recompose(root, scale=6):
    """Rebuild alpha and layers from cached paid outputs, with no API calls."""
    manifest = json.loads((root / 'manifest.json').read_text())
    for record in manifest['records']:
        if record.get('canonical') != record['source']:
            continue
        if preserve_cutout(root, record, scale): continue
        raw = root / 'raw' / (job_key(record, scale) + '.png')
        if raw.exists():
            with Image.open(raw) as result, Image.open(root / 'cleaned' / record['source']) as original:
                atomic_image(restore_alpha(result, original, scale), root / f'{scale}x' / record['source'])
    materialize(root, manifest, scale=scale)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--key-file', type=Path, default=Path('.context/secrets/topaz-api-key'))
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--max-credits', type=int, default=3)
    parser.add_argument('--scale', type=int, choices=(4, 6), default=6)
    parser.add_argument('--only', action='append', default=[])
    parser.add_argument('--priority-prefix', action='append', default=[], help='Process these source prefixes first, preserving the full queue')
    parser.add_argument('--selection-file', type=Path, help='JSON array of canonical source names to process')
    parser.add_argument('--defer-downloads', action='store_true', help='Preserve unavailable paid outputs for later download and continue other frames')
    parser.add_argument('--recompose', action='store_true', help='Restore transparency from cached outputs without using credits')
    args = parser.parse_args()
    if args.selection_file:
        selection = json.loads(args.selection_file.read_text())
        if not isinstance(selection, list) or not all(isinstance(source, str) for source in selection):
            parser.error('Selection file must contain an array of source names')
        if not selection:
            parser.error('Selection file must not be empty')
        args.only.extend(selection)
    if args.limit < 1 or args.max_credits < 0:
        parser.error('Image limit must be positive; credit cap must be nonnegative (0 resumes downloads only)')
    with (args.root / 'batch.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.recompose:
            recompose(args.root, args.scale)
        else:
            try:
                run(args.root, API(args.key_file, args.scale), args.limit, args.max_credits, args.only,
                    priority_prefixes=args.priority_prefix, defer_downloads=args.defer_downloads, scale=args.scale)
            except Exception:
                status_path = args.root / 'progress.json'
                if status_path.exists():
                    status = json.loads(status_path.read_text())
                    status.update(state='interrupted', updated_at=time.time())
                    temporary = status_path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(status, indent=2))
                    temporary.replace(status_path)
                raise
