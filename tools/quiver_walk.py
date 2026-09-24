#!/usr/bin/env python3
"""Quiver Arrow 2 walking preview, with explicit reference-canvas registration.

Paid requests are never retried automatically. This creates actual Quiver
outputs, not local vector traces. All generated material is ignored output.
"""
import argparse
import base64
import copy
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import closing
import json
import io
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import xml.etree.ElementTree as ET

from PIL import Image
import numpy as np

from costume_sequences import cels
from quiver_extract import resources, sha
import quiver_cannon as q

OUTPUT = q.OUTPUT / 'walking'


def prepare(output, game, sources=q.OUTPUT, operation='generation'):
    existing = output / 'manifest.json'
    if existing.exists() and json.loads(existing.read_text()).get('operation', 'generation') != operation:
        raise ValueError('Use a separate output directory for a different Quiver operation')
    original = json.loads((sources / 'manifest.json').read_text())
    fields = next(fields for cid, room, raw, fields, _ in resources(game, [2]) if cid == 2)
    walk, _ = cels(fields, 2)
    stand_body, _ = cels(fields, 3)
    stand_head, _ = cels(fields, 5)
    # The stand chore updates bodies only. The head persists from init/talk-stop;
    # exact-pose fallback therefore requires both sets for an SVG idle pose.
    stand = sorted(set(stand_body + stand_head))
    initial, _ = cels(fields, 1)
    if not set(initial) <= set(stand):
        raise ValueError('Idle selection does not cover the initial multipart pose')
    records = [dict(r) for r in original['records'] if r['costume'] == 2 and r['cel'] in set(walk + stand)]
    (output / 'cleaned').mkdir(parents=True, exist_ok=True)
    (output / 'references').mkdir(exist_ok=True)
    for r in records:
        source = sources / 'cleaned' / r['source']
        shutil.copy2(source, output / 'cleaned' / r['source'])
        width, height = r['size']
        side = max(width, height) + 16
        x, y = (side - width) // 2, (side - height) // 2
        r['reference_canvas'] = dict(side=side, x=x, y=y)
        r['sprite_role'] = ('standing_head' if r['cel'] in stand_head else
                            'standing_body' if r['cel'] in stand_body else 'walking')
        square = Image.new('RGBA', (side, side))
        square.paste(Image.open(source).convert('RGBA'), (x, y))
        square.resize((side * 4, side * 4), Image.Resampling.NEAREST).save(output / 'references' / r['source'])
    manifest = dict(original, records=records,
                    pilot_keys=[next(r['artwork_sha256'] for r in records if r['cel'] == 599)],
                    operation=operation,
                    scope=dict(character='Guybrush', costume=2, walking_cels=walk, standing_cels=stand,
                               standing_body_cels=stand_body, standing_head_cels=stand_head,
                               provenance=f'Quiver Arrow 2 paid {operation}; character paths are provider output; shadow repairs are recorded separately'))
    q.atomic(output / 'manifest.json', manifest)
    print(f'Prepared {len(walk)} walking and {len(stand)} standing cels', flush=True)


def payload(output, record):
    width, height = record['size']
    canvas = record['reference_canvas']; side, x, y = canvas['side'], canvas['x'], canvas['y']
    prompt = (f'Redraw this exact animation cel of Guybrush Threepwood from The Curse of Monkey Island '
              f'as clean, detailed cartoon SVG vector artwork. This is frame {record["cel"]} of an existing '
              'animation: copy the precise pose, expression, facing direction, clothing and original colors. '
              'Use smooth Bezier contours, retain thin dark outlines, eyes, fingers and boot details. '
              'Do not redesign, straighten, re-pose, or complete missing body parts. '
              f'The reference is a square transparent canvas, {side} by {side} design units. '
              f'The original sprite canvas is the rectangle x={x}, y={y}, width={width}, height={height}. '
              'KEEP THE EXACT REFERENCE COMPOSITION AND TRANSPARENT PADDING. Do not center, zoom, '
              'auto-crop, or move the character. Keep ground shadows translucent black. '
              f'The entire SVG viewBox must be "0 0 {side} {side}". '
              'Output only the visible character artwork and its shadow, with empty space transparent. '
              'No background, frame, grid, labels, text or embedded bitmap. This is a faithful vector redraw, '
              'not pixel rectangles or a stylized new design.')
    return dict(model='arrow-2', stream=False, n=1, prompt=prompt,
                instructions='Self-contained SVG with paths, basic shapes, groups and gradients only. No masks, clipPaths, filters, images, fonts, CSS classes or external resources. Match reference silhouette and coordinates exactly.',
                references=[{'base64': base64.b64encode((output / 'references' / record['source']).read_bytes()).decode()}])


def registered_svg(raw, record):
    canvas = record['reference_canvas']; side = canvas['side']
    normalized = ET.fromstring(q.normalize_svg(raw, [side, side]))
    width, height = record['size']
    root = ET.Element(f'{{{q.SVG}}}svg', dict(viewBox=f'0 0 {width} {height}',
                                           width=str(width * 6), height=str(height * 6)))
    group = ET.SubElement(root, f'{{{q.SVG}}}g',
                          dict(transform=f'translate({-canvas["x"]} {-canvas["y"]})'))
    group.extend(normalized)
    return ET.tostring(root, encoding='unicode')


def source_shadow_mask(source, record):
    """Keep ground footprints; partial-alpha edge pixels are not ground shadows."""
    mask = (source[:, :, 3] > 0) & (source[:, :, 3] < 192)
    if record.get('sprite_role') == 'standing_head':
        return np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    mask[:int(height * .75)] = False
    points = set(map(tuple, np.argwhere(mask)))
    result = np.zeros(mask.shape, dtype=bool)
    while points:
        start = points.pop(); group, queue = [start], [start]
        while queue:
            y, x = queue.pop()
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                point = y + dy, x + dx
                if point in points:
                    points.remove(point); group.append(point); queue.append(point)
        if len(group) >= max(3, round(height * width * .001)) and max(y for y, x in group) >= height * .85:
            for y, x in group: result[y, x] = True
    return result


def restore_shadow_alpha(output, raw, record):
    """Correct flattened gray shadow paint, only where the source proves shadow.

    Quiver's vectorization can flatten partial alpha into opaque gray. Preserve
    its generated path geometry and restore the archive's black/128 shadow
    convention. Never treat gray clothing or outlines as a shadow by color alone.
    """
    source = np.array(Image.open(output / 'cleaned' / record['source']).convert('RGBA'))
    shadow = source_shadow_mask(source, record)
    if not shadow.any(): return raw, []
    root = ET.fromstring(raw)
    corrections = []
    diagnostic = output / 'validation' / record['artwork_sha256']
    for index, node in enumerate(root.iter()):
        fill = node.get('fill', '')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', fill): continue
        rgb = [int(fill[i:i + 2], 16) for i in (1, 3, 5)]
        # Arrow sometimes tints flattened shadows slightly (e.g. #858281).
        # Spatial overlap, rather than exact gray, proves this is shadow paint.
        if max(rgb) - min(rgb) > 32 or not 64 <= rgb[0] <= 192: continue
        if float(node.get('opacity', 1)) < .9 or float(node.get('fill-opacity', 1)) < .9: continue
        isolated = copy.deepcopy(root)
        for other_index, other in enumerate(isolated.iter()):
            if other_index != index and other.tag.split('}')[-1] in ('path', 'rect', 'ellipse', 'circle', 'polygon', 'polyline', 'line'):
                other.set('opacity', '0')
        diagnostic.mkdir(parents=True, exist_ok=True)
        svg, png = diagnostic / f'shadow-{index}.svg', diagnostic / f'shadow-{index}.png'
        svg.write_text(registered_svg(ET.tostring(isolated, encoding='unicode'), record))
        subprocess.run(['node', str(q.ROOT / 'tools/quiver_render.mjs'), str(svg), str(png),
                        *map(str, record['size'])], check=True, capture_output=True)
        mask = np.array(Image.open(png).convert('RGBA'))[:, :, 3] >= 128
        # A shadow path can legitimately continue underneath opaque boots; those
        # covered pixels are not evidence of misplaced shadow geometry.
        mask &= source[:, :, 3] < 192
        overlap = int((mask & shadow).sum())
        precision = overlap / max(1, int(mask.sum()))
        coverage = overlap / int(shadow.sum())
        if precision >= .9 and coverage >= .5:
            node.set('fill', '#000000'); node.set('opacity', str(128 / 255))
            corrections.append(dict(type='restore-shadow-alpha', element_index=index,
                                    original_fill=fill, fill='#000000', alpha=128,
                                    source_overlap=precision, source_coverage=coverage))
    return ET.tostring(root, encoding='unicode'), corrections


def validate(output, record):
    key = record['artwork_sha256']
    response = json.loads((output / 'raw' / f'{key}.json').read_text())
    # Sanitize before running either renderer, including during shadow analysis.
    raw = response['data'][0]['svg']
    q.normalize_svg(raw, [record['reference_canvas']['side']] * 2)
    corrected, corrections = restore_shadow_alpha(output, raw, record)
    repairs_file = output / 'repairs.json'
    repair = json.loads(repairs_file.read_text()).get(key) if repairs_file.exists() else None
    if repair:
        if repair.get('raw_sha256') != sha(raw.encode()) or not repair.get('reason'):
            raise ValueError('Reviewed SVG repair does not match this provider response')
        root = ET.fromstring(corrected)
        nodes = list(root.iter())
        for index in repair.get('remove_elements', []):
            node = nodes[index]
            parent = next(parent for parent in root.iter() if node in list(parent))
            parent.remove(node)
        for edit in repair.get('elements', []):
            node = nodes[edit['index']]
            for attr, value in edit.get('attributes', {}).items():
                if attr not in ('fill', 'stroke', 'stroke-width', 'transform', 'd', 'opacity'):
                    raise ValueError('Unsupported reviewed SVG attribute repair')
                node.set(attr, str(value))
        for patch in reversed(repair.get('underlays', [])):
            root.insert(1, ET.Element(f'{{{q.SVG}}}path', patch))
        corrected = ET.tostring(root, encoding='unicode')
        q.normalize_svg(corrected, [record['reference_canvas']['side']] * 2)
        corrections.append(dict(type='reviewed-vector-repair', **repair))
    registered = registered_svg(corrected, record)
    calibration_file = output / 'calibration.json'
    calibration = json.loads(calibration_file.read_text()).get(key) if calibration_file.exists() else None
    if calibration:
        scale, x, y = [float(calibration[k]) for k in ('scale', 'x', 'y')]
        if not .95 <= scale <= 1.05 or max(abs(x), abs(y)) > 5 or not calibration.get('reason'):
            raise ValueError('Calibration must be a documented small uniform anchor correction')
        root = ET.fromstring(registered)
        group = ET.Element(f'{{{q.SVG}}}g', dict(transform=f'translate({x} {y}) scale({scale})'))
        group.extend(list(root)); root[:] = [group]
        registered = ET.tostring(root, encoding='unicode')
        corrections.append(dict(type='reviewed-anchor-calibration', **calibration))
    if repair and repair.get('overlays_original'):
        root = ET.fromstring(registered)
        for shape in repair['overlays_original']:
            tag = 'path' if 'd' in shape else ('ellipse' if 'rx' in shape else 'circle')
            ET.SubElement(root, f'{{{q.SVG}}}{tag}', shape)
        registered = ET.tostring(root, encoding='unicode')
    # Reuse the exact geometry checks and 6x/4x rasterization, retaining the raw
    # provider response unmodified and recording the known padding transform.
    brush_file = output / 'brush-style.json'
    if brush_file.exists():
        from quiver_brush import stylize
        config = json.loads(brush_file.read_text())
        registered, brush_report = stylize(registered, record['size'], config,
                                           q.ROOT / '.context/quiver-native-render')
        corrections.append(brush_report)
    staging = output / 'registered'
    (staging / 'raw').mkdir(parents=True, exist_ok=True)
    if not (staging / 'cleaned').exists(): (staging / 'cleaned').symlink_to((output / 'cleaned').resolve())
    q.atomic(staging / 'raw' / f'{key}.json', {'data': [{'svg': registered}]})
    report = q.validate_one(staging, record)
    # Some provider results omit the ground shadow entirely. Recover only that
    # source alpha mask as vector paths; all visible character artwork remains
    # Quiver-generated. Never insert an embedded bitmap or a traced body.
    source = np.array(Image.open(output / 'cleaned' / record['source']).convert('RGBA'))
    shadow = source_shadow_mask(source, record)
    if shadow.any():
        preview = Image.open(staging / '6x' / f'{key}.png').convert('RGBA').resize(tuple(record['size']), Image.Resampling.LANCZOS)
        rendered = np.array(preview)
        present = (rendered[:, :, 3] > 32) & (rendered[:, :, 3] < 192) & (rendered[:, :, :3].max(axis=2) < 32)
        if float((present & shadow).sum() / shadow.sum()) < .25:
            if not shutil.which('potrace'):
                raise RuntimeError('Install potrace to restore missing source shadows, then validate the cached response')
            bitmap = io.BytesIO()
            Image.fromarray(np.where(shadow, 0, 255).astype('uint8')).convert('1').save(bitmap, format='PPM')
            result = subprocess.run(['potrace', '-s', '--flat', '--turdsize', '0', '--opttolerance', '.15', '-o', '-', '-'],
                                    input=bitmap.getvalue(), capture_output=True, check=True)
            traced = ET.fromstring(result.stdout)
            shadow_group = next(n for n in traced if n.tag.split('}')[-1] == 'g')
            shadow_group.set('fill', '#000000'); shadow_group.set('opacity', str(128 / 255))
            root = ET.fromstring(registered); root.insert(0, shadow_group)
            registered = ET.tostring(root, encoding='unicode')
            q.atomic(staging / 'raw' / f'{key}.json', {'data': [{'svg': registered}]})
            report = q.validate_one(staging, record)
            corrections.append(dict(type='restore-missing-source-shadow',
                                    source_shadow_pixels=int(shadow.sum()), alpha=128,
                                    method='potrace source alpha mask only; no character paths replaced'))
    report['corrections'] = corrections
    for folder in ('svg', '6x', '4x'):
        (output / folder).mkdir(exist_ok=True)
        suffix = '.svg' if folder == 'svg' else '.png'
        shutil.copy2(staging / folder / (key + suffix), output / folder / (key + suffix))
    report['output_hashes'] = {str(p.relative_to(output)): sha(p.read_bytes()) for p in
                             (output / 'svg' / (key + '.svg'), output / '6x' / (key + '.png'), output / '4x' / (key + '.png'))}
    return report


def generate_one(output, record, i, total, operation):
    key = record['artwork_sha256']
    with closing(q.journal(output)) as db:
        state, details = q.job(db, key)
        if state in ('geometry_passed', 'accepted'): return
        if state in ('submitting', 'unknown', 'failed', 'rejected'):
            raise ValueError(f'{key[:12]} is {state}; no automatic resubmission')
        print(f'[{i + 1}/{total}] Quiver Arrow 2: {record["source"]}', flush=True)
        if state != 'downloaded':
            request = payload(output, record)
            endpoint = '/svgs/generations'
            if operation == 'vectorization':
                endpoint = '/svgs/vectorizations'
                request = dict(model='arrow-2', stream=False, auto_crop=False,
                               image=request['references'][0])
            history = details.get('previous_attempts', [])
            details = dict(source=record['source'], model='arrow-2', endpoint=endpoint,
                           prompt=request.get('prompt'), instructions=request.get('instructions'),
                           reference_canvas=record['reference_canvas'], created_at=time.time(),
                           previous_attempts=history)
            q.save_job(db, key, 'submitting', **details)
            try:
                response, request_id = q.request(endpoint, request)
                q.atomic(output / 'raw' / f'{key}.json', response)
                details.update(request_id=request_id, response_id=response.get('id'),
                               usage=response.get('usage'), billing=response.get('billing'))
                q.save_job(db, key, 'downloaded', **details)
            except urllib.error.HTTPError as error:
                details.update(http_status=error.code, request_id=error.headers.get('X-Request-ID') if error.headers else None)
                q.save_job(db, key, 'failed' if error.code < 500 else 'unknown', **details)
                raise RuntimeError(f'Quiver HTTP {error.code}; stopped without retrying') from None
            except Exception as error:
                details['error_type'] = type(error).__name__
                q.save_job(db, key, 'unknown', **details)
                raise RuntimeError('Uncertain generation outcome; no automatic retry') from None
        try:
            report = validate(output, record)
            details['validation'] = report
            q.save_job(db, key, 'geometry_passed' if report['passed'] else 'rejected', **details)
            print(json.dumps(report), flush=True)
            if not report['passed']: raise RuntimeError('Alignment rejected; paid batch stopped')
        except (ValueError, KeyError, IndexError, ET.ParseError) as error:
            details['validation_error'] = str(error)[:200]
            q.save_job(db, key, 'rejected', **details)
            raise RuntimeError('SVG rejected; provider response retained') from None


def generate(output, pilot, workers=2, selected=None):
    manifest = json.loads((output / 'manifest.json').read_text())
    records = {r['artwork_sha256']: r for r in manifest['records']}
    keys = manifest['pilot_keys'] if pilot else list(records)
    if selected:
        if pilot or any(k not in records for k in selected):
            raise ValueError('Selected keys must belong to the walking manifest')
        keys = list(dict.fromkeys(selected))
    walking = set(manifest.get('scope', {}).get('walking_cels', []))
    if not pilot: keys.sort(key=lambda k: (records[k]['cel'] not in walking, records[k]['cel']))
    with closing(q.journal(output)) as db:
        if not pilot and any(q.job(db, k)[0] != 'accepted' for k in manifest['pilot_keys']):
            raise ValueError('Review the walking pilot before submitting the batch')
        # Reject uncertain/error jobs before any further paid submission.
        for key in keys:
            state, _ = q.job(db, key)
            if state in ('submitting', 'unknown', 'failed', 'rejected'):
                raise ValueError(f'{key[:12]} is {state}; no automatic resubmission')
        keys = [k for k in keys if q.job(db, k)[0] not in ('accepted', 'geometry_passed')]
    if not keys: return
    models, _ = q.request('/models')
    q.atomic(output / 'model.json', next(m for m in models['data'] if m['id'] == 'arrow-2'))
    # Bounded concurrency. On any failure, stop new work and let only requests
    # already dispatched settle into the journal. Never cancel an uncertain POST.
    failure = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}; index = 0
        while pending or (index < len(keys) and failure is None):
            while len(pending) < workers and index < len(keys) and failure is None:
                future = pool.submit(generate_one, output, records[keys[index]], index, len(keys), manifest.get('operation'))
                pending[future] = keys[index]; index += 1
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                try: future.result()
                except Exception as error:
                    if failure is None: failure = error
        if failure is not None: raise failure


def retry_rejected(output, keys, reason):
    """Explicitly archive a known completed rejection; never retry uncertainty."""
    if not keys or not reason:
        raise ValueError('retry-rejected requires --key and a reviewed --reason')
    with closing(q.journal(output)) as db:
        for key in keys:
            state, details = q.job(db, key)
            raw = output / 'raw' / (key + '.json')
            if state != 'rejected' or not raw.exists() or not details.get('response_id'):
                raise ValueError('Only a completed, identified rejected response can be retried')
        for key in keys:
            _, details = q.job(db, key)
            history = details.pop('previous_attempts', [])
            archive = output / 'attempts' / key / str(len(history) + 1)
            archive.mkdir(parents=True, exist_ok=True)
            details.update(rejection_reason=reason, archive=str(archive.relative_to(output)))
            q.atomic(archive / 'job.json', details)
            for folder, suffix in [('raw', '.json'), ('svg', '.svg'), ('6x', '.png'), ('4x', '.png')]:
                source = output / folder / (key + suffix)
                if source.exists(): shutil.copy2(source, archive / (folder + suffix))
            q.save_job(db, key, 'retry_ready', previous_attempts=history + [details])


def accept_reviewed(output, keys, eyes_reviewed):
    if not keys or not eyes_reviewed:
        raise ValueError('accept requires --key and --eyes-reviewed after inspecting facial placement')
    q.review(output, keys)
    with closing(q.journal(output)) as db:
        for key in keys:
            state, details = q.job(db, key)
            details['eye_review'] = dict(reviewed_at=time.time(),
                                        svg_sha256=details['validation']['output_hashes']['svg/' + key + '.svg'],
                                        note='Original and SVG eye placement and visibility reviewed; not applicable to body-only parts.')
            q.save_job(db, key, state, **details)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'pilot', 'generate', 'validate', 'accept', 'status', 'install', 'restore', 'retry-rejected'])
    p.add_argument('--output', type=Path, default=OUTPUT)
    p.add_argument('--game', type=Path, default=q.ROOT / '.playtest/game')
    p.add_argument('--hd', type=Path, default=q.ROOT / '.playtest/hd')
    p.add_argument('--key', action='append', default=[])
    p.add_argument('--reason', default='')
    p.add_argument('--eyes-reviewed', action='store_true')
    p.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    p.add_argument('--operation', choices=['generation', 'vectorization'], default='generation',
                   help='Operation recorded at prepare time; existing journals are never reset')
    args = p.parse_args()
    if args.command == 'status':
        q.status(args.output)
        return
    with q.locked(args.output):
        if args.command == 'prepare': prepare(args.output, args.game, operation=args.operation)
        elif args.command == 'retry-rejected': retry_rejected(args.output, args.key, args.reason)
        elif args.command in ('pilot', 'generate'): generate(args.output, args.command == 'pilot', args.workers, args.key)
        elif args.command == 'validate':
            manifest = json.loads((args.output / 'manifest.json').read_text())
            records = {r['artwork_sha256']: r for r in manifest['records']}
            db = q.journal(args.output)
            for key in args.key:
                state, details = q.job(db, key)
                if state not in ('downloaded', 'rejected', 'geometry_passed', 'accepted'):
                    raise ValueError('No cached response available')
                report = validate(args.output, records[key])
                details['validation'] = report
                response = json.loads((args.output / 'raw' / (key + '.json')).read_text())
                details['response_id'] = response.get('id')
                q.save_job(db, key, 'geometry_passed' if report['passed'] else 'rejected', **details)
                print(json.dumps(report), flush=True)
        elif args.command == 'accept': accept_reviewed(args.output, args.key, args.eyes_reviewed)
        else: q.install(args.output, args.hd, args.command == 'restore')


if __name__ == '__main__':
    try: main()
    except (ValueError, RuntimeError) as error: raise SystemExit(str(error))
