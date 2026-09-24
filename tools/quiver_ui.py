#!/usr/bin/env python3
"""Faithful Arrow 2 UI vectors, with resumable paid requests and reversible installation."""
import argparse
import base64
from contextlib import closing
import json
import io
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.error
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageFilter

import quiver_cannon as q
from prepare_topaz import chunks
from quiver_ui_clip import flatten

OUTPUT = q.ROOT / 'output/quiver-ui'
NAMES = ('system-cursor-icon', 'north-arrow-icon', 'northeast-arrow-icon',
         'east-arrow-icon', 'southeast-arrow-icon', 'south-arrow-icon',
         'southwest-arrow-icon', 'west-arrow-icon', 'northwest-arrow-icon')
SOURCES = tuple(f'objects/0003_{name}_{state:04d}.png' for name in NAMES for state in (0, 1))


def manifest(output):
    return json.loads((output / 'manifest.json').read_text())


def prepare(output, batch):
    originals = {r['source']: r for r in json.loads((batch / 'manifest.json').read_text())['records']}
    records = []
    for source in SOURCES:
        original = originals[source]
        data = (batch / 'cleaned' / source).read_bytes()
        if q.sha(data) != original['cleaned_sha256']:
            raise ValueError(f'Prepared original changed: {source}')
        with Image.open(batch / 'cleaned' / source) as im:
            if im.mode != 'RGBA' or list(im.size) != original['size']:
                raise ValueError(f'Invalid prepared image: {source}')
            width, height = im.size
            key = q.sha(struct.pack('<II', width, height) + im.tobytes())
            side = max(width, height) + 16
            x, y = (side - width) // 2, (side - height) // 2
            square = Image.new('RGBA', (side, side))
            square.paste(im, (x, y))
        record = dict(original, artwork_sha256=key, reference_canvas=dict(side=side, x=x, y=y))
        records.append(record)
        for folder in ('cleaned', 'references'):
            (output / folder / source).parent.mkdir(parents=True, exist_ok=True)
        (output / 'cleaned' / source).write_bytes(data)
        square.resize((side * 4, side * 4), Image.Resampling.NEAREST).save(output / 'references' / source)
    value = dict(model='arrow-2', operation='vectorization', records=records,
                 pilot_keys=list(dict.fromkeys(r['artwork_sha256'] for r in records[:4])))
    if (output / 'manifest.json').exists() and manifest(output) != value:
        raise ValueError('Prepared selection changed; use a new output directory')
    q.atomic(output / 'manifest.json', value)
    print(f'Prepared {len(records)} states, {len(set(r["artwork_sha256"] for r in records))} unique images')


def registered_svg(raw, record):
    canvas = record['reference_canvas']
    normalized = ET.fromstring(q.normalize_svg(raw, [canvas['side']] * 2))
    w, h = record['size']
    root = ET.Element(f'{{{q.SVG}}}svg', dict(viewBox=f'0 0 {w} {h}', width=str(w), height=str(h)))
    group = ET.SubElement(root, f'{{{q.SVG}}}g', dict(transform=f'translate({-canvas["x"]} {-canvas["y"]})'))
    group.extend(normalized)
    return ET.tostring(root, encoding='unicode')


def alignment(source, rendered, edge_tolerance=0, minimum_iou=.85):
    """Tiny UI glyphs tolerate one source pixel of contour smoothing, not displacement."""
    report = q.alignment(source, rendered)
    a = np.array(source.convert('RGBA'))[:, :, 3] >= 192
    b = np.array(rendered.convert('RGBA').resize(source.size, Image.Resampling.LANCZOS))[:, :, 3] >= 192
    if not a.any() or not b.any():
        return dict(report, passed=False)
    dilated = np.array(Image.fromarray(b.astype('uint8') * 255).filter(ImageFilter.MaxFilter(3))) > 0
    missing = float((a & ~dilated).sum() / a.sum())
    ay, ax = np.where(a)
    by, bx = np.where(b)
    bounds_delta = max(abs(float(v)) for v in (ax.min() - bx.min(), ay.min() - by.min(),
                                               ax.max() - bx.max(), ay.max() - by.max()))
    center_delta = max(abs(float(ax.mean() - bx.mean())), abs(float(ay.mean() - by.mean())))
    ratio = float(b.sum() / a.sum())
    passed = (report['silhouette_iou'] >= minimum_iou and report['outside_fraction'] <= .01
              and report['background_fraction'] <= .01 and report['new_edge_pixels'] <= edge_tolerance
              and missing <= .01 and bounds_delta <= 1 and center_delta <= .75 and .85 <= ratio <= 1.15)
    return dict(report, passed=passed, missing_interior_fraction=missing,
                bounds_delta=bounds_delta, center_delta=center_delta, area_ratio=ratio)


def native_renderer(output):
    binary = output / 'native-render'
    source = q.ROOT / 'tools/quiver_native_render.cpp'
    header = q.ROOT / 'tools/engine/quiver_svg.h'
    if not binary.exists() or binary.stat().st_mtime < max(source.stat().st_mtime, header.stat().st_mtime):
        subprocess.run(['c++', '-std=c++11', '-O2', '-I', str(q.ROOT / '.playtest/engine/source'),
                        '-I', str(header.parent), str(source), '-o', str(binary)], check=True, capture_output=True)
    return binary.resolve()


def restore_white_border(output, record, svg):
    """Recover only an omitted white border; colored Quiver artwork stays intact."""
    if not record['source'].startswith('objects/') or record['source'].split('_')[1] == 'system-cursor-icon':
        return svg, None
    source = np.array(Image.open(output / 'cleaned' / record['source']).convert('RGBA'))
    white = (source[:, :, :3].min(2) >= 245) & (source[:, :, 3] >= 192)
    if int(white.sum()) < 10:
        return svg, None
    with tempfile.TemporaryDirectory(dir=output) as temp:
        path = Path(temp) / 'before.svg'
        path.write_text(svg)
        png = path.with_suffix('.png')
        subprocess.run(['node', str(q.ROOT / 'tools/quiver_render.mjs'), str(path), str(png),
                        *map(str, record['size'])], check=True, capture_output=True)
        rendered = np.array(Image.open(png).convert('RGBA'))
    present = (rendered[:, :, :3].min(2) >= 230) & (rendered[:, :, 3] >= 128)
    if float((present & white).sum() / white.sum()) >= .25:
        return svg, None
    # This is the original white underlay only. Do not trace/repaint the colored arrow.
    bitmap = io.BytesIO()
    Image.fromarray(np.where(source[:, :, 3] >= 192, 0, 255).astype('uint8')).convert('1').save(bitmap, format='PPM')
    result = subprocess.run(['potrace', '-s', '--flat', '--turdsize', '0', '--opttolerance', '.15', '-o', '-', '-'],
                            input=bitmap.getvalue(), check=True, capture_output=True)
    traced = ET.fromstring(result.stdout)
    group = next(node for node in traced if node.tag.split('}')[-1] == 'g')
    group.set('fill', '#ffffff')
    root = ET.fromstring(svg)
    root.insert(0, group)
    return ET.tostring(root, encoding='unicode'), dict(type='restore-omitted-white-border',
        source_sha256=record['cleaned_sha256'], white_pixels=int(white.sum()),
        method='Original alpha contour as white vector underlay; colored paths remain Quiver output')


def validate(output, record):
    key = record['artwork_sha256']
    response = json.loads((output / 'raw' / f'{key}.json').read_text())
    raw = response['data'][0]['svg']
    repair_file = output / 'repairs.json'
    repair = json.loads(repair_file.read_text()).get(key) if repair_file.exists() else None
    if repair:
        path = (output / repair['svg']).resolve()
        if (repair.get('raw_sha256') != q.sha(raw.encode()) or not repair.get('reason')
                or not path.is_relative_to(output.resolve())):
            raise ValueError('Reviewed repair does not match this provider response')
        raw = path.read_text()
    raw, clip_corrections = flatten(raw)
    svg = registered_svg(raw, record)
    svg, border = restore_white_border(output, record, svg)
    # Coins touch their native canvas edges; use the existing two-pixel edge
    # allowance and stricter 90% overlap. Padded cursor glyphs must never clip.
    def geometry(source, rendered):
        coin = record.get('kind') == 'action_coin'
        return alignment(source, rendered, edge_tolerance=2 if coin else 0, minimum_iou=.90 if coin else .85)
    artifacts = [Path('svg') / f'{key}.svg', Path('4x') / f'{key}.png', Path('6x') / f'{key}.png']
    for relative in artifacts:
        (output / relative).parent.mkdir(parents=True, exist_ok=True)
    (output / artifacts[0]).write_text(svg)
    for scale, relative in zip((4, 6), artifacts[1:]):
        subprocess.run(['node', str(q.ROOT / 'tools/quiver_render.mjs'), str(output / artifacts[0]),
                        str(output / relative), *[str(v * scale) for v in record['size']]],
                       check=True, capture_output=True)
    with Image.open(output / 'cleaned' / record['source']) as source, Image.open(output / artifacts[1]) as rendered:
        report = geometry(source, rendered)
    native_reports = []
    binary = native_renderer(output)
    for scale in (4, 6):
        size = tuple(v * scale for v in record['size'])
        relative = Path(f'native-{scale}x') / f'{key}.png'
        (output / relative).parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output) as temp:
            rgba = Path(temp) / 'render.rgba'
            subprocess.run([str(binary), str(output / artifacts[0]), str(rgba), *map(str, size)],
                           check=True, capture_output=True)
            image = Image.frombytes('RGBA', size, rgba.read_bytes())
            image.save(output / relative)
            with Image.open(output / 'cleaned' / record['source']) as source:
                native_reports.append(geometry(source, image))
        artifacts.append(relative)
    report['native'] = native_reports
    report['corrections'] = clip_corrections + ([border] if border else [])
    if repair:
        report['reviewed_repair'] = {**repair, 'corrected_sha256': q.sha(raw.encode())}
    report['passed'] = report['passed'] and all(r['passed'] for r in native_reports)
    report['output_hashes'] = {str(p): q.sha((output / p).read_bytes()) for p in artifacts}
    return report


def validate_job(output, record):
    with closing(q.journal(output)) as db:
        key = record['artwork_sha256']
        state, details = q.job(db, key)
        try:
            report = validate(output, record)
        except (ValueError, KeyError, IndexError, ET.ParseError, subprocess.CalledProcessError) as error:
            q.save_job(db, key, 'rejected', **{**details, 'validation_error': str(error)[:200]})
            raise
        details.pop('visual_reviewed_at', None)
        details.pop('validation_error', None)
        q.save_job(db, key, 'geometry_passed' if report['passed'] else 'rejected', **{**details, 'validation': report})
        print(json.dumps(dict(key=key, source=record['source'], **report)), flush=True)
        return report


def generate(output, pilot=False):
    value = manifest(output)
    unique = {r['artwork_sha256']: r for r in reversed(value['records'])}
    keys = value['pilot_keys'] if pilot else list(dict.fromkeys(r['artwork_sha256'] for r in value['records']))
    with closing(q.journal(output)) as db:
        if not pilot and any(q.job(db, key)[0] != 'accepted' for key in value['pilot_keys']):
            raise ValueError('Review and accept the pilots first')
        for key in keys:
            if q.job(db, key)[0] in ('submitting', 'unknown', 'failed', 'rejected'):
                raise ValueError(f'{key}: stopped; no automatic paid retries')
        pending = [k for k in keys if q.job(db, k)[0] not in ('accepted', 'geometry_passed')]
        if not pending:
            return
        models, _ = q.request('/models')
        q.atomic(output / 'model.json', next(m for m in models['data'] if m['id'] == 'arrow-2'))
        for key in pending:
            record = unique[key]
            state, details = q.job(db, key)
            if state != 'downloaded':
                request = dict(model='arrow-2', stream=False, auto_crop=False,
                               image={'base64': base64.b64encode((output / 'references' / record['source']).read_bytes()).decode()})
                details = dict(source=record['source'], model='arrow-2', endpoint='/svgs/vectorizations',
                               reference_canvas=record['reference_canvas'], created_at=time.time())
                q.save_job(db, key, 'submitting', **details)
                print(f'Quiver Arrow 2: {record["source"]}', flush=True)
                try:
                    response, request_id = q.request('/svgs/vectorizations', request)
                    q.atomic(output / 'raw' / f'{key}.json', response)
                    details.update(request_id=request_id, response_id=response.get('id'),
                                   usage=response.get('usage'), billing=response.get('billing'))
                    q.save_job(db, key, 'downloaded', **details)
                except urllib.error.HTTPError as error:
                    q.save_job(db, key, 'failed' if error.code < 500 else 'unknown',
                               **{**details, 'http_status': error.code})
                    raise RuntimeError(f'Quiver HTTP {error.code}; stopped without retrying') from None
                except Exception as error:
                    q.save_job(db, key, 'unknown', **{**details, 'error_type': type(error).__name__})
                    raise RuntimeError('Uncertain request outcome; no automatic retry') from None
            if not validate_job(output, record)['passed']:
                raise RuntimeError('Geometry rejected; cached response retained')


def stopped(local):
    process = local / 'process.json'
    if process.exists():
        pid = json.loads(process.read_text())['pid']
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        raise RuntimeError('Stop the game before changing cursor textures')


def object_ids(local):
    index = next(payload for tag, _, payload in chunks((local / 'game/COMI.LA0').read_bytes()) if tag == 'DOBJ')
    ids = {}
    for number in range(struct.unpack_from('<I', index)[0]):
        name = index[4 + number * 46:44 + number * 46].split(b'\0')[0].decode()
        ids.setdefault(name, []).append(str(number))
    if any(len(ids.get(name, [])) != 1 for name in NAMES):
        raise ValueError('Game object IDs are missing or ambiguous')
    return {name: ids[name][0] for name in NAMES}


def install(output, local, restore=False):
    stopped(local)
    hd = local / 'hd'
    receipt = output / 'installation.json'
    backup = output / 'previous-ui'
    map_path = hd / 'object_map.json'
    mapping = json.loads(map_path.read_text()) if map_path.exists() else {}
    if restore:
        info = json.loads(receipt.read_text())
        if info['local'] != str(local.resolve()):
            raise ValueError('Restore directory differs from installation')
        for target in info['files']:
            saved = backup / target
            if saved.exists():
                shutil.copy2(saved, hd / target)
            else:
                (hd / target).unlink(missing_ok=True)
        # Restore only the room-3 states touched by installation. Preserve other rooms/objects.
        for obj, previous in info['mapping'].items():
            entry = mapping.get(obj)
            if entry is None:
                continue
            current = set(entry.get('rooms', {}).get('3', {}).get('states', []))
            states = sorted((current - {0, 1}) | set(previous or []))
            if states or previous is not None:
                entry.setdefault('rooms', {}).setdefault('3', {})['states'] = states
            else:
                entry.get('rooms', {}).pop('3', None)
                if not entry.get('rooms'):
                    mapping.pop(obj, None)
        q.atomic(map_path, mapping)
        receipt.unlink()
        shutil.rmtree(backup)
        print('Previous UI restored; restart the game')
        return
    records = manifest(output)['records']
    if [r['source'] for r in records] != list(SOURCES):
        raise ValueError('Unexpected UI selection')
    with closing(q.journal(output)) as db:
        for record in records:
            key = record['artwork_sha256']
            state, details = q.job(db, key)
            if state != 'accepted':
                raise ValueError('Installation requires all selected artwork to be accepted')
            hashes = details.get('validation', {}).get('output_hashes', {})
            svg = f'svg/{key}.svg'
            if svg not in hashes or q.sha((output / svg).read_bytes()) != hashes[svg]:
                raise ValueError('Approved SVG changed; validate and review again')
            q.normalize_svg((output / svg).read_text(), record['size'])
    ids = object_ids(local)
    targets = [str(Path(r['source']).with_suffix('.svg')) for r in records]
    if receipt.exists() and json.loads(receipt.read_text())['local'] != str(local.resolve()):
        raise ValueError('Already installed to a different directory')
    if not receipt.exists():
        previous = {}
        for name, obj in ids.items():
            old_room = mapping.get(obj, {}).get('rooms', {}).get('3')
            previous[obj] = old_room.get('states', []) if old_room is not None else None
        for target in targets:
            if (hd / target).exists():
                (backup / target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(hd / target, backup / target)
        backup.mkdir(parents=True, exist_ok=True)
        q.atomic(receipt, dict(local=str(local.resolve()), files=targets, mapping=previous))
    with tempfile.TemporaryDirectory(dir=local, prefix='quiver-ui-') as temp:
        stage = Path(temp)
        for record, target in zip(records, targets):
            (stage / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output / 'svg' / f'{record["artwork_sha256"]}.svg', stage / target)
            _, name, state = Path(record['source']).stem.split('_')
            entry = mapping.setdefault(ids[name], dict(name=name, rooms={}))
            room = entry['rooms'].setdefault('3', dict(states=[]))
            room['states'] = sorted(set(room['states'] + [int(state)]))
        for target in targets:
            (hd / target).parent.mkdir(parents=True, exist_ok=True)
            (stage / target).replace(hd / target)
        q.atomic(map_path, mapping)
    print(f'Installed {len(targets)} native SVG cursor states; restart the game')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'pilot', 'generate', 'validate', 'accept', 'status', 'install', 'restore'])
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--batch', type=Path, default=q.ROOT / 'output/topaz-batch')
    parser.add_argument('--local', type=Path, default=q.ROOT / '.playtest')
    parser.add_argument('--key', action='append', default=[])
    args = parser.parse_args()
    with q.locked(args.output):
        if args.command == 'prepare':
            prepare(args.output, args.batch)
        elif args.command in ('pilot', 'generate'):
            generate(args.output, args.command == 'pilot')
        elif args.command in ('validate', 'accept'):
            records = {r['artwork_sha256']: r for r in manifest(args.output)['records']}
            if not args.key or any(k not in records for k in args.key):
                raise ValueError('Specify valid --key values from the manifest')
            if args.command == 'validate':
                for key in args.key:
                    validate_job(args.output, records[key])
            else:
                q.review(args.output, args.key)
        elif args.command == 'status':
            q.status(args.output)
        else:
            install(args.output, args.local, args.command == 'restore')


if __name__ == '__main__':
    main()
