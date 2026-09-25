#!/usr/bin/env python3
"""Pack one scene's artwork into labelled review sheets with an exact file index.

Sheets are local review aids under .context/, never runtime atlases: the engine,
manifest and installer keep using one PNG per frame/state. Every tile has a short
ID (C3.17 = costume 3, frame 17; O4.1 = object 4, state 1; L = object layer;
B = background) that index.json maps back to its source and master paths and
SHA-256 hashes. index.md summarises each group in a few lines of text.

Pages stay within ~1.15 megapixels so an image viewer reads them without
downscaling. A sheet is not a review record: record reviews per file.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
VERSION = 1
MAX_PIXELS = 1_150_000
MAX_EDGE = 1568
CATEGORIES = ('characters', 'objects', 'layers', 'backgrounds')
PREFIX = dict(characters='C', objects='O', layers='L', backgrounds='B')
# Panel size (per image) for each category; compare tiles hold two panels.
PANELS = dict(characters=(64, 104), objects=(88, 88), layers=(128, 96), backgrounds=(600, 450))
MARGIN, GAP, LABEL, HEADER = 6, 4, 13, 16
PAGE_BG, TEXT = (38, 42, 46), (235, 235, 235)
BORDER = dict(accepted=(80, 200, 110), validated=(80, 200, 110), rejected=(225, 70, 70),
              missing=(120, 120, 120))
COSTUME_DIRS = ('extracted/costumes', 'assets/references/topaz-cleaned/costumes',
                'assets/masters/topaz-4x/costumes', 'assets/masters/ui-4x/costumes')
FRAME = re.compile(r'_frame_(\d+)\.png$')
STATE = re.compile(r'^(\d{4})_(.+)_(\d{4})\.png$')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def rel(root, path):
    return path.relative_to(root).as_posix()


def font(size=11):
    try: return ImageFont.load_default(size=size)
    except (TypeError, OSError): return ImageFont.load_default()


def load_scene(root, key):
    """Find a scene by UUID, name or room number."""
    matches = []
    for path in sorted((root/'data/scenes').glob('*.json')):
        data = json.loads(path.read_text())
        s = data['scene']
        if key in (s['id'], s['name']) or (key.isdigit() and int(key) == s.get('roomNumber')):
            matches.append(data)
    if not matches: raise SystemExit(f'No scene matches {key!r}')
    if len(matches) > 1:
        raise SystemExit(f'{key!r} matches several scenes; use the UUID: ' +
                         ', '.join(f"{m['scene']['id']} ({m['scene']['name']})" for m in matches))
    return matches[0]


class Library:
    """Manifest hashes/statuses and artwork-review states, read once."""
    def __init__(self, root):
        self.root = root
        manifest = root/'assets/manifest.json'
        files = json.loads(manifest.read_text())['files'] if manifest.exists() else []
        self.records = {f['path']: f for f in files}
        self.backgrounds = {f['asset_id']: f['path'] for f in files
                            if f.get('canonical') and str(f.get('asset_id', '')).startswith('background-room-')}
        review = root/'assets/metadata/artwork-review.json'
        self.review = json.loads(review.read_text()) if review.exists() else {}
        self.derived = {}
        for f in files:
            if f.get('derived_from'): self.derived.setdefault(f['derived_from'], []).append(f['path'])

    def master(self, category, name):
        # Only exact-name matches: UI masters use engine aframe numbers, which are
        # not extracted frame numbers, so guessing would give a wrong reference.
        for folder in ('topaz-4x', 'ui-4x'):
            path = self.root/'assets/masters'/folder/category/name
            if path.exists(): return path

    def describe(self, path, review_key=None):
        if path is None or not path.exists(): return None
        p = rel(self.root, path)
        sha = digest(path)
        record = self.records.get(p, {})
        info = dict(path=p, sha256=sha, review_status=record.get('review_status'))
        if record and record.get('sha256') != sha: info['manifest_sha256'] = record.get('sha256')
        runtime = sorted(self.derived.get(p, []))
        if runtime:
            # Installed copies exported from this master (manifest derived_from).
            info['runtime'] = [dict(path=r, sha256=digest(self.root/r) if (self.root/r).exists() else None)
                               for r in runtime]
        if review_key in self.review:
            r = self.review[review_key]
            info['review_state'] = r.get('state')
            if r.get('sha256') and r['sha256'] != sha: info['review_sha256'] = r['sha256']
        return info


def state_of(tile):
    master = tile['master']
    if not master: return 'missing'
    return master.get('review_state') or master.get('review_status') or 'unknown'


def drawn_box(path):
    """Bounding box of drawn pixels: alpha if present, else pixels unlike a uniform corner colour."""
    with Image.open(path) as f: im = f.copy()
    if im.mode == 'RGBA' or 'transparency' in im.info:
        box = im.convert('RGBA').getchannel('A').getbbox()
    else:
        # Compare palette indices, not colours: the placeholder index may share a colour with paint.
        im = Image.frombytes('L', im.size, im.tobytes()) if im.mode == 'P' else im.convert('RGB')
        corners = {im.getpixel(p) for p in ((0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1))}
        if len(corners) != 1: return None
        box = ImageChops.difference(im, Image.new(im.mode, im.size, corners.pop())).getbbox()
    if not box or box == (0, 0, im.width, im.height): return None
    return [max(0, box[0] - 2), max(0, box[1] - 2), min(im.width, box[2] + 2), min(im.height, box[3] + 2)]


ORIGINALS = '.context/scene-sheets/originals'
LOOKS = ('extracted', 'assets/references/topaz-cleaned', 'assets/masters/topaz-4x', 'assets/masters/ui-4x')


def load_scope(path, room):
    """Source keys ('costumes/…png') that must appear: a plain list, {'sources': [...]},
    or the scene-focus audit report (scenes[room].assets[].source)."""
    if not path: return set()
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and 'scenes' in data:
        return {a['source'] for a in data['scenes'][str(room)]['assets']}
    return set(data['sources'] if isinstance(data, dict) else data)


def collect(root, scene, library, categories, frame_step=1, max_frames=0, masters_only=False, scope=()):
    """Return groups: [{id, category, name, tiles: [...], ...}] in display order."""
    assets = scene['assets'].values() if isinstance(scene['assets'], dict) else scene['assets']
    by_type = {t: sorted((a for a in assets if a['type'] == t), key=lambda a: a['name'])
               for t in ('character', 'object', 'background')}
    room = scene['scene'].get('roomNumber')
    originals = root/ORIGINALS
    groups = []

    def tile(tile_id, category, folder, name, crop=None):
        # Originals missing from extracted/ may exist in the local (ignored) originals pool.
        source = next((p for p in (root/'extracted'/folder/name, originals/'indexed'/name) if p.exists()), None)
        reference = next((p for p in (root/'assets/references/topaz-cleaned'/folder/name, originals/'cleaned'/name)
                          if p.exists()), None)
        master = library.master(folder, name)
        key = f'{folder}/{name}'
        t = dict(id=tile_id, category=category, key=key, source=library.describe(source),
                 reference=library.describe(reference), master=library.describe(master, key), review_command=None)
        if crop: t['crop'] = crop
        if master is not None:
            t['review_command'] = f'tools/venv/bin/python tools/topaz_scenes.py review --source {key}'
        legacy = root/'assets/runtime'/folder/name.replace('_frame_', '_aframe_')
        base = reference or source
        if legacy.exists() and base is not None:
            # The older default pack names costume cels aframe_N; link only exact 4x copies.
            with Image.open(legacy) as a, Image.open(base) as b:
                if a.size == (b.width * 4, b.height * 4): t['legacy_runtime'] = library.describe(legacy)
        t['state'] = state_of(t)
        return t

    if 'characters' in categories:
        listed = [a['metadata'].get('akosId') or a['name'] for a in by_type['character']]
        wanted = {FRAME.split(Path(k).name)[0] for k in scope if k.startswith('costumes/')}
        # Costumes stored in this room's LFLF but missing from the scene data, plus scope costumes
        # (e.g. shared Guybrush), are included and flagged.
        prefixed = {FRAME.split(p.name)[0] for folder in COSTUME_DIRS[1:] + (ORIGINALS + '/indexed',)
                    for p in (root/folder).glob(f'LFLF_{room or 0:04}_AKOS_*_frame_*.png')} if room is not None else set()
        extra = sorted((prefixed | wanted) - set(listed))
        frame_no = lambda name: int(FRAME.search(name).group(1))
        for n, akos in enumerate(listed + extra, 1):
            # A frame counts if any copy exists or the scope names it, so nothing is dropped.
            names = {p.name for folder in COSTUME_DIRS + (ORIGINALS + '/indexed', ORIGINALS + '/cleaned')
                     for p in (root/folder).glob(f'{akos}_frame_*.png')}
            names |= {Path(k).name for k in scope if Path(k).name.startswith(akos + '_frame_')}
            names = sorted(names, key=frame_no)
            shown = names[::frame_step]
            if max_frames: shown = shown[:max_frames]
            skipped = [frame_no(f) for f in names if f not in set(shown)]
            gid = f'C{n}'
            group = dict(id=gid, category='characters', name=akos, frames_total=len(names), skipped_frames=skipped,
                         tiles=[tile(f'{gid}.{frame_no(f)}', 'characters', 'costumes', f) for f in shown])
            if akos in extra: group['not_in_scene_data'] = True
            groups.append(group)

    in_scene, names = set(), {}
    for asset in by_type['object']:
        f = Path(asset['originalPath']).name
        if STATE.match(f): in_scene.add(f)
    # Room-prefixed files in any object folder count too, and objects/layers share one
    # numbering (O4 and L4 are the same object) so they stay easy to pair.
    found = set(in_scene) | {Path(k).name for k in scope if k.startswith(('objects/', 'objects_layers/'))}
    if room is not None:
        found |= {p.name for base in LOOKS for folder in ('objects', 'objects_layers')
                  for p in (root/base/folder).glob(f'{room:04}_*.png')}
    for f in found:
        m = STATE.match(f)
        if not m: continue
        label = m.group(2) if room is not None and int(m.group(1)) == room else f'{m.group(1)} {m.group(2)}'
        names.setdefault(label, set()).add(f)

    def objects(category, folder):
        for n, (name, files) in enumerate(sorted(names.items(), key=lambda kv: (' ' in kv[0], kv[0])), 1):
            gid = f'{PREFIX[category]}{n}'
            tiles = []
            for f in sorted(files):
                if f'{folder}/{f}' not in scope and not any((root/base/folder/f).exists() for base in LOOKS):
                    continue
                # Layers are full-room canvases; show the drawn area only.
                reference = root/'assets/references/topaz-cleaned'/folder/f
                shown = reference if reference.exists() else root/'extracted'/folder/f
                crop = drawn_box(shown) if category == 'layers' and shown.exists() else None
                tiles.append(tile(f'{gid}.{int(STATE.match(f).group(3))}', category, folder, f, crop))
            if tiles:
                group = dict(id=gid, category=category, name=name, tiles=tiles)
                if not files & in_scene: group['not_in_scene_data'] = True
                groups.append(group)

    if 'objects' in categories: objects('objects', 'objects')
    if 'layers' in categories: objects('layers', 'objects_layers')
    if 'backgrounds' in categories:
        for n, asset in enumerate(by_type['background'], 1):
            source = root/asset['originalPath']
            bg_room = asset['metadata'].get('roomNumber', room)
            master = library.backgrounds.get(f'background-room-{bg_room}')
            t = dict(id=f'B{n}', category='backgrounds', key=f'backgrounds/{source.name}',
                     source=library.describe(source), reference=None,
                     master=library.describe(root/master if master else None), review_command=None)
            t['state'] = state_of(t)
            groups.append(dict(id=f'B{n}', category='backgrounds', name=source.stem, tiles=[t]))
    if masters_only:
        for g in groups:
            g['omitted_no_master'] = [t['id'] for t in g['tiles'] if t['master'] is None]
            g['tiles'] = [t for t in g['tiles'] if t['master'] is not None]
        groups = [g for g in groups if g['tiles']]
    return groups


def fit(image, box, pixel_art):
    """Scale an image into box; source pixel art uses whole-number nearest scaling."""
    w, h = image.size
    scale = min(box[0] / w, box[1] / h)
    if pixel_art and scale >= 1: scale = int(scale)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    method = Image.Resampling.NEAREST if pixel_art and scale >= 1 else Image.Resampling.LANCZOS
    return image.resize(size, method)


BACKDROPS = dict(checker=None, light=(235, 235, 228), dark=(24, 24, 28))


def checker(size, backdrop='checker', cell=8):
    if BACKDROPS[backdrop]: return Image.new('RGB', size, BACKDROPS[backdrop])
    board = Image.new('RGB', size, (200, 200, 200))
    draw = ImageDraw.Draw(board)
    for y in range(0, size[1], cell):
        for x in range((y // cell) % 2 * cell, size[0], cell * 2):
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(150, 150, 150))
    return board


def open_rgba(root, info, crop=None, scale=1):
    if not info: return None
    try:
        with Image.open(root/info['path']) as f: im = f.convert('RGBA')
    except OSError:
        return None
    if crop: im = im.crop(tuple(round(v * scale) for v in crop))
    return im


def render_tile(root, t, mode, panel, text_font, backdrop='checker'):
    panels = 2 if mode == 'compare' else 1
    width = panels * panel[0] + (panels - 1) * GAP + 4
    tile = Image.new('RGB', (width, LABEL + panel[1] + 4), PAGE_BG)
    draw = ImageDraw.Draw(tile)
    border = BORDER.get(t['state'], (215, 180, 60))
    draw.rectangle((0, LABEL, width - 1, LABEL + panel[1] + 3), outline=border, width=2)
    label = t['id'] if t['category'] == 'characters' else f"{t['id']} {t.get('group_name', '')}"
    while label and draw.textlength(label, font=text_font) > width: label = label[:-1]
    draw.text((1, 0), label, fill=TEXT, font=text_font)
    # The extracted PNGs are opaque; the cleaned reference restores palette transparency.
    source = open_rgba(root, t['reference'] or t['source'], t.get('crop'))
    scale = 1
    master = None
    if mode != 'source' and t['master']:
        master_full = open_rgba(root, t['master'])
        if master_full is not None and source is not None:
            with Image.open(root/(t['reference'] or t['source'])['path']) as raw: scale = master_full.width / raw.width
            master = master_full.crop(tuple(round(v * scale) for v in t['crop'])) if t.get('crop') else master_full
        else:
            master = master_full
    images = dict(source=[source], master=[master], compare=[source, master])[mode]
    shown = None
    for i, im in enumerate(images):
        x, y = 2 + i * (panel[0] + GAP), LABEL + 2
        tile.paste(checker(panel, backdrop), (x, y))
        if im is None:
            draw.text((x + 3, y + 3), 'no master' if i or mode == 'master' else 'no source',
                      fill=(170, 30, 30), font=text_font)
            continue
        if i == 1 and shown is not None:
            # Same displayed size as the source so the pair is directly comparable.
            im = im.resize(shown, Image.Resampling.LANCZOS)
        else:
            im = fit(im, panel, pixel_art=(i == 0 and mode != 'master'))
            shown = im.size
        tile.paste(im, (x + (panel[0] - im.width) // 2, y + (panel[1] - im.height) // 2), im)
    return tile


def page_size(width, height):
    if max(width, height) > MAX_EDGE or width * height > MAX_PIXELS:
        raise SystemExit(f'Page {width}x{height} would be downscaled by image viewers '
                         f'(max edge {MAX_EDGE}, max {MAX_PIXELS} pixels)')
    return width, height


def layout(groups, category, tile_size, page):
    """Place tiles on pages. Characters start one row per costume; others flow inline."""
    pages, y = [[]], MARGIN
    cols = max(1, (page[0] - 2 * MARGIN + GAP) // (tile_size[0] + GAP))
    if tile_size[0] + 2 * MARGIN > page[0] or tile_size[1] + HEADER + 2 * MARGIN > page[1]:
        raise SystemExit(f'{category} tiles do not fit on a {page[0]}x{page[1]} page')
    rows = [(g['id'] + ' ' + g['name'], g['tiles']) for g in groups] if category == 'characters' else \
        [(category.capitalize() + ' (names in index.md)', [t for g in groups for t in g['tiles']])]
    for title, tiles in rows:
        i, first = 0, True
        while i < len(tiles):
            if y + HEADER + tile_size[1] > page[1] - MARGIN:
                pages.append([]); y = MARGIN
            pages[-1].append(('header', title + ('' if first else ' (cont.)'), (MARGIN, y)))
            y += HEADER
            while i < len(tiles) and y + tile_size[1] <= page[1] - MARGIN:
                for k, t in enumerate(tiles[i:i + cols]):
                    pages[-1].append(('tile', t, (MARGIN + k * (tile_size[0] + GAP), y)))
                i += cols; y += tile_size[1] + GAP
            first = False
        y += 2
    return [p for p in pages if p]


def fingerprint(groups, mode, page):
    # Every tile field (hashes, crop, review state) and every skipped frame affects the render.
    data = [VERSION, mode, page, [{k: v for k, v in g.items() if k != 'tiles'} for g in groups],
            [t for g in groups for t in g['tiles']]]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def ranges(numbers, limit=None):
    """Compress numbers to 1-3,7; past limit runs, only a count (full lists stay in index.json)."""
    numbers, out = sorted(numbers), []
    for n in numbers:
        if out and n == out[-1][1] + 1: out[-1][1] = n
        else: out.append([n, n])
    if limit and len(out) > limit: return f'{len(numbers)} scattered'
    return ','.join(str(a) if a == b else f'{a}-{b}' for a, b in out)


def summary(groups, category, pages, tiles):
    listed = ', '.join(pages) if len(pages) <= 3 else f'{pages[0]} … {pages[-1]}'
    lines = [f"## {category}: {listed}"]
    for g in groups:
        numbers = sorted({int(tiles[t['id']]['page'].rsplit('-', 1)[1][:-4]) for t in g['tiles']})
        states = Counter(t['state'] for t in g['tiles'])
        nums = [int(t['id'].split('.')[1]) for t in g['tiles'] if '.' in t['id']]
        line = f"- **{g['id']}** {g['name']} (p{ranges(numbers)})"
        if g.get('not_in_scene_data'): line += ' [not in scene data]'
        if category == 'characters':
            line += f" frames {ranges(nums, 6)} ({len(g['tiles'])}/{g['frames_total']})"
            if g['skipped_frames']: line += f", skipped {ranges(g['skipped_frames'], 6)}"
        elif nums:
            line += f" states {ranges(nums)}"
        line += ' — ' + ', '.join(f'{k} {v}' for k, v in sorted(states.items()))
        for state in ('rejected', 'missing'):
            flagged = [int(t['id'].split('.')[1]) for t in g['tiles'] if '.' in t['id'] and t['state'] == state]
            if flagged and len(flagged) < len(g['tiles']): line += f"; {state}: {ranges(flagged, 6)}"
        if g.get('omitted_no_master'):
            omitted = [int(i.split('.')[1]) for i in g['omitted_no_master'] if '.' in i]
            line += f"; omitted without master: {ranges(omitted, 6) or len(g['omitted_no_master'])}"
        mismatch = sum(1 for t in g['tiles'] for side in ('source', 'reference', 'master') if t[side] and
                       ('manifest_sha256' in t[side] or 'review_sha256' in t[side]))
        if mismatch: line += f"; {mismatch} file(s) differ from manifest/review hash"
        lines.append(line)
    return lines


SCAN = ('extracted', 'assets/masters', 'assets/references', 'assets/runtime', 'upscaled', 'previews')


def coverage(root, room, index):
    """Files named for this room (or its background master) that no tile references."""
    if room is None: return []
    pattern = re.compile(rf'(^|_)LFLF_{room:04}_|^{room:04}_|^bg_{room:04}\b')
    referenced = set()
    for t in index['tiles'].values():
        for side in ('source', 'reference', 'master', 'legacy_runtime'):
            if t.get(side):
                referenced.add(t[side]['path'])
                referenced.update(r['path'] for r in t[side].get('runtime', []))
    referenced |= {p + '.stamp' for p in referenced}
    found = {rel(root, p) for folder in SCAN if (root/folder).exists()
             for p in (root/folder).rglob('*') if p.is_file() and pattern.search(p.name)}
    return sorted(found - referenced)


def markdown(index):
    s = index['scene']
    lines = [f"# {s['name']} (room {s['room']}) — {index['mode']} sheets on {index['backdrop']}", '',
             'Tile border: green validated/accepted, red rejected, grey no master, amber other.',
             'Left panel: transparency-restored reference when one exists, else the opaque extracted original; '
             'right panel: canonical master.',
             f"Details for any tile or group: `python3 tools/scene_sheets.py lookup {s['room'] or s['id']} ID`",
             "Counts marked 'scattered' are listed in full by lookup on the group ID.", '']
    for category in CATEGORIES:
        if category in index['sheets']: lines += index['sheets'][category]['summary'] + ['']
    counts = Counter(side for t in index['tiles'].values() for side in ('source', 'reference', 'master') if t.get(side))
    counts['runtime'] = sum(len(t[side].get('runtime', [])) for t in index['tiles'].values()
                            for side in ('source', 'master') if t.get(side))
    counts['legacy runtime'] = sum(1 for t in index['tiles'].values() if t.get('legacy_runtime'))
    lines.append(f"## Coverage: {len(index['tiles'])} tiles; " + ', '.join(
        f'{counts[k]} {k}' for k in ('source', 'reference', 'master', 'runtime', 'legacy runtime')) + ' files referenced')
    no_files = [t['key'] for t in index['tiles'].values() if not (t['source'] or t['reference'] or t['master'])]
    if no_files: lines.append(f"Tiles with no file anywhere (native cel not extracted): {len(no_files)}")
    scope = index.get('scope') or {}
    if scope.get('file'):
        lines.append(f"Scope {scope['file']}: {scope['sources']} sources, {len(scope['not_on_sheets'])} not on sheets"
                     + ''.join(f'\n- {k}' for k in scope['not_on_sheets'][:20]))
    missing = index.get('unreferenced', [])
    lines.append(f"Room files not on any sheet: {len(missing)} (full list in index.json `unreferenced`)")
    if len(missing) <= 20: lines += [f'- {p}' for p in missing]
    else:
        grouped = Counter(re.sub(r'_(a?frame)_\d+\.png$', r'_\1_*.png', p) for p in missing)
        lines += [f'- {p} ({n})' for p, n in sorted(grouped.items())]
    return '\n'.join(lines)


def build(root, scene, mode='compare', categories=CATEGORIES, output=None, frame_step=1, max_frames=0,
          page=(1280, 896), force=False, masters_only=False, backdrop='checker', scope=None):
    page = page_size(*page)
    s = scene['scene']
    output = output or root/'.context/scene-sheets'
    folder = output/f"{s.get('roomNumber', 0):04}-{s['name']}"/(mode if backdrop == 'checker' else f'{mode}-{backdrop}')
    folder.mkdir(parents=True, exist_ok=True)
    library = Library(root)
    wanted = load_scope(scope, s.get('roomNumber'))
    groups = collect(root, scene, library, categories, frame_step, max_frames, masters_only, wanted)
    for g in groups:
        for t in g['tiles']: t['group_name'] = g['name']
    index_path = folder/'index.json'
    previous = json.loads(index_path.read_text()) if index_path.exists() else {}
    index = dict(version=VERSION, scene=dict(id=s['id'], name=s['name'], room=s.get('roomNumber')),
                 mode=mode, backdrop=backdrop, sheets={}, groups={}, tiles={})
    if previous.get('version') == VERSION:
        # Keep categories that this run did not rebuild.
        keep = lambda v: v['category'] not in categories
        index['sheets'] = {k: v for k, v in previous['sheets'].items() if k not in categories}
        index['groups'] = {k: v for k, v in previous['groups'].items() if keep(v)}
        index['tiles'] = {k: v for k, v in previous['tiles'].items() if keep(v)}
    text_font = font()
    built = []
    for category in categories:
        members = [g for g in groups if g['category'] == category]
        if not members: continue
        key = fingerprint(members, mode, list(page) + [backdrop])
        old = previous.get('sheets', {}).get(category, {})
        panels = 2 if mode == 'compare' else 1
        panel = PANELS[category]
        if category == 'backgrounds':
            # Shrink the 4:3 panel to fit smaller pages.
            ph = min(panel[1], (page[0] - 2 * MARGIN - 4 - (panels - 1) * GAP) // panels * 3 // 4,
                     page[1] - 2 * MARGIN - HEADER - LABEL - 4)
            panel = (ph * 4 // 3, ph)
        tile_size = (panels * panel[0] + (panels - 1) * GAP + 4, LABEL + panel[1] + 4)
        pages = layout(members, category, tile_size, page)
        names = [f'{category}-{n:02}.png' for n in range(1, len(pages) + 1)]
        reuse = not force and old.get('fingerprint') == key and all((folder/n).exists() for n in names)
        if not reuse:
            for stale in folder.glob(f'{category}-*.png'): stale.unlink()
        for name, items in zip(names, pages):
            sheet = None if reuse else Image.new('RGB', page, PAGE_BG)
            draw = None if reuse else ImageDraw.Draw(sheet)
            for kind, item, (x, y) in items:
                if kind == 'header':
                    if draw: draw.text((x, y + 2), item, fill=TEXT, font=text_font)
                    continue
                if sheet: sheet.paste(render_tile(root, item, mode, panel, text_font, backdrop), (x, y))
                index['tiles'][item['id']] = dict(
                    {k: v for k, v in item.items() if k not in ('id', 'group_name')},
                    group=item['id'].split('.')[0], page=name,
                    bbox=[x, y, x + tile_size[0], y + tile_size[1]])
            if sheet: sheet.save(folder/name, optimize=True)
        index['sheets'][category] = dict(fingerprint=key, page=list(page), pages=names, reused=reuse,
                                         summary=summary(members, category, names, index['tiles']))
        built.append((category, names, reuse))
    for g in groups:
        index['groups'][g['id']] = {k: v for k, v in g.items() if k not in ('id', 'tiles')}
        index['groups'][g['id']]['tiles'] = len(g['tiles'])
    if set(categories) == set(CATEGORIES) and not masters_only and frame_step == 1 and not max_frames:
        index['unreferenced'] = coverage(root, s.get('roomNumber'), index)
        # Scope sources are keyed by category/name; each must be a tile (with or without files).
        shown = {t.get('key') for t in index['tiles'].values()}
        index['scope'] = dict(file=str(scope) if scope else None, sources=len(wanted),
                              not_on_sheets=sorted(wanted - shown))
    else:
        index['unreferenced'] = previous.get('unreferenced', [])
        index['scope'] = previous.get('scope')
    index_path.write_text(json.dumps(index, indent=1) + '\n')
    (folder/'index.md').write_text(markdown(index) + '\n')
    return folder, built, index


def parse_ids(values):
    """Accept IDs like C3.17 and ranges like C3.10-14."""
    out = []
    for value in values:
        m = re.fullmatch(r'([A-Z]\d+)\.(\d+)-(\d+)', value)
        out += [f'{m.group(1)}.{n}' for n in range(int(m.group(2)), int(m.group(3)) + 1)] if m else [value]
    return out


def lookup(root, scene, ids, mode='compare', output=None):
    s = scene['scene']
    output = output or root/'.context/scene-sheets'
    scene_dir = output/f"{s.get('roomNumber', 0):04}-{s['name']}"
    # Paths and hashes are identical across modes/backdrops; only page and bbox differ.
    candidates = [scene_dir/mode/'index.json'] + sorted(scene_dir.glob('*/index.json'))
    index_path = next((f for f in candidates if f.exists()), None)
    if not index_path: raise SystemExit('No sheets for this scene yet; run build first')
    index = json.loads(index_path.read_text())
    found = {}
    for tile_id in parse_ids(ids):
        if tile_id in index['tiles']: found[tile_id] = index['tiles'][tile_id]
        elif tile_id in index['groups']:
            found[tile_id] = dict(index['groups'][tile_id], tile_ids=sorted(
                (k for k in index['tiles'] if k.split('.')[0] == tile_id),
                key=lambda k: int(k.split('.')[1]) if '.' in k else 0))
        else: raise SystemExit(f'{tile_id} is not in {index_path.relative_to(root)}')
    return found


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build', help='render sheets and indexes for one scene or all scenes')
    b.add_argument('--scene', help='scene UUID, name or room number')
    b.add_argument('--all', action='store_true')
    b.add_argument('--mode', choices=('compare', 'source', 'master'), default='compare')
    b.add_argument('--category', action='append', choices=CATEGORIES,
                   help='limit to these categories (repeatable); default all')
    b.add_argument('--frame-step', type=int, default=1, help='show every Nth costume frame')
    b.add_argument('--max-frames', type=int, default=0, help='cap frames shown per costume (0 = all)')
    b.add_argument('--backdrop', choices=tuple(BACKDROPS), default='checker',
                   help='panel background; light/dark pages go to <mode>-<backdrop>/')
    b.add_argument('--scope', type=Path, help='JSON of source keys that must appear (list, {"sources": [...]}, '
                   'or .context/scene-focus/coverage.json)')
    b.add_argument('--masters-only', action='store_true',
                   help='omit tiles that have no master (listed per group in the index)')
    b.add_argument('--page', default='1280x896', help='page size WxH (max ~1.15 MP)')
    b.add_argument('--output', type=Path)
    b.add_argument('--force', action='store_true', help='re-render even if inputs are unchanged')
    l = sub.add_parser('lookup', help='print paths, hashes and review command for tiles or groups')
    l.add_argument('scene')
    l.add_argument('ids', nargs='+', help='tile IDs (C3.17, C3.10-14) or group IDs (C3)')
    l.add_argument('--mode', choices=('compare', 'source', 'master'), default='compare')
    l.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.command == 'lookup':
        print(json.dumps(lookup(ROOT, load_scene(ROOT, args.scene), args.ids, args.mode, args.output), indent=1))
        return
    if args.frame_step < 1 or args.max_frames < 0: p.error('--frame-step must be >= 1 and --max-frames >= 0')
    if bool(args.scene) == args.all: p.error('Pass --scene or --all')
    page = tuple(int(v) for v in args.page.lower().split('x'))
    scenes = [json.loads(f.read_text()) for f in sorted((ROOT/'data/scenes').glob('*.json'))] if args.all \
        else [load_scene(ROOT, args.scene)]
    for scene in scenes:
        folder, built, index = build(ROOT, scene, args.mode, tuple(args.category or CATEGORIES), args.output,
                                     args.frame_step, args.max_frames, page, args.force, args.masters_only,
                                     args.backdrop, args.scope)
        count = sum(len(names) for _, names, _ in built)
        print(f"{rel(ROOT, folder) if folder.is_relative_to(ROOT) else folder}: {len(index['tiles'])} tiles on "
              f"{count} page(s), ~{count * page[0] * page[1] // 750} image tokens if all are viewed")
        for category, names, reuse in built:
            print(f"  {category}: {len(names)} page(s){' (unchanged, reused)' if reuse else ''}")


if __name__ == '__main__':
    sys.exit(main())
