#!/usr/bin/env python3
"""Arrow 2 cannon-only redraws; preserve paid responses and existing character packs."""
import argparse
import base64
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import xml.etree.ElementTree as ET

from PIL import Image, ImageFilter
import numpy as np
import quiver_cannon as q
from quiver_walk import registered_svg
from quiver_ui import native_renderer, stopped
from quiver_ui_clip import flatten

OUTPUT = q.OUTPUT / 'cannon-sequence'


def prepare(output, sources):
    original = json.loads((sources / 'extraction.json').read_text())
    records = original['records']
    if len(records) != 14 or {r['cel'] for r in records} != set(range(14)) or any(r['costume'] != 26 or r['room'] != 9 for r in records):
        raise ValueError('Expected exactly the fourteen room-9 cannon cels')
    for record in records:
        source = sources / 'cleaned' / record['source']
        width, height = record['size']
        side = max(width, height) + 16
        x, y = (side - width) // 2, (side - height) // 2
        record['reference_canvas'] = dict(side=side, x=x, y=y)
        record['cleaned_sha256'] = q.sha(source.read_bytes())
        for folder in ('cleaned', 'references', 'raw'):
            (output / folder).mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output / 'cleaned' / record['source'])
        with Image.open(source) as image:
            square = Image.new('RGBA', (side, side))
            square.paste(image.convert('RGBA'), (x, y))
        square.resize((side * 4, side * 4), Image.Resampling.NEAREST).save(output / 'references' / record['source'])
    manifest = dict(original, records=records, operation='vectorization',
                    pilot_keys=[r['artwork_sha256'] for r in records if r['cel'] in (0, 5, 9)])
    if (output / 'manifest.json').exists() and json.loads((output / 'manifest.json').read_text()) != manifest:
        raise ValueError('Manifest changed; use a separate output directory')
    q.atomic(output / 'manifest.json', manifest)
    print('Prepared 14 cannon cels, with three representative pilots', flush=True)


def alignment(source, rendered):
    """Cannon cels touch the canvas: allow one source pixel of contour smoothing.

    Apply the same one-pixel boundary corridor on canvas edges as in the
    interior. A fixed count of two edge pixels is inappropriate for the cannon's
    long, edge-touching ropes/smoke. Displaced or filled backgrounds still fail.
    """
    report = q.alignment(source, rendered)
    allowed = np.array(source.convert('RGBA').getchannel('A').filter(ImageFilter.MaxFilter(3))) > 0
    opaque = np.array(rendered.convert('RGBA').resize(source.size, Image.Resampling.LANCZOS))[:, :, 3] > 192
    outside = opaque & ~allowed
    edge = int(outside[0].sum() + outside[-1].sum() + outside[:, 0].sum() + outside[:, -1].sum())
    report['edge_pixels_beyond_one_pixel'] = edge
    report['passed'] = (report['silhouette_iou'] >= .90 and report['outside_fraction'] <= .01
                        and report['background_fraction'] <= .05 and edge == 0)
    return report


def validate(output, record):
    key = record['artwork_sha256']
    source = output / 'cleaned' / record['source']
    if q.sha(source.read_bytes()) != record['cleaned_sha256']:
        raise ValueError('Source changed')
    raw = json.loads((output / 'raw' / f'{key}.json').read_text())['data'][0]['svg']
    repairs = output / 'repairs.json'
    repair = json.loads(repairs.read_text()).get(key) if repairs.exists() else None
    if repair:
        path = (output / repair['svg']).resolve()
        if repair['raw_sha256'] != q.sha(raw.encode()) or not repair.get('reason') or not path.is_relative_to(output.resolve()):
            raise ValueError('Repair does not match reviewed provider output')
        raw = path.read_text()
    raw, corrections = flatten(raw)
    if repair: corrections.append(dict(type='reviewed-vector-repair', **repair))
    registered = registered_svg(raw, record)
    if repair and repair.get('anchor'):
        anchor = repair['anchor']
        scale, x, y = [float(anchor[k]) for k in ('scale', 'x', 'y')]
        if not .99 <= scale <= 1.01 or max(abs(x), abs(y)) > 1:
            raise ValueError('Anchor correction exceeds one source pixel')
        root = ET.fromstring(registered)
        group = ET.Element(f'{{{q.SVG}}}g', {'transform': f'translate({x} {y}) scale({scale})'})
        group.extend(list(root)); root[:] = [group]
        registered = ET.tostring(root, encoding='unicode')
    staging = output / 'registered'
    (staging / 'raw').mkdir(parents=True, exist_ok=True)
    try:
        (staging / 'cleaned').symlink_to((output / 'cleaned').resolve())
    except FileExistsError:
        if (staging / 'cleaned').resolve() != (output / 'cleaned').resolve():
            raise ValueError('Unexpected staging source directory')
    q.atomic(staging / 'raw' / f'{key}.json', {'data': [{'svg': registered}]})
    report = q.validate_one(staging, record)
    with Image.open(source) as original, Image.open(staging / '6x' / f'{key}.png') as rendered:
        report.update(alignment(original, rendered))
    paths = []
    for folder, suffix in (('svg', '.svg'), ('4x', '.png'), ('6x', '.png')):
        relative = Path(folder) / (key + suffix)
        (output / folder).mkdir(exist_ok=True)
        shutil.copy2(staging / relative, output / relative)
        paths.append(relative)
    binary = native_renderer(output)
    size = tuple(v * 4 for v in record['size'])
    relative = Path('native-4x') / f'{key}.png'
    (output / relative).parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as temp:
        rgba = Path(temp) / 'render.rgba'
        subprocess.run([str(binary), str(output / paths[0]), str(rgba), *map(str, size)], check=True, capture_output=True)
        native = Image.frombytes('RGBA', size, rgba.read_bytes())
        native.save(output / relative)
        with Image.open(source) as original:
            report['native'] = alignment(original, native)
    paths.append(relative)
    report['passed'] = report['passed'] and report['native']['passed']
    report['corrections'] = corrections
    report['output_hashes'] = {str(p): q.sha((output / p).read_bytes()) for p in paths}
    return report


def generate(output, pilot):
    manifest = json.loads((output / 'manifest.json').read_text())
    with closing(q.journal(output)) as db:
        if not pilot and any(q.job(db, key)[0] != 'accepted' for key in manifest['pilot_keys']):
            raise ValueError('Review pilot outputs before the full batch')
        records = [r for r in manifest['records'] if not pilot or r['artwork_sha256'] in manifest['pilot_keys']]
        if any(q.job(db, r['artwork_sha256'])[0] in ('submitting', 'unknown', 'failed', 'rejected') for r in records):
            raise ValueError('Stopped job requires review; no automatic paid retries')
        models, _ = q.request('/models')
        q.atomic(output / 'model.json', next(m for m in models['data'] if m['id'] == 'arrow-2'))
    # Keep at most two paid requests in flight and drain them after any failure.
    native_renderer(output)
    failure = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {}; index = 0
        while pending or (index < len(records) and failure is None):
            while len(pending) < 2 and index < len(records) and failure is None:
                future = pool.submit(generate_one, output, records[index])
                pending[future] = records[index]['cel']; index += 1
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                try: future.result()
                except Exception as error:
                    if failure is None: failure = error
        if failure: raise failure


def generate_one(output, record):
    with closing(q.journal(output)) as db:
        key = record['artwork_sha256']
        state, details = q.job(db, key)
        if state in ('accepted', 'geometry_passed'): return
        if state in ('submitting', 'unknown', 'failed', 'rejected'):
            raise ValueError('Stopped job requires review; no automatic paid retries')
        if state != 'downloaded':
            payload = dict(model='arrow-2', stream=False, auto_crop=False,
                           image={'base64': base64.b64encode((output / 'references' / record['source']).read_bytes()).decode()})
            details = dict(source=record['source'], model='arrow-2', endpoint='/svgs/vectorizations', created_at=time.time())
            q.save_job(db, key, 'submitting', **details)
            print(f'Arrow 2 cannon cel {record["cel"]}', flush=True)
            try:
                response, request_id = q.request('/svgs/vectorizations', payload)
                q.atomic(output / 'raw' / f'{key}.json', response)
                details.update(request_id=request_id, response_id=response.get('id'), usage=response.get('usage'), billing=response.get('billing'))
                q.save_job(db, key, 'downloaded', **details)
            except Exception as error:
                state = 'failed' if isinstance(error, urllib.error.HTTPError) and error.code < 500 else 'unknown'
                q.save_job(db, key, state, **{**details, 'error_type': type(error).__name__})
                raise RuntimeError('API request stopped; no automatic retry') from None
        try:
            report = validate(output, record)
        except Exception as error:
            q.save_job(db, key, 'rejected', **{**details, 'validation_error': str(error)[:200]})
            raise
        q.save_job(db, key, 'geometry_passed' if report['passed'] else 'rejected', **{**details, 'validation': report})
        print(json.dumps(dict(cel=record['cel'], **report)), flush=True)
        if not report['passed']: raise RuntimeError('Geometry rejected; response preserved')


def install(output, local):
    stopped(local)
    manifest = json.loads((output / 'manifest.json').read_text())
    if len(manifest['records']) != 14 or {r['cel'] for r in manifest['records']} != set(range(14)) or any(r['costume'] != 26 or r['room'] != 9 or Path(r['source']).name != r['source'] for r in manifest['records']):
        raise ValueError('Installation requires only the fourteen cannon cels')
    target = local / 'hd/quiver-cannon/costumes'
    with closing(q.journal(output)) as db:
        for r in manifest['records']:
            state, details = q.job(db, r['artwork_sha256'])
            if state != 'accepted': raise ValueError('Review all cannon cels first')
            expected = details['validation']['output_hashes']
            key = r['artwork_sha256']
            if not {f'svg/{key}.svg', f'4x/{key}.png', f'6x/{key}.png', f'native-4x/{key}.png'} <= set(expected):
                raise ValueError('Missing reviewed artifacts')
            for relative, digest in expected.items():
                artifact = (output / relative).resolve()
                if not artifact.is_relative_to(output.resolve()) or q.sha(artifact.read_bytes()) != digest:
                    raise ValueError('Reviewed output changed')
    target.mkdir(parents=True, exist_ok=True)
    receipt = []
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        for r in manifest['records']:
            name = Path(r['source'].replace('_frame_', '_aframe_')).with_suffix('.svg').name
            source = output / 'svg' / (r['artwork_sha256'] + '.svg')
            q.normalize_svg(source.read_text(), r['size'])
            destination = target / name
            backup = output / 'previous-cannon' / name
            if destination.exists() and not backup.exists():
                backup.parent.mkdir(exist_ok=True)
                shutil.copy2(destination, backup)
            shutil.copy2(source, Path(temporary) / name)
            receipt.append(dict(file=name, sha256=q.sha(source.read_bytes())))
        for entry in receipt:
            (Path(temporary) / entry['file']).replace(target / entry['file'])
    q.atomic(target.parent / 'cannon-sequence.json', dict(model='arrow-2', runtime_scale=4, files=receipt))
    print('Installed 14 cannon SVGs; all other character textures preserved')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'pilot', 'generate', 'status', 'install'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--sources', type=Path, default=q.ROOT / 'output/topaz-batch/extracted-cannon')
    parser.add_argument('--local', type=Path, default=q.ROOT / '.playtest')
    args = parser.parse_args()
    with q.locked(args.output):
        if args.command == 'prepare': prepare(args.output, args.sources)
        elif args.command in ('pilot', 'generate'): generate(args.output, args.command == 'pilot')
        elif args.command == 'status': q.status(args.output)
        elif args.command == 'install': install(args.output, args.local)

if __name__ == '__main__': main()
