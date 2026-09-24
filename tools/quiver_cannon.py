#!/usr/bin/env python3
"""Resumable reference-guided Quiver generation; no network calls during prepare.

Use tools/venv/bin/python tools/quiver_cannon.py --help.
"""
import argparse
import base64
from contextlib import contextmanager
import fcntl
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageFilter

from quiver_extract import extract, sha

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/quiver-cannon'
CHARACTERS = {2: 'Guybrush', 4: 'Guybrush', 25: 'Wally', 28: 'Wally',
              29: 'Guybrush', 30: 'Guybrush', 31: 'Guybrush', 33: 'Guybrush'}
PILOTS = [(30, 0), (30, 10), (25, 110), (25, 0)]
API = 'https://api.quiver.ai/v1'
SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'API redirect refused', headers, fp)


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


@contextmanager
def locked(output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'workflow.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another Quiver workflow is running') from None
        yield


def journal(output):
    db = sqlite3.connect(output / 'jobs.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, state TEXT NOT NULL, details TEXT NOT NULL)')
    return db


def save_job(db, key, state, **details):
    db.execute('INSERT OR REPLACE INTO jobs VALUES (?, ?, ?)', (key, state, json.dumps(details)))
    db.commit()


def job(db, key):
    row = db.execute('SELECT state, details FROM jobs WHERE key=?', (key,)).fetchone()
    return (row[0], json.loads(row[1])) if row else (None, {})


def prepare(output, game):
    manifest = extract(game, output, CHARACTERS)
    references = {}
    for r in manifest['records']:
        r['character'] = CHARACTERS[r['costume']]
        if (r['costume'], r['cel']) in [(30, 0), (25, 110)]:
            references[r['character']] = r['source']
    manifest['references'] = references
    manifest['pilot_keys'] = list(dict.fromkeys(r['artwork_sha256'] for pair in PILOTS
                                 for r in manifest['records'] if (r['costume'], r['cel']) == pair))
    manifest['scope'] = {'costumes': list(CHARACTERS), 'excluded_costumes': [26, 27, 32],
                         'note': 'Complete character costume resources, including shared Guybrush cels; room-9 activation only.'}
    atomic(output / 'manifest.json', manifest)
    print(f"Prepared {len(manifest['records'])} mappings; {len(set(r['artwork_sha256'] for r in manifest['records']))} unique sprites", flush=True)


def request(endpoint, payload=None):
    key = os.environ.get('QUIVERAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('Set QUIVERAI_API_KEY in the local process')
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'X-Trace-ID': str(uuid.uuid4())}
    req = urllib.request.Request(API + endpoint, data=json.dumps(payload).encode() if payload else None, headers=headers)
    # Deliberately no automatic POST retries, including on timeouts and 429.
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=1200) as res:
        return json.load(res), res.headers.get('X-Request-ID')


def reference(path):
    # Enlarging without filtering makes the original contours legible, retains the whole canvas.
    im = Image.open(path).convert('RGBA')
    factor = min(4, max(1, 2048 // max(im.size)))
    im = im.resize((im.width * factor, im.height * factor), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    im.save(buf, format='PNG')
    return {'base64': base64.b64encode(buf.getvalue()).decode()}


def payload_for(output, manifest, record):
    width, height = record['size']
    prompt = (f"Faithfully redraw the first reference as an editable SVG animation cel from The Curse of Monkey Island. "
              f"The sprite belongs to {record['character']}. The second reference is ONLY character/style context. "
              "Copy ONLY the exact visible artwork in the FIRST reference: same pose, facial expression, viewing direction, "
              "clothing, palette, outline, relative coordinates and proportions. If the first image is a detached head, "
              "body, hand, shadow or accessory, draw ONLY that part, never complete the character. "
              "Smooth the original cartoon line work into accurate detailed Bezier paths; retain the original painted colors. "
              "No redesign, no new details, no text, no pixel-square tracing. All empty space must be transparent. "
              f"Use viewBox=\"0 0 {width} {height}\". Preserve the entire original canvas and its transparent margins exactly. "
              "Do not center, crop, pad or scale the subject within that canvas. Preserve any translucent ground shadow.")
    return dict(model='arrow-2', stream=False, n=1, prompt=prompt,
                instructions='Return a self-contained static SVG using vector shapes only. No background rectangle, embedded images, external resources, scripts, fonts or animation.',
                references=[reference(output / 'cleaned' / record['source']),
                            reference(output / 'cleaned' / manifest['references'][record['character']])])


def normalize_svg(raw, size):
    if len(raw) > 8_000_000 or re.search(r'<!DOCTYPE|<!ENTITY', raw, re.I):
        raise ValueError('Unsupported SVG document')
    root = ET.fromstring(raw)
    if root.tag not in ('svg', f'{{{SVG}}}svg'):
        raise ValueError('Output is not SVG')
    allowed = {'svg', 'g', 'defs', 'path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline',
               'line', 'linearGradient', 'radialGradient', 'stop', 'title', 'desc'}
    for node in root.iter():
        if node.tag.split('}')[-1] not in allowed:
            raise ValueError('SVG contains non-vector or unsupported content')
        for attr, value in node.attrib.items():
            name = attr.split('}')[-1].lower()
            if name.startswith('on') or name in ('href', 'src', 'class', 'clip-path', 'mask', 'filter'):
                raise ValueError('SVG contains active or external content')
            if name == 'style' and re.search(r'(?:^|;)\s*(?:clip-path|mask|filter)\s*:', value, re.I):
                raise ValueError('SVG contains unsupported rendering effects')
            urls = re.findall(r'url\s*\(([^)]*)\)', value, re.I)
            if any(not u.strip().strip('\'"').startswith('#') for u in urls) or re.search(r'@import|javascript:|data:', value, re.I):
                raise ValueError('SVG contains external content')
    if 'viewBox' not in root.attrib:
        raise ValueError('SVG must declare its coordinate system')
    values = [float(x) for x in re.split(r'[ ,]+', root.attrib['viewBox'].strip())]
    if len(values) != 4 or not all(math.isfinite(x) for x in values) or min(values[2:]) <= 0:
        raise ValueError('Invalid viewBox')
    x, y, w, h = values
    width, height = size
    if abs(w / h / (width / height) - 1) > .01:
        raise ValueError('Generated canvas aspect ratio changed')
    # Uniform mapping, anchored to the declared canvas, never content bounding-box fitting.
    scale = width / w
    if abs(scale * h - height) > .1:
        raise ValueError('Cannot normalize canvas without distortion')
    outer = ET.Element(f'{{{SVG}}}svg', {'viewBox': f'0 0 {width} {height}',
                                      'width': str(width * 6), 'height': str(height * 6)})
    group = ET.SubElement(outer, f'{{{SVG}}}g', {'transform': f'scale({scale}) translate({-x} {-y})'})
    # Retain root presentation attributes as well as its child geometry.
    inner = ET.SubElement(group, f'{{{SVG}}}g', {k: v for k, v in root.attrib.items()
                                               if k not in ('viewBox', 'width', 'height', 'xmlns')})
    inner.extend(root)
    return ET.tostring(outer, encoding='unicode')


def alignment(source, rendered):
    a = np.array(source.convert('RGBA'))
    b = np.array(rendered.convert('RGBA').resize(source.size, Image.Resampling.LANCZOS))
    am, bm = a[:, :, 3] >= 192, b[:, :, 3] >= 192
    union = int((am | bm).sum())
    iou = float((am & bm).sum() / union) if union else 1.0
    # At most one source pixel of antialias contour variation; no large displacement.
    dilated = np.array(Image.fromarray((a[:, :, 3] > 0).astype('uint8') * 255).filter(ImageFilter.MaxFilter(3))) > 0
    outside = float((bm & ~dilated).sum() / max(1, bm.sum()))
    transparent = a[:, :, 3] == 0
    background = float((b[:, :, 3][transparent] >= 192).mean()) if transparent.any() else 0.0
    edge = np.concatenate((b[0, :, 3], b[-1, :, 3], b[:, 0, 3], b[:, -1, 3]))
    source_edge = np.concatenate((a[0, :, 3], a[-1, :, 3], a[:, 0, 3], a[:, -1, 3]))
    clipping = int(((edge > 192) & (source_edge == 0)).sum())
    passed = iou >= .90 and outside <= .01 and background <= .05 and clipping <= 2
    return dict(passed=passed, silhouette_iou=iou, outside_fraction=outside,
                background_fraction=background, new_edge_pixels=clipping)


def validate_one(output, record):
    key = record['artwork_sha256']
    response = json.loads((output / 'raw' / f'{key}.json').read_text())
    raw = response['data'][0]['svg']
    normalized = normalize_svg(raw, record['size'])
    for folder in ('svg', '6x', '4x'):
        (output / folder).mkdir(exist_ok=True)
    svg = output / 'svg' / f'{key}.svg'
    svg.write_text(normalized)
    for scale in (6, 4):
        target = output / f'{scale}x' / f'{key}.png'
        subprocess.run(['node', str(ROOT / 'tools/quiver_render.mjs'), str(svg), str(target),
                        *[str(v * scale) for v in record['size']]], check=True, capture_output=True)
        with Image.open(target) as im:
            if list(im.size) != [v * scale for v in record['size']]:
                raise ValueError('Rasterizer changed output dimensions')
    report = alignment(Image.open(output / 'cleaned' / record['source']), Image.open(output / '6x' / f'{key}.png'))
    report['output_hashes'] = {str(p.relative_to(output)): sha(p.read_bytes()) for p in
                               (svg, output / '6x' / f'{key}.png', output / '4x' / f'{key}.png')}
    return report


def generate(output, pilot=False):
    manifest = json.loads((output / 'manifest.json').read_text())
    records = {r['artwork_sha256']: r for r in reversed(manifest['records'])}
    db = journal(output)
    if not pilot:
        failed = [k for k in manifest['pilot_keys'] if job(db, k)[0] != 'accepted']
        if failed:
            raise RuntimeError('Representative sprites must pass geometry checks and visual review before the full run')
    keys = manifest['pilot_keys'] if pilot else list(records)
    models, _ = request('/models')
    model = next(m for m in models['data'] if m['id'] == 'arrow-2')
    atomic(output / 'model.json', model)
    for index, key in enumerate(keys):
        state, details = job(db, key)
        if state in ('accepted', 'geometry_passed'):
            continue
        if state in ('submitting', 'unknown', 'failed', 'rejected'):
            raise RuntimeError(f'{key[:12]} is {state}; no automatic resubmission')
        record = records[key]
        print(f"[{index + 1}/{len(keys)}] {record['source']}", flush=True)
        if state != 'downloaded':
            payload = payload_for(output, manifest, record)
            # Persist prompt and reference identities, never credentials/base64 payloads.
            details = dict(source=record['source'], model='arrow-2', prompt=payload['prompt'],
                           instructions=payload['instructions'], created_at=time.time(),
                           references=[record['source'], manifest['references'][record['character']]])
            save_job(db, key, 'submitting', **details)
            try:
                response, request_id = request('/svgs/generations', payload)
                atomic(output / 'raw' / f'{key}.json', response)
                details.update(request_id=request_id, usage=response.get('usage'), billing=response.get('billing'))
                save_job(db, key, 'downloaded', **details)
            except urllib.error.HTTPError as error:
                details['http_status'] = error.code
                details['request_id'] = error.headers.get('X-Request-ID') if error.headers else None
                # Server responses can contain user input; do not echo body or credentials.
                save_job(db, key, 'failed' if 400 <= error.code < 500 else 'unknown', **details)
                raise RuntimeError(f'Quiver HTTP {error.code}; stopped without retrying') from None
            except Exception as error:
                details['error_type'] = type(error).__name__
                save_job(db, key, 'unknown', **details)
                raise RuntimeError('Generation outcome uncertain; stopped without retrying') from None
        try:
            report = validate_one(output, record)
            details['validation'] = report
            save_job(db, key, 'geometry_passed' if report['passed'] else 'rejected', **details)
            print(json.dumps(report), flush=True)
            if not report['passed']:
                raise RuntimeError('Sprite failed alignment checks; batch stopped for review')
        except (ValueError, KeyError, IndexError, ET.ParseError, subprocess.CalledProcessError) as error:
            details['validation_error'] = str(error)[:200]
            save_job(db, key, 'rejected', **details)
            raise RuntimeError('Invalid SVG or rendering failure; cached response retained') from None


def review(output, keys):
    db = journal(output)
    for key in keys:
        state, details = job(db, key)
        if state != 'geometry_passed':
            raise ValueError(f'{key[:12]} has not passed geometry validation')
        details['visual_reviewed_at'] = time.time()
        save_job(db, key, 'accepted', **details)


def status(output):
    manifest = json.loads((output / 'manifest.json').read_text())
    db = journal(output)
    keys = set(r['artwork_sha256'] for r in manifest['records'])
    counts = {}
    for key, state in db.execute('SELECT key, state FROM jobs'):
        if key in keys: counts[state] = counts.get(state, 0) + 1
    unique = len(keys)
    counts['not_submitted'] = unique - sum(counts.values())
    usage = {'input_tokens': 0, 'output_tokens': 0}
    for (raw,) in db.execute('SELECT details FROM jobs'):
        detail = json.loads(raw)
        for attempt in [detail, *detail.get('previous_attempts', [])]:
            for field in usage:
                usage[field] += (attempt.get('usage') or {}).get(field, 0)
    model_file = output / 'model.json'
    rates = json.loads(model_file.read_text()).get('billing', {}).get('rates', {}) if model_file.exists() else {}
    estimated_cost = sum(usage[f'{kind}_tokens'] * rates.get(kind, 0) / 100_000_000_000
                         for kind in ('input', 'output')) if rates else None
    report = dict(mappings=len(manifest['records']), unique_sprites=unique, counts=counts,
                  usage=usage, estimated_usd_at_recorded_rates=estimated_cost,
                  complete=counts.get('accepted', 0) == unique)
    atomic(output / 'status.json', report)
    print(json.dumps(report, indent=2))


def install(output, hd, restore=False, runtime_format='svg'):
    # Pack has a separate directory: no existing costume files are overwritten.
    target = hd / 'quiver-cannon'
    if runtime_format not in ('svg', 'png'):
        raise ValueError('Runtime format must be svg or png')
    backup = output / 'previous-pack'
    receipt = output / 'installation.json'
    if restore:
        if not receipt.exists():
            raise ValueError('No installation receipt')
        info = json.loads(receipt.read_text())
        if str(hd.resolve()) != info['hd']:
            raise ValueError('Restore directory differs from installation')
        if target.exists():
            shutil.rmtree(target)
        if backup.exists():
            shutil.move(str(backup), target)
        receipt.unlink()
        print('Previous costume pack restored; restart the game')
        return
    manifest = json.loads((output / 'manifest.json').read_text())
    db = journal(output)
    if any(job(db, r['artwork_sha256'])[0] != 'accepted' for r in manifest['records']):
        raise ValueError('Installation requires all selected sprites to pass geometry and visual review')
    for key in set(r['artwork_sha256'] for r in manifest['records']):
        _, details = job(db, key)
        expected = details.get('validation', {}).get('output_hashes', {})
        if len(expected) != 3:
            raise ValueError('Approved output checksums are missing; validate and review again')
        for relative, digest in expected.items():
            artifact = (output / relative).resolve()
            if not artifact.is_relative_to(output.resolve()) or sha(artifact.read_bytes()) != digest:
                raise ValueError('Approved output changed; validate and review again')
    if not receipt.exists():
        if target.exists():
            shutil.copytree(target, backup)
        atomic(receipt, dict(hd=str(hd.resolve()), installed_at=time.time()))
    staging = hd / 'quiver-cannon.staging'
    if staging.exists():
        shutil.rmtree(staging)
    (staging / 'costumes').mkdir(parents=True)
    for record in manifest['records']:
        if runtime_format == 'svg':
            source = output / 'svg' / (record['artwork_sha256'] + '.svg')
            normalize_svg(source.read_text(), record['size'])
        else:
            source = output / '4x' / (record['artwork_sha256'] + '.png')
            with Image.open(source) as im:
                if im.mode != 'RGBA' or list(im.size) != [v * 4 for v in record['size']]:
                    raise ValueError(f"Invalid runtime image: {record['source']}")
        filename = Path(record['source'].replace('_frame_', '_aframe_')).with_suffix('.' + runtime_format)
        shutil.copy2(source, staging / 'costumes' / filename)
    atomic(staging / 'manifest.json', {**manifest, 'runtime_scale': 4})
    if target.exists():
        shutil.rmtree(target)
    staging.replace(target)
    print('Installed complete room-9 pack; restart the game')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'pilot', 'generate', 'validate', 'accept', 'status', 'install', 'restore'])
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--game', type=Path, default=ROOT / '.playtest/game')
    parser.add_argument('--hd', type=Path, default=ROOT / '.playtest/hd')
    parser.add_argument('--runtime-format', choices=['svg', 'png'], default='svg',
                        help='Install SVG masters for direct engine loading (default), or legacy 4x PNGs')
    parser.add_argument('--key', action='append', default=[], help='Full artwork hash for accept or validate; repeatable')
    args = parser.parse_args()
    if args.command == 'status':
        status(args.output)
        return
    with locked(args.output):
        if args.command == 'prepare':
            prepare(args.output, args.game)
        elif args.command in ('pilot', 'generate'):
            generate(args.output, args.command == 'pilot')
        elif args.command == 'accept':
            if not args.key:
                parser.error('accept requires --key after visual inspection')
            review(args.output, args.key)
        elif args.command == 'validate':
            manifest = json.loads((args.output / 'manifest.json').read_text())
            records = {r['artwork_sha256']: r for r in manifest['records']}
            db = journal(args.output)
            for key in args.key:
                state, details = job(db, key)
                if state not in ('downloaded', 'rejected', 'geometry_passed', 'accepted'):
                    raise ValueError('No cached generation to validate')
                details['validation'] = validate_one(args.output, records[key])
                save_job(db, key, 'geometry_passed' if details['validation']['passed'] else 'rejected', **details)
                print(json.dumps(details['validation']))
        elif args.command in ('install', 'restore'):
            install(args.output, args.hd, args.command == 'restore', args.runtime_format)
        else:
            status(args.output)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error))
