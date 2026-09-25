#!/usr/bin/env python3
"""Arrow 2 vectorization for an explicit list of sources, under a hard USD ceiling.

Produces review candidates only (SVG plus 4x/6x renders and a comparison sheet); nothing
is installed or packaged. Inputs are the transparency-restored references (local originals
for cels never extracted into the repo); object layers are cropped to their drawn area
and backgrounds use the extracted room image. Requests run one at a time; each is
reserved at a conservative cost before submission, so spending cannot pass the ceiling.
Failed or uncertain requests stop the run and are never retried automatically.

  QUIVERAI_API_KEY=... tools/venv/bin/python tools/quiver_sources.py prepare --output DIR KEY...
  ... generate --output DIR --max-usd 5
  ... status --output DIR / sheet --output DIR
"""
import argparse
import base64
from contextlib import closing
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error

from PIL import Image, ImageDraw
import quiver_cannon as q
from quiver_ui_clip import flatten
from quiver_walk import registered_svg
from scene_sheets import ORIGINALS, checker, drawn_box, fit, font

ROOT = q.ROOT
# Conservative reservations (USD) before each request; replaced by the largest observed cost.
RESERVE = dict(backgrounds=2.0, default=0.5)


def locate(key):
    category, name = key.split('/', 1)
    for path in (ROOT/'assets/references/topaz-cleaned'/key, ROOT/ORIGINALS/'cleaned'/name, ROOT/'extracted'/key):
        if path.exists(): return path
    raise FileNotFoundError(key)


def prepare(output, keys, smooth=False, prompt=None):
    records = []
    for key in keys:
        source = locate(key)
        with Image.open(source) as im:
            image = im.convert('RGBA')
        crop = drawn_box(source) if key.startswith('objects_layers/') else None
        if crop: image = image.crop(crop)
        cleaned = output/'cleaned'/key
        cleaned.parent.mkdir(parents=True, exist_ok=True)
        image.save(cleaned)
        width, height = image.size
        side = max(width, height) + 16
        x, y = (side - width) // 2, (side - height) // 2
        factor = max(1, min(4, 2048 // side))
        square = Image.new('RGBA', (side, side)); square.paste(image, (x, y))
        reference = output/'references'/key
        reference.parent.mkdir(parents=True, exist_ok=True)
        if smooth:
            # Premultiplied LANCZOS gives soft contours to trace instead of the pixel staircase.
            square = square.convert('RGBa').resize((side * factor, side * factor), Image.Resampling.LANCZOS).convert('RGBA')
        else:
            square = square.resize((side * factor, side * factor), Image.Resampling.NEAREST)
        square.save(reference)
        records.append(dict(source=key, input=source.relative_to(ROOT).as_posix(), input_sha256=q.sha(source.read_bytes()),
                            crop=crop, size=[width, height], reference_canvas=dict(side=side, x=x, y=y),
                            reference_factor=factor, smooth=smooth, artwork_sha256=q.sha(cleaned.read_bytes()),
                            opaque=key.startswith('backgrounds/')))
    # A prompt switches to Arrow 2's prompted redraw with the source as reference: smoother,
    # reinterpreted artwork on the same path; geometry is then checked loosely (see loose()).
    manifest = dict(model='arrow-2', operation='generation' if prompt else 'vectorization', records=records)
    if prompt: manifest['prompt'] = prompt
    if (output/'manifest.json').exists() and json.loads((output/'manifest.json').read_text()) != manifest:
        raise ValueError('Manifest changed; use a separate output directory')
    q.atomic(output/'manifest.json', manifest)
    print(f'Prepared {len(records)} sources in {output}')


def rates(output):
    model = output/'model.json'
    return json.loads(model.read_text()).get('billing', {}).get('rates', {}) if model.exists() else {}


def cost(usage, rate):
    return sum((usage or {}).get(f'{kind}_tokens', 0) * rate.get(kind, 0) / 100_000_000_000 for kind in ('input', 'output'))


def spent(db, rate):
    """Recorded cost; submitted-but-unknown requests count at their reservation."""
    total, largest = 0.0, 0.0
    for state, raw in db.execute('SELECT state, details FROM jobs'):
        detail = json.loads(raw)
        value = cost(detail.get('usage'), rate) if detail.get('usage') else detail.get('reserved_usd', 0)
        total += value; largest = max(largest, value)
    return total, largest


def loose(source, rendered):
    """Redraws may soften/reshape strokes: require they stay on and cover the original path."""
    from PIL import ImageFilter
    import numpy as np
    a = np.array(source.convert('RGBA'))[:, :, 3] > 0
    b = np.array(rendered.convert('RGBA').resize(source.size, Image.Resampling.LANCZOS))[:, :, 3] >= 96
    near = lambda m: np.array(Image.fromarray(m.astype('uint8') * 255).filter(ImageFilter.MaxFilter(5))) > 0
    on_path = float((b & near(a)).sum() / max(1, b.sum()))
    covered = float((a & near(b)).sum() / max(1, a.sum()))
    return dict(passed=on_path >= .9 and covered >= .8, on_path=on_path, covered=covered, geometry='loose')


def validate(output, record, generated=False):
    key = record['artwork_sha256']
    raw, corrections = flatten(json.loads((output/'raw'/f'{key}.json').read_text())['data'][0]['svg'])
    staging = output/'registered'
    (staging/'raw').mkdir(parents=True, exist_ok=True)
    if not (staging/'cleaned').exists(): (staging/'cleaned').symlink_to((output/'cleaned').resolve())
    q.atomic(staging/'raw'/f'{key}.json', {'data': [{'svg': registered_svg(raw, record)}]})
    report = q.validate_one(staging, record)
    if generated:
        with Image.open(output/'cleaned'/record['source']) as original, Image.open(staging/'6x'/f'{key}.png') as rendered:
            report.update(loose(original, rendered))
    if record['opaque']:
        # Silhouette checks are meaningless on an opaque room painting; visual review decides.
        report.update(passed=True, geometry='not-applicable-opaque')
    for folder, suffix in (('svg', '.svg'), ('4x', '.png'), ('6x', '.png')):
        (output/folder).mkdir(exist_ok=True)
        shutil.copy2(staging/folder/(key + suffix), output/folder/(key + suffix))
    engine = ROOT/'.playtest/engine/source'
    if record['source'].startswith('costumes/') and engine.exists():
        # Costume SVGs load through the engine's own decoder in exact-frame rooms.
        from quiver_ui import native_renderer
        binary = native_renderer(output)
        size = [v * 4 for v in record['size']]
        with tempfile.TemporaryDirectory(dir=output) as temp:
            rgba = Path(temp)/'render.rgba'
            subprocess.run([str(binary), str(output/'svg'/f'{key}.svg'), str(rgba), *map(str, size)],
                           check=True, capture_output=True)
            native = Image.frombytes('RGBA', tuple(size), rgba.read_bytes())
        (output/'native-4x').mkdir(exist_ok=True); native.save(output/'native-4x'/f'{key}.png')
        with Image.open(output/'cleaned'/record['source']) as original:
            report['native'] = (loose if generated else q.alignment)(original, native)
        report['passed'] = report['passed'] and report['native']['passed']
    elif record['source'].startswith('costumes/'):
        report['native'] = 'not-run: engine source missing'
    report['corrections'] = corrections
    return report


def generate(output, max_usd):
    manifest = json.loads((output/'manifest.json').read_text())
    with closing(q.journal(output)) as db:
        blocked = [r['source'] for r in manifest['records']
                   if q.job(db, r['artwork_sha256'])[0] in ('submitting', 'unknown', 'failed')]
        if blocked: raise ValueError(f'Stopped jobs need review first (no automatic paid retry): {blocked}')
        models, _ = q.request('/models')
        q.atomic(output/'model.json', next(m for m in models['data'] if m['id'] == 'arrow-2'))
        rate = rates(output)
        if not rate: raise RuntimeError('Model rates unavailable; cannot enforce the USD ceiling')
        for record in manifest['records']:
            key = record['artwork_sha256']
            state, details = q.job(db, key)
            if state in ('geometry_passed', 'rejected', 'accepted'): continue
            if state != 'downloaded':
                total, largest = spent(db, rate)
                reserve = max(RESERVE.get(record['source'].split('/')[0], RESERVE['default']), 1.5 * largest)
                if total + reserve > max_usd:
                    print(json.dumps(dict(stopped='usd-ceiling', spent_usd=round(total, 4), next_reserve=reserve,
                                          max_usd=max_usd, next=record['source'])), flush=True)
                    return
                image = base64.b64encode((output/'references'/record['source']).read_bytes()).decode()
                side = record['reference_canvas']['side']
                if 'prompt' in manifest:
                    endpoint = '/svgs/generations'
                    payload = dict(model='arrow-2', stream=False, n=1, references=[{'base64': image}],
                                   prompt=manifest['prompt'].format(side=side),
                                   instructions='Return a self-contained static SVG using vector shapes only. '
                                                'No background rectangle, embedded images, external resources, '
                                                'scripts, fonts or animation.')
                else:
                    endpoint = '/svgs/vectorizations'
                    payload = dict(model='arrow-2', stream=False, auto_crop=False, image={'base64': image})
                details = dict(source=record['source'], model='arrow-2', endpoint=endpoint,
                               created_at=time.time(), reserved_usd=reserve)
                q.save_job(db, key, 'submitting', **details)
                print(f"Arrow 2: {record['source']} (spent ${total:.3f} of ${max_usd})", flush=True)
                try:
                    response, request_id = q.request(endpoint, payload)
                    q.atomic(output/'raw'/f'{key}.json', response)
                    details.update(request_id=request_id, response_id=response.get('id'),
                                   usage=response.get('usage'), billing=response.get('billing'))
                    q.save_job(db, key, 'downloaded', **details)
                except Exception as error:
                    failed = isinstance(error, urllib.error.HTTPError) and error.code < 500
                    q.save_job(db, key, 'failed' if failed else 'unknown', **{**details, 'error_type': type(error).__name__})
                    raise RuntimeError('API request stopped; no automatic retry') from None
            try:
                report = validate(output, record, 'prompt' in manifest)
            except Exception as error:
                q.save_job(db, key, 'rejected', **{**details, 'validation_error': str(error)[:300]})
                print(json.dumps(dict(source=record['source'], rejected=str(error)[:300])), flush=True)
                continue
            q.save_job(db, key, 'geometry_passed' if report['passed'] else 'rejected', **{**details, 'validation': report})
            print(json.dumps(dict(source=record['source'], passed=report['passed'],
                                  iou=round(report.get('silhouette_iou', 0), 3),
                                  on_path=report.get('on_path'), covered=report.get('covered'))), flush=True)
        total, _ = spent(db, rate)
        print(json.dumps(dict(done=True, spent_usd=round(total, 4))), flush=True)


def status(output):
    manifest = json.loads((output/'manifest.json').read_text())
    with closing(q.journal(output)) as db:
        states = {r['source']: q.job(db, r['artwork_sha256'])[0] or 'not_submitted' for r in manifest['records']}
        total, _ = spent(db, rates(output))
    report = dict(counts={s: list(states.values()).count(s) for s in set(states.values())},
                  spent_usd=round(total, 4), sources=states)
    q.atomic(output/'status.json', report)
    print(json.dumps(report, indent=1))


def sheet(output, page=(1280, 896)):
    """Original | Arrow 2 (4x render) pairs, same display size, labelled with source keys."""
    manifest = json.loads((output/'manifest.json').read_text())
    text = font(); tiles = []
    with closing(q.journal(output)) as db:
        for r in manifest['records']:
            state = q.job(db, r['artwork_sha256'])[0] or 'not_submitted'
            render = output/'4x'/f"{r['artwork_sha256']}.png"
            tiles.append((r, state, render if render.exists() else None))
    panel = (180, 180)
    width, height = 2 * panel[0] + 8, panel[1] + 18
    cols = (page[0] - 12) // (width + 6)
    rows = max(1, (page[1] - 12) // (height + 6))
    pages = [tiles[i:i + cols * rows] for i in range(0, len(tiles), cols * rows)]
    for n, items in enumerate(pages, 1):
        sheet = Image.new('RGB', page, (38, 42, 46)); draw = ImageDraw.Draw(sheet)
        for i, (r, state, render) in enumerate(items):
            x, y = 6 + (i % cols) * (width + 6), 6 + (i // cols) * (height + 6)
            label = f"{Path(r['source']).stem} [{state}]"
            while draw.textlength(label, font=text) > width: label = label[:-1]
            draw.text((x, y), label, fill=(235, 235, 235), font=text)
            shown = None
            for j, path in enumerate((output/'cleaned'/r['source'], render)):
                px = x + j * (panel[0] + 8); sheet.paste(checker(panel), (px, y + 16))
                if path is None: continue
                with Image.open(path) as im:
                    im = im.convert('RGBA')
                    im = fit(im, panel, pixel_art=True) if j == 0 else im.resize(shown, Image.Resampling.LANCZOS)
                if j == 0: shown = im.size
                sheet.paste(im, (px + (panel[0] - im.width) // 2, y + 16 + (panel[1] - im.height) // 2), im)
        sheet.save(output/f'sheet-{n:02}.png')
        print(output/f'sheet-{n:02}.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('prepare', 'generate', 'status', 'sheet'))
    parser.add_argument('keys', nargs='*', help="source keys such as costumes/LFLF_0009_AKOS_0032_frame_0.png")
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-usd', type=float)
    parser.add_argument('--prompt', help='prepare: use prompted redraw; {side} is the square canvas size')
    parser.add_argument('--smooth', action='store_true', help='prepare: smooth (LANCZOS) instead of pixel enlargement')
    args = parser.parse_intermixed_args()
    with q.locked(args.output):
        if args.command == 'prepare': prepare(args.output, args.keys, args.smooth, args.prompt)
        elif args.command == 'generate':
            if not args.max_usd or args.max_usd <= 0: parser.error('generate needs a positive --max-usd')
            generate(args.output, args.max_usd)
        elif args.command == 'status': status(args.output)
        else: sheet(args.output)


if __name__ == '__main__':
    main()
