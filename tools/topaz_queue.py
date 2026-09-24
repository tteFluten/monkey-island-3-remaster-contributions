#!/usr/bin/env python3
"""Bounded async Topaz queue with serial credit reservations and resumable job IDs."""
import argparse
import fcntl
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from PIL import Image
from topaz_batch import API, SETTINGS, atomic_image, database, job_key, materialize, restore_alpha


def run(root, api, selection, max_credits, concurrency=4, timeout=1800, poll_interval=5):
    if getattr(api, 'scale', 6) != 6:
        raise ValueError('This queue supports 6x; use topaz_batch.py --scale 4 for direct 4x jobs')
    if not 1 <= concurrency <= 4 or max_credits < 0:
        raise ValueError('Use 1–4 concurrent jobs and a nonnegative credit cap')
    manifest = json.loads((root / 'manifest.json').read_text())
    by_source = {r['source']: r for r in manifest['records']}
    if not selection or len(selection) != len(set(selection)):
        raise ValueError('Selection must be nonempty and deduplicated')
    records = []
    for source in selection:
        record = by_source.get(source)
        if not record or record.get('canonical') != source or 'derived_from' in record:
            raise ValueError(f'Not a canonical prepared input: {source}')
        path = root / 'cleaned' / source
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['cleaned_sha256']:
            raise ValueError(f'Prepared input changed: {source}')
        records.append(record)
    db = database(root)
    active, pending = [], []
    spent = completed = 0
    estimates = {}
    available = api.balance()
    for record in records:
        key = job_key(record)
        row = db.execute('SELECT state, process_id FROM jobs WHERE key=?', (key,)).fetchone()
        if row and row[0] == 'complete' and (root / '6x' / record['source']).exists():
            continue
        if row and (row[0] in ('submitting', 'failed') or not row[1]):
            db.close()
            raise RuntimeError(f'Inspect saved {row[0]} job before retrying: {record["source"]}')
        pending.append((record, row[1] if row else None))
    # Resume paid jobs before spending any additional credits.
    pending.sort(key=lambda item: item[1] is None)

    def progress(state):
        counts = dict(db.execute('SELECT state, COUNT(*) FROM jobs GROUP BY state').fetchall())
        value = dict(state=state, pid=os.getpid(), updated_at=time.time(),
                     current_source=active[0][0]['source'] if active else None,
                     active_sources=[r['source'] for r, _, _ in active],
                     run_completed=completed, run_estimated_credits=spent,
                     run_credit_cap=max_credits, job_counts=counts,
                     model=SETTINGS['model'], enhancement='high', scale=6)
        temporary = root / 'progress.json.tmp'
        temporary.write_text(json.dumps(value, indent=2))
        temporary.replace(root / 'progress.json')

    capped = False
    try:
        print(f'Available credits: {available}; run cap: {max_credits}; pending: {len(pending)}', flush=True)
        progress('running')
        while pending or active:
            while pending and len(active) < concurrency and not capped:
                record, pid = pending[0]
                key = job_key(record)
                if not pid:
                    size = tuple(record['size'])
                    if size not in estimates:
                        estimates[size] = api.estimate(size)
                    credits = estimates[size]['credits']
                    # All paid submissions and budget updates happen on this
                    # thread, so concurrency cannot race the spending cap.
                    available = api.balance()
                    if spent + credits > max_credits or credits > available:
                        capped = True
                        print('Credit cap reached; finishing submitted jobs.', flush=True)
                        break
                    with tempfile.TemporaryDirectory(dir=root) as temporary:
                        upload = Path(temporary) / 'input.png'
                        with Image.open(root / 'cleaned' / record['source']) as original:
                            original = original.convert('RGBA')
                            if original.size != size:
                                raise ValueError('Prepared dimensions changed')
                            matte = Image.new('RGB', size, (127, 127, 127))
                            matte.paste(original, mask=original.getchannel('A'))
                            matte.save(upload)
                        db.execute('INSERT INTO jobs VALUES (?, ?, ?, NULL, ?, NULL)',
                                   (key, record['source'], 'submitting', credits))
                        db.commit()
                        # Never retry a paid submission with an unknown result.
                        pid = api.submit(upload, size)['process_id']
                    db.execute('UPDATE jobs SET state=?, process_id=? WHERE key=?', ('submitted', pid, key))
                    db.commit()
                    spent += credits
                    print(f'Submitted {record["source"]}: {credits} credit(s)', flush=True)
                pending.pop(0)
                active.append((record, pid, time.monotonic() + timeout))
                progress('processing')
            for record, pid, deadline in list(active):
                key = job_key(record)
                status = api.call('/image/v1/status/' + pid)['status']
                if status in ('Failed', 'Cancelled'):
                    db.execute('UPDATE jobs SET state=?, error=? WHERE key=?', ('failed', status, key))
                    db.commit()
                    raise RuntimeError(f'Topaz {status}: {record["source"]}')
                if status != 'Completed':
                    if time.monotonic() > deadline:
                        raise TimeoutError('Job timed out; saved IDs will resume without resubmitting')
                    continue
                raw = root / 'raw' / (key + '.png')
                raw.parent.mkdir(exist_ok=True)
                try:
                    api.download(pid, raw)
                    with Image.open(raw) as result, Image.open(root / 'cleaned' / record['source']) as original:
                        atomic_image(restore_alpha(result, original), root / '6x' / record['source'])
                except Exception as error:
                    db.execute('UPDATE jobs SET state=?, error=? WHERE key=?', ('download_pending', str(error), key))
                    db.commit()
                    raise
                db.execute('UPDATE jobs SET state=?, error=NULL WHERE key=?', ('complete', key))
                db.commit()
                completed += 1
                materialize(root, manifest, {record['source']})
                active.remove((record, pid, deadline))
                print(f'Completed {record["source"]}', flush=True)
                progress('processing' if active else 'running')
            if capped and not active:
                break
            if active:
                time.sleep(poll_interval)
        materialize(root, manifest)
        progress('stopped')
        print(f'Completed {completed}; submitted {spent} credits; unsubmitted {len(pending)}.', flush=True)
        return dict(completed=completed, credits=spent, pending=len(pending))
    except Exception:
        progress('interrupted')
        raise
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--key-file', type=Path, default=Path('.context/secrets/topaz-api-key'))
    parser.add_argument('--selection-file', type=Path, required=True)
    parser.add_argument('--max-credits', type=int, required=True)
    parser.add_argument('--concurrency', type=int, default=4)
    args = parser.parse_args()
    with (args.root / 'batch.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args.root, API(args.key_file), json.loads(args.selection_file.read_text()),
            args.max_credits, args.concurrency)
