"""Rebuild catalog JSON and pre-warm thumbnails.

Runs as a subprocess so NTFS I/O never blocks the server's GIL.
Usage: python _rebuild_catalog.py <root> <store> <catalog_json_path>
"""
import hashlib, io, json, os, re, sys
from pathlib import Path

root = Path(sys.argv[1])
store = Path(sys.argv[2])
catalog_path = Path(sys.argv[3])
THUMB_DIR = Path('/tmp/monkey-thumb-cache')
THUMB_DIR.mkdir(exist_ok=True)

def sha(data):
    return hashlib.sha256(data).hexdigest()

# Load manifest
manifest = root / 'assets' / 'manifest.json'
if not manifest.exists():
    sys.exit(0)

records = json.loads(manifest.read_text(encoding='utf-8-sig'))
review_file = root / 'assets/metadata/artwork-review.json'
reviews = json.loads(review_file.read_text(encoding='utf-8-sig')) if review_file.exists() else {}

# Build frame list
frames = {}
for p, record in records.items():
    if not p.startswith('assets/masters/topaz-4x/'):
        continue
    rel = p
    id_ = sha(rel.encode())[:24]
    stem = Path(p).stem
    match = re.match(r'(.*)_(a?frame)_(\d+)$', stem)
    group = (match.group(1) + '_' + match.group(2)) if match else stem
    index = int(match.group(3)) if match else 0
    category_folder = Path(p).parent.name
    category_map = {'costumes': 'Guybrush · compartido', 'objects': 'Barco · objetos e inventario',
                    'backgrounds': 'Fondos', 'interface': 'Interfaz'}
    category = category_map.get(category_folder, category_folder)
    # Detect scene-specific categories from plan
    plan_path = root / 'assets/metadata/topaz-scene-plan.json'
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
        except:
            plan = {}
    else:
        plan = {}
    frames[id_] = dict(id=id_, path=rel, name=stem, group=category + '/' + group,
                       category=category, number=index)

# Scan edits
edits_dir = store / 'edits'
edit_stats = {}
if edits_dir.is_dir():
    for p in edits_dir.glob('*.png'):
        try:
            st = p.stat()
            edit_stats[p.stem] = (p, st)
        except FileNotFoundError:
            pass

# Build catalog frames with edit info
catalog_frames = []
thumb_jobs = []
for id_, frame in frames.items():
    edit_entry = edit_stats.get(id_)
    if edit_entry:
        path, st = edit_entry
        edited = True
        image_version = f'{st.st_mtime_ns}-{st.st_size}'
    else:
        edited = False
        image_version = 'base'

    if edited:
        meta_path = edits_dir / (id_ + '.json')
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        variant = meta.get('selected_variant') or {}
        revision = meta.get('revision') or sha(path.read_bytes())
    else:
        meta = {}
        variant = {}
        revision = None

    result = dict(frame, edited=edited, revision=revision, thumbnail_version=image_version,
                  edge_cleaned=variant.get('operation') == 'local-alpha' or variant.get('model', '').startswith('Limpieza de borde'),
                  has_reference=False, reference_kind='original')
    catalog_frames.append(result)

    # Queue thumbnail generation
    thumb_path = str(edit_entry[0]) if edit_entry else str(root / frame['path'])
    try:
        st = Path(thumb_path).stat()
        cache_key = hashlib.md5(f'{thumb_path}:{st.st_mtime_ns}:{False}'.encode()).hexdigest()
        if not (THUMB_DIR / (cache_key + '.png')).exists():
            thumb_jobs.append((thumb_path, False, cache_key))
    except FileNotFoundError:
        pass

# Write catalog JSON
result = dict(frames=catalog_frames, root=str(root), store=str(store), cursor=0)
try:
    catalog_path.write_bytes(json.dumps(result, ensure_ascii=False).encode())
except OSError:
    pass

# Generate thumbnails
try:
    from PIL import Image
except ImportError:
    sys.exit(0)

for thumb_path, reference, cache_key in thumb_jobs:
    out = THUMB_DIR / (cache_key + '.png')
    if out.exists():
        continue
    try:
        data = Path(thumb_path).read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert('RGBA')
            image.thumbnail((240, 180), Image.Resampling.NEAREST if reference else Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            image.save(buf, format='PNG')
            out.write_bytes(buf.getvalue())
    except Exception:
        pass
