"""Local, dependency-free sprite painting workspace. Python 3.11+."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time
import webbrowser
import zlib
import urllib.request
import io
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from imagelab import ImageLab
from live_updates import ChangeFeed

PNG = b'\x89PNG\r\n\x1a\n'
MAX_BODY = 48 * 1024 * 1024


_THUMB_DIR = Path('/tmp/monkey-thumb-cache')
_THUMB_DIR.mkdir(exist_ok=True)
_IMG_CACHE_DIR = Path('/tmp/monkey-img-cache')
_IMG_CACHE_DIR.mkdir(exist_ok=True)

def _cached_read(path):
    """Read file bytes, caching small files on ext4 /tmp to avoid repeated slow NTFS reads."""
    p = Path(path)
    try:
        stat = p.stat()
    except FileNotFoundError:
        raise
    # Skip disk cache for large files (>200KB) to avoid filling WSL2 storage
    if stat.st_size > 200_000:
        return p.read_bytes()
    cache_key = hashlib.md5(f'{path}:{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()
    cached = _IMG_CACHE_DIR / cache_key
    try:
        return cached.read_bytes()
    except FileNotFoundError:
        pass
    data = p.read_bytes()
    try:
        cached.write_bytes(data)
    except OSError:
        pass
    return data

def thumbnail(path, modified, reference):
    cache_key = hashlib.md5(f'{path}:{modified}:{reference}'.encode()).hexdigest()
    cached = _THUMB_DIR / (cache_key + '.png')
    try:
        return cached.read_bytes()
    except FileNotFoundError:
        pass
    data = _cached_read(path)
    png_size(data)
    try:
        from PIL import Image
    except ImportError:
        return data
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert('RGBA')
        image.thumbnail((240, 180), Image.Resampling.NEAREST if reference else Image.Resampling.LANCZOS)
        result = io.BytesIO(); image.save(result, format='PNG')
        out = result.getvalue()
    try:
        cached.write_bytes(out)
    except OSError:
        pass
    return out


_VERSION_THUMB_DIR = Path('/tmp/monkey-version-thumbs')
_VERSION_THUMB_DIR.mkdir(exist_ok=True)

def version_thumb(data, cache_key):
    """Return a small thumbnail PNG for a version image, cached on disk."""
    cached = _VERSION_THUMB_DIR / (cache_key + '.png')
    try:
        return cached.read_bytes()
    except FileNotFoundError:
        pass
    try:
        from PIL import Image
    except ImportError:
        return data
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert('RGBA')
        image.thumbnail((128, 112), Image.Resampling.LANCZOS)
        result = io.BytesIO(); image.save(result, format='PNG')
        out = result.getvalue()
    try:
        cached.write_bytes(out)
    except OSError:
        pass
    return out


def png_size(data):
    """Validate the container, CRCs and dimensions before storing user data."""
    if not data.startswith(PNG):
        raise ValueError('No es un PNG real. Puede ser un puntero de Git LFS.')
    pos, size, ended, has_data = 8, None, False, False
    while pos + 12 <= len(data):
        n = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + n
        if end > len(data):
            raise ValueError('PNG incompleto.')
        body = data[pos + 8:pos + 8 + n]
        crc = struct.unpack('>I', data[pos + 8 + n:end])[0]
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError('PNG dañado: checksum incorrecto.')
        if pos == 8:
            if kind != b'IHDR' or n != 13:
                raise ValueError('Falta la cabecera PNG.')
            size = struct.unpack('>II', body[:8])
            if min(size) < 1 or max(size) > 16384 or size[0] * size[1] > 16_000_000:
                raise ValueError('El límite es 16 millones de píxeles por cuadro.')
        if kind == b'IDAT':
            has_data = True
        if kind == b'IEND':
            ended = end == len(data) and n == 0
            break
        pos = end
    if not ended or not has_data:
        raise ValueError('PNG incompleto.')
    return size


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + secrets.token_hex(5) + '.tmp')
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Conflict(Exception):
    pass


class Workshop:
    def __init__(self, root):
        self.root = root.resolve()
        self.store = self.root / '.context' / 'sprite-painter'
        self.frames = {}
        self.catalog_cache = {}
        self._full_catalog_cache = None
        self._catalog_json_path = Path('/tmp/monkey-catalog.json')
        self._history_cache = {}
        self._open_cache = {}
        self.lock = threading.RLock()
        self.changes = ChangeFeed()
        self.reload()
        # Build catalog in background thread
        threading.Thread(target=self._prebuild_all, daemon=True).start()

    def _prebuild_all(self):
        """Load catalog from /tmp snapshot, then rebuild in a SUBPROCESS (no GIL)."""
        try:
            self.full_catalog()
        except Exception:
            pass
        # Rebuild catalog + thumbnails in a subprocess so NTFS I/O never blocks HTTP
        self._subprocess_rebuild()

    def full_catalog(self):
        with self.lock:
            if self._full_catalog_cache is not None:
                return self._full_catalog_cache
        # Load from /tmp snapshot (instant)
        try:
            data = self._catalog_json_path.read_bytes()
            result = json.loads(data)
            cached_ids = {f['id'] for f in result.get('frames', [])}
            if cached_ids == set(self.frames.keys()) and result.get('root') == str(self.root):
                with self.lock:
                    self._full_catalog_cache = result
                return result
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        # No snapshot — must build synchronously (only on very first run)
        return self._rebuild_catalog()

    def _rebuild_catalog(self):
        edit_cache = self._scan_edits()
        cursor = self.changes.cursor()
        frames = [self.catalog_frame(id_, _edit_cache=edit_cache) for id_ in list(self.frames)]
        result = dict(frames=frames, root=str(self.root), store=str(self.store), cursor=cursor)
        with self.lock:
            self._full_catalog_cache = result
        try:
            self._catalog_json_path.write_bytes(json.dumps(result, ensure_ascii=False).encode())
        except OSError:
            pass
        return result

    def _subprocess_rebuild(self):
        """Rebuild catalog + thumbnails in a subprocess. Zero GIL impact."""
        script = str(Path(__file__).parent / '_rebuild_catalog.py')
        try:
            proc = subprocess.Popen(
                [sys.executable, script, str(self.root), str(self.store), str(self._catalog_json_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            # Watch for completion in a lightweight thread (no NTFS I/O)
            def watch():
                proc.wait()
                try:
                    data = self._catalog_json_path.read_bytes()
                    result = json.loads(data)
                    with self.lock:
                        self._full_catalog_cache = result
                except Exception:
                    pass
            threading.Thread(target=watch, daemon=True).start()
        except OSError:
            pass

    def invalidate_catalog(self):
        with self.lock:
            self._full_catalog_cache = None

    def register(self, path, category, name=None, dimensions=None):
        if '..' in path.parts:
            path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Ruta fuera del proyecto.')
        relative = path.relative_to(self.root).as_posix()
        id_ = sha(relative.encode())[:24]
        stem = name or path.stem
        match = re.match(r'(.*)_(a?frame)_(\d+)$', stem)
        group = (match.group(1) + '_' + match.group(2)) if match else stem
        index = int(match.group(3)) if match else 0
        self.frames[id_] = dict(id=id_, path=relative, name=stem,
                               group=category + '/' + group, category=category,
                               number=index, dimensions=dimensions)
        self.catalog_cache.pop(id_,None);self._open_cache.pop(id_,None);self._full_catalog_cache=None
        return id_

    def reload(self):
        with self.lock:
            self.reference.cache_clear()
            self.catalog_cache.clear();self._full_catalog_cache=None
            self._reference_index = None
            self.frames = {}
            manifest = self.root / 'assets' / 'manifest.json'
            review_file = self.root / 'assets/metadata/artwork-review.json'
            reviews = json.loads(review_file.read_text(encoding='utf-8-sig')) if review_file.exists() else {}
            plan_path=self.root/'assets/metadata/topaz-scene-plan.json'
            scene_sources=set()
            if plan_path.exists():
                plan=json.loads(plan_path.read_text(encoding='utf-8-sig'))
                scene_sources={entry['source'] for scene in plan.get('scenes',[]) if scene['id'] in ('room-0009','room-0010','room-0011') for entry in scene['sources']}
            if manifest.exists():
                records = json.loads(manifest.read_text(encoding='utf-8-sig')).get('files', [])
                for record in records:
                    p = record['path']
                    if not p.lower().endswith('.png'):
                        continue
                    category = None
                    if p.startswith('assets/masters/topaz-4x/costumes/'):
                        if 'LFLF_0009_' in p: category = 'Barco · personajes'
                        elif 'LFLF_0001_AKOS_0002_' in p: category = 'Guybrush · compartido'
                        elif 'LFLF_0011_' in p: category = 'Agua · personajes'
                    elif p.startswith('assets/masters/topaz-4x/objects/') and re.search(r'/000[39]_', p):
                        category = 'Barco · objetos e inventario'
                    elif p.startswith('assets/masters/backgrounds/') and record.get('asset_id') in ('background-room-9', 'background-room-11'):
                        category = 'Fondos'
                    elif p.startswith('assets/masters/ui-4x/'):
                        category = 'Interfaz'
                    elif p.startswith('extracted/costumes/') and ('LFLF_0009_' in p or 'LFLF_0001_AKOS_0002_' in p):
                        category = 'Originales · referencia'
                    if not category and record.get('canonical') and (record.get('source_id') in scene_sources or record.get('asset_id')=='background-room-10'):
                        category='Entrega · dependencias del barco'
                    if category:
                        d = record.get('image', {})
                        frame_id = self.register(self.root / p, category,
                                      dimensions=[d['width'], d['height']] if 'width' in d else None)
                        key = p.removeprefix('assets/masters/topaz-4x/')
                        review = reviews.get(key)
                        if review:
                            valid = review.get('sha256') == record.get('sha256') and bool(record.get('sha256'))
                            self.frames[frame_id]['review'] = dict(state=review.get('state'), current=valid, sha256=review.get('sha256'),
                                note=review.get('note', ''), validation=review.get('validation', {}),
                                validation_passed=review.get('validation_passed'))
            imports = self.store / 'imports'
            if imports.exists():
                for p in sorted(imports.glob('*/*.png')):
                    self.register(p, 'Importados · ' + p.parent.name)
            self._build_reference_index()

    def frame(self, id_):
        if id_ not in self.frames:
            raise ValueError('Recurso desconocido.')
        return self.frames[id_]

    def draft(self, id_):
        self.frame(id_)
        return self.store / 'edits' / (id_ + '.png')

    def original(self, id_):
        p = (self.root / self.frame(id_)['path']).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError('Ruta fuera del proyecto.')
        return p

    def _build_reference_index(self):
        """Scan reference directories once to avoid per-frame is_file() calls."""
        if self._reference_index is not None:
            return
        index = {}
        for folder in ('assets/references/topaz-cleaned', 'extracted'):
            base = self.root / folder
            if base.is_dir():
                for p in base.rglob('*.png'):
                    key = p.relative_to(base).as_posix()
                    if key not in index:
                        index[key] = p
        self._reference_index = index

    @lru_cache(maxsize=4096)
    def reference(self, id_):
        relative = self.frame(id_)['path']
        prefix = next((p for p in ('assets/masters/topaz-4x/', 'assets/masters/ui-4x/') if relative.startswith(p)), None)
        if prefix is None:
            return None
        self._build_reference_index()
        suffix = relative.removeprefix(prefix)
        candidate = self._reference_index.get(suffix)
        if candidate is not None:
            return candidate
        # Fallback for files created after index was built
        for folder in ('assets/references/topaz-cleaned', 'extracted'):
            path = (self.root / folder / suffix)
            if '..' not in path.parts:
                path = path.resolve()
            if path.is_relative_to(self.root) and path.is_file():
                return path
        return None

    def revision(self, id_):
        p = self.draft(id_)
        if not p.exists():
            return None
        # Include metadata so concurrent alignment-only edits also conflict.
        return self.metadata(id_).get('revision') or sha(p.read_bytes())

    def generation_reference(self, id_):
        from source_preparation import reference
        return reference(self, id_)

    def metadata(self, id_):
        p = self.store / 'edits' / (id_ + '.json')
        return json.loads(p.read_text()) if p.exists() else {}

    def _scan_edits(self):
        """Pre-scan the edits directory once, returning dicts keyed by id."""
        edits_dir = self.store / 'edits'
        stats = {}
        if edits_dir.is_dir():
            for p in edits_dir.glob('*.png'):
                stem = p.stem
                try:
                    st = p.stat()
                    stats[stem] = (p, st)
                except FileNotFoundError:
                    pass
        return stats

    def catalog_frame(self, id_, _edit_cache=None):
        with self.lock:
            frame=self.frame(id_)
            # Fast path: check if this frame has an edit via pre-scanned cache
            if _edit_cache is not None:
                edit_entry = _edit_cache.get(id_)
                if edit_entry:
                    path, stat = edit_entry; edited = True
                    image_version = f'{stat.st_mtime_ns}-{stat.st_size}'
                else:
                    edited = False; image_version = 'base'
            else:
                draft=self.draft(id_)
                try:
                    stat=draft.stat();edited=True;path=draft
                    image_version=f'{stat.st_mtime_ns}-{stat.st_size}'
                except FileNotFoundError:
                    edited=False;image_version='base'
            stamp=(edited,image_version)
            cached=self.catalog_cache.get(id_)
            if cached and cached[0]==stamp:return dict(cached[1])
            if edited:
                meta=self.metadata(id_)
                variant=meta.get('selected_variant') or {}
                revision=meta.get('revision') or sha(path.read_bytes())
            else:
                meta={};variant={};revision=None
            ref=self.reference(id_)
            result=dict(frame,edited=edited,revision=revision,thumbnail_version=image_version,
                edge_cleaned=variant.get('operation')=='local-alpha' or variant.get('model','').startswith('Limpieza de borde'),
                has_reference=ref is not None,reference_kind='original-preparado' if ref and 'topaz-cleaned' in ref.parts else 'original')
            self.catalog_cache[id_]=(stamp,result)
            return dict(result)

    def history_names(self, id_):
        """Return sorted history PNG names, cached to avoid repeated NTFS globs."""
        folder = self.store / 'history' / id_
        try:
            mtime = folder.stat().st_mtime_ns
        except FileNotFoundError:
            self._history_cache.pop(id_, None)
            return []
        cached = self._history_cache.get(id_)
        if cached and cached[0] == mtime:
            return cached[1]
        names = sorted((p.name for p in folder.glob('*.png')), reverse=True)
        self._history_cache[id_] = (mtime, names)
        return names

    def invalidate_history(self, id_):
        self._history_cache.pop(id_, None)

    def open(self, id_):
        from source_preparation import metadata
        with self.lock:
            draft = self.draft(id_)
            try:
                draft_stat = draft.stat()
                draft_key = f'{draft_stat.st_mtime_ns}-{draft_stat.st_size}'
            except FileNotFoundError:
                draft_key = 'none'
            cache_key = f'{id_}:{draft_key}'
            cached = self._open_cache.get(id_)
            if cached and cached[0] == cache_key:
                return dict(cached[1])
            original = _cached_read(self.original(id_))
            size = png_size(original)
            revision = self.revision(id_)
            meta = self.metadata(id_)
            result = dict(frame=self.frame(id_), width=size[0], height=size[1],
                        revision=revision, offset=meta.get('offset', [0, 0]),
                        current_sha256=meta.get('sha256') if revision else sha(original),
                        selected_variant=meta.get('selected_variant'),
                        source_preparation=metadata(self,id_),
                        original=f'/api/image?id={id_}&original=1',
                        image=f'/api/image?id={id_}&v={revision or "base"}')
            self._open_cache[id_] = (cache_key, result)
            return dict(result)

    def save(self, body, selected_variant=None):
        id_ = body['id']
        encoded = body['png']
        if not encoded.startswith('data:image/png;base64,'):
            raise ValueError('Formato no admitido.')
        image = base64.b64decode(encoded.split(',', 1)[1], validate=True)
        size = png_size(image)
        with self.lock:
            if self.revision(id_) != body.get('revision'):
                raise Conflict('Otra ventana guardó este cuadro. Exportá tu PNG y recargá antes de continuar.')
            original = self.original(id_).read_bytes()
            if png_size(original) != size:
                raise ValueError('El retoque debe conservar las dimensiones originales.')
            offset = body.get('offset', [0, 0])
            if not isinstance(offset, list) or len(offset) != 2 or any(type(x) not in (int, float) or not -16384 <= x <= 16384 for x in offset):
                raise ValueError('Offset inválido.')
            previous = self.draft(id_)
            stamp = str(time.time_ns())
            revision = sha(image + json.dumps(offset).encode() + stamp.encode())
            history = self.store / 'history' / id_
            prior = previous.read_bytes() if previous.exists() else original
            atomic(history / (stamp + '-before.png'), prior)
            atomic(history / (stamp + '-before.json'), json.dumps(self.metadata(id_)).encode())
            self.invalidate_history(id_)
            meta = dict(source=self.frame(id_)['path'], source_sha256=sha(original),
                        sha256=sha(image), revision=revision, saved_at=time.time(), offset=offset,
                        width=size[0], height=size[1], review_status='manual-draft',
                        note='Offset de comparación, no modifica coordenadas del juego.')
            previous_meta=self.metadata(id_)
            if selected_variant:
                meta['selected_variant']=selected_variant
            elif previous_meta.get('sha256')==sha(image) and previous_meta.get('selected_variant'):
                meta['selected_variant']=previous_meta['selected_variant']
            atomic(previous, image)
            atomic(previous.with_suffix('.json'), json.dumps(meta, indent=2).encode())
            if self.frame(id_)['name'].startswith('0003_') and self.frame(id_)['name'].endswith('_0000'):
                from inventory_states import sync
                sync(self,id_)
            self.catalog_cache.pop(id_,None);self._open_cache.pop(id_,None);self._full_catalog_cache=None
            self.changes.publish(id_)
            return dict(revision=revision, saved=str(previous), offset=offset)

    def delete_history(self, body):
        id_ = body['id']; self.frame(id_)
        name = body['name']
        if not isinstance(name, str) or not re.fullmatch(r'\d+-before\.png', name):
            raise ValueError('Versión inválida.')
        with self.lock:
            path = self.store / 'history' / id_ / name
            path.unlink(missing_ok=True)
            path.with_suffix('.json').unlink(missing_ok=True)
            self.invalidate_history(id_)
            self.changes.publish(id_)
            return dict(ok=True)

    def restore(self, body):
        id_ = body['id']; self.frame(id_)
        name = body['name']
        if not isinstance(name, str) or not re.fullmatch(r'\d+-before\.png', name):
            raise ValueError('Versión inválida.')
        with self.lock:
            path = self.store / 'history' / id_ / name
            meta = json.loads(path.with_suffix('.json').read_text()) if path.with_suffix('.json').exists() else {}
            return self.save(dict(id=id_, revision=body.get('revision'),
                png='data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode(),
                offset=meta.get('offset', [0, 0])), selected_variant=meta.get('selected_variant'))

    def import_png(self, body):
        name = re.sub(r'[^\w. -]', '_', str(body.get('name', 'sprite.png')))
        if not name.lower().endswith('.png'): raise ValueError('Importá archivos PNG.')
        session = re.sub(r'[^a-zA-Z0-9_-]', '', str(body.get('batch', 'manual')))[:64] or 'manual'
        encoded = body['png']
        if not encoded.startswith('data:image/png;base64,'): raise ValueError('Formato no admitido.')
        data = base64.b64decode(encoded.split(',', 1)[1], validate=True)
        size = png_size(data)
        path = self.store / 'imports' / session / name
        with self.lock:
            if path.exists() and path.read_bytes() != data:
                raise Conflict('Ya existe un PNG distinto con ese nombre en este lote.')
            atomic(path, data)
            id_=self.register(path, 'Importados · ' + session, dimensions=list(size))
            self.changes.publish(id_)
            return dict(id=id_)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, value, mime='application/json', cache_control='no-store'):
        data = json.dumps(value, ensure_ascii=False).encode() if mime == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', cache_control)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def stream_changes(self):
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Cache-Control','no-cache')
        self.send_header('Connection','close')
        self.end_headers()
        cursor=self.headers.get('Last-Event-ID')
        try:
            self.wfile.write(b'retry: 1000\n\n');self.wfile.flush()
            while True:
                change=self.server.workshop.changes.read(cursor)
                if change:
                    cursor=change['cursor']
                    packet=f'id: {cursor}\nevent: change\ndata: {json.dumps(change)}\n\n'.encode()
                else:packet=b': keepalive\n\n'
                self.wfile.write(packet);self.wfile.flush()
        except (BrokenPipeError,ConnectionError,OSError):
            pass
        self.close_connection=True

    def trusted(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected:
            raise ValueError('Usá la dirección local indicada por el lanzador.')
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + expected:
            raise ValueError('Origen no admitido.')

    def do_GET(self):
        try:
            self.trusted()
            parsed = urlparse(self.path)
            args = parse_qs(parsed.query)
            w = self.server.workshop
            if parsed.path == '/api/health':
                self.send(200, dict(app='monkey-sprite-painter', root=str(w.root)))
            elif parsed.path == '/api/events':
                # Retire per-tab streams from already-open old clients. HTTP 204
                # tells EventSource to stop reconnecting; their fallback stays usable.
                if args.get('shared')==['1']: self.stream_changes()
                else:self.send(204,b'','text/event-stream')
            elif parsed.path == '/api/changes':
                self.send(200,w.changes.read(args.get('since',[None])[0],0) or dict(cursor=w.changes.cursor(),ids=[]))
            elif parsed.path == '/api/source-preparation':
                from source_preparation import snapshot
                self.send(200,snapshot(w,args['id'][0]))
            elif parsed.path == '/api/source-image':
                path=w.generation_reference(args['id'][0])
                if path is None: raise ValueError('No hay original asociado.')
                self.send(200,_cached_read(path),'image/png')
            elif parsed.path == '/api/review':
                asset=args['id'][0];lab=self.server.imagelab
                with lab.lock,w.lock:
                    result=dict(info=w.open(asset),jobs=lab.list(asset),
                        history=dict(items=w.history_names(asset)),
                        approvals={asset:lab.approvals().get(asset)})
                self.send(200,result)
            elif parsed.path == '/api/live-state':
                ids=list(dict.fromkeys(args.get('ids',[''])[0].split(','))) if 'ids' in args else list(w.frames)
                for id_ in ids:w.frame(id_)
                lab=self.server.imagelab
                # Same lock order as accepting a variant; never publish a half-saved image.
                with lab.lock,w.lock:
                    approvals=lab.approvals()
                    jobs=lab.list(assets=ids)
                    wanted=set(ids)
                    changed=w.changes.read(args['since'][0],0) if 'since' in args and 'ids' not in args else None
                    frame_ids=ids
                    if 'since' in args and 'ids' not in args and not (changed and changed.get('reset')):
                        frame_ids=[id_ for id_ in (changed or {}).get('ids',[]) if id_ in wanted]
                    snapshot=dict(ids=ids,full='ids' not in args,
                        cursor=w.changes.cursor(),frames=[w.catalog_frame(id_) for id_ in frame_ids],
                        approvals={id_:approvals.get(id_) for id_ in ids},
                        jobs=[job for job in jobs if job['asset_id'] in wanted])
                self.send(200,snapshot)
            elif parsed.path == '/api/imagelab/status':
                self.send(200, self.server.imagelab.status())
            elif parsed.path == '/api/deliveries':
                self.send(200,self.server.deliveries.snapshot())
            elif parsed.path == '/api/imagelab/jobs':
                asset=args.get('asset',[None])[0];approvals=self.server.imagelab.approvals()
                ids=args.get('ids',[''])[0].split(',') if 'ids' in args else None
                self.send(200, dict(jobs=self.server.imagelab.list(asset,assets=ids),approvals={asset:approvals.get(asset)} if asset else approvals))
            elif parsed.path == '/api/imagelab/job':
                self.send(200, self.server.imagelab.read(args['id'][0]))
            elif parsed.path == '/api/imagelab/image':
                folder=self.server.imagelab.folder(args['id'][0])
                name='input.png' if 'input' in args else ('provider.png' if 'raw' in args else 'candidate.png')
                if 'input' in args and (folder/'alpha-source.png').exists():
                    name='alpha-source.png'
                self.send(200, _cached_read(folder/name), 'image/png', 'private, max-age=300')
            elif parsed.path == '/api/imagelab/reference':
                asset=args['id'][0];w.frame(asset);approval=self.server.imagelab.approvals().get(asset)
                path=self.server.imagelab.root/'references'/approval['file'] if approval else w.original(asset)
                self.send(200,path.read_bytes(),'image/png')
            elif parsed.path == '/api/imagelab/prepared':
                from PIL import Image
                from spriteprep import clean_base
                path=w.generation_reference(args['id'][0])
                if not path: raise ValueError('No hay original asociado.')
                with Image.open(path) as original:
                    original=original.convert('RGBA');factor=896/max(original.size)
                    width,height=max(1,round(original.width*factor)),max(1,round(original.height*factor))
                    prepared=Image.new('RGBA',(1024,1024),(128,128,128,255))
                    prepared.alpha_composite(clean_base(original,(width,height)),((1024-width)//2,(1024-height)//2))
                    buffer=io.BytesIO();prepared.save(buffer,format='PNG')
                self.send(200,buffer.getvalue(),'image/png')
            elif parsed.path == '/api/asset-audit':
                self.send(200,self.server.audit.snapshot())
            elif parsed.path == '/api/catalog':
                self.send(200, w.full_catalog())
            elif parsed.path == '/api/thumbnail':
                id_ = args['id'][0]
                reference = args.get('reference', ['0'])[0] == '1'
                with w.lock:
                    if reference:
                        path = w.reference(id_)
                    else:
                        draft = w.draft(id_)
                        path = draft if draft.exists() else (w.root / w.frame(id_)['path'])
                    if path is None: return self.send(404, dict(error='No hay un original asociado por nombre exacto.'))
                try:
                    stat=path.stat();version=f'{stat.st_mtime_ns}-{stat.st_size}'
                except FileNotFoundError:
                    return self.send(404, dict(error='Archivo no disponible.'))
                cache_control='private, max-age=31536000, immutable' if args.get('v',[''])[0]==version else 'no-store'
                data=thumbnail(str(path), stat.st_mtime_ns, reference)
                self.send(200,data,'image/png',cache_control)
            elif parsed.path == '/api/open':
                self.send(200, w.open(args['id'][0]))
            elif parsed.path == '/api/image':
                id_ = args['id'][0]
                p = w.original(id_) if 'original' in args or not w.draft(id_).exists() else w.draft(id_)
                data = _cached_read(p)
                png_size(data)
                v = args.get('v', [''])[0]
                cc = 'private, max-age=300' if v and v != 'base' else 'no-store'
                self.send(200, data, 'image/png', cc)
            elif parsed.path == '/api/reference':
                reference=w.reference(args['id'][0])
                if reference is None: return self.send(404, dict(error='No hay original asociado a este asset.'))
                data=_cached_read(reference);png_size(data)
                self.send(200, data, 'image/png')
            elif parsed.path == '/api/history':
                id_ = args['id'][0]; w.frame(id_)
                self.send(200, dict(items=w.history_names(id_)))
            elif parsed.path == '/api/version':
                id_ = args['id'][0]; w.frame(id_)
                name = args['name'][0]
                if not re.fullmatch(r'\d+-before\.png', name): raise ValueError('Versión inválida.')
                data = _cached_read(w.store / 'history' / id_ / name)
                self.send(200, data, 'image/png')
            elif parsed.path == '/api/version-thumb':
                kind = args.get('kind', [''])[0]
                if kind == 'job':
                    job_id = args['job'][0]
                    folder = self.server.imagelab.folder(job_id)
                    path = folder / 'candidate.png'
                    data = _cached_read(path)
                    key = hashlib.md5(f'job:{job_id}:{path.stat().st_mtime_ns}'.encode()).hexdigest()
                elif kind == 'history':
                    id_ = args['id'][0]; w.frame(id_)
                    name = args['name'][0]
                    if not re.fullmatch(r'\d+-before\.png', name): raise ValueError('Versión inválida.')
                    path = w.store / 'history' / id_ / name
                    data = _cached_read(path)
                    key = hashlib.md5(f'history:{id_}:{name}:{path.stat().st_mtime_ns}'.encode()).hexdigest()
                elif kind == 'current':
                    id_ = args['id'][0]
                    draft = w.draft(id_)
                    path = draft if draft.exists() else (w.root / w.frame(id_)['path'])
                    data = _cached_read(path)
                    key = hashlib.md5(f'current:{id_}:{path.stat().st_mtime_ns}'.encode()).hexdigest()
                else:
                    raise ValueError('Tipo de versión inválido.')
                self.send(200, version_thumb(data, key), 'image/png', 'private, max-age=300')
            elif parsed.path == '/confite/':
                self.send(200, (Path(__file__).parent / 'confite' / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            elif parsed.path in ('/source-preparation.js','/live-worker.js'):
                self.send(200,(Path(__file__).parent/parsed.path[1:]).read_bytes(),'text/javascript; charset=utf-8')
            elif parsed.path in ('/', '/app.js', '/style.css', '/confite-link.js', '/confite-workshop.css', '/workshop-theme.css', '/asset-browser.js', '/imagelab-ui.js', '/asset-review.js', '/review-ui.js', '/lucide-icons.json', '/deliveries-ui.js', '/live-assets.js', '/sequence-tools.js'):
                names = {'/': ('index.html', 'text/html; charset=utf-8'),
                         '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                         '/confite-link.js': ('confite-link.js', 'text/javascript; charset=utf-8'),
                         '/confite-workshop.css': ('confite-workshop.css', 'text/css; charset=utf-8'),
                         '/workshop-theme.css': ('workshop-theme.css', 'text/css; charset=utf-8'),
                         '/asset-browser.js': ('asset-browser.js', 'text/javascript; charset=utf-8'),
                         '/asset-review.js': ('asset-review.js', 'text/javascript; charset=utf-8'),
                         '/review-ui.js': ('review-ui.js', 'text/javascript; charset=utf-8'),
                         '/lucide-icons.json': ('lucide-icons.json', 'application/json; charset=utf-8'),
                         '/deliveries-ui.js': ('deliveries-ui.js', 'text/javascript; charset=utf-8'),
                         '/imagelab-ui.js': ('imagelab-ui.js', 'text/javascript; charset=utf-8'),
                         '/live-assets.js': ('live-assets.js', 'text/javascript; charset=utf-8'),
                         '/sequence-tools.js': ('sequence-tools.js', 'text/javascript; charset=utf-8'),
                         '/style.css': ('style.css', 'text/css; charset=utf-8')}
                name, mime = names[parsed.path]
                self.send(200, (Path(__file__).parent / name).read_bytes(), mime)
            elif parsed.path == '/api/preview/alpha':
                from alpha_cleanup import clean, outline as make_outline, remove_magenta, _parse_color
                from PIL import Image
                id_=args['id'][0]
                trim=float(args.get('trim',['0.5'])[0])
                tint=float(args.get('tint',['0'])[0])
                dark=args.get('dark',['1'])[0]=='1'
                seams=args.get('seams',['1'])[0]=='1'
                magenta=args.get('magenta',['0'])[0]=='1'
                ol=args.get('outline',[None])[0]
                job_id=args.get('job_id',[None])[0]
                history=args.get('history',[None])[0]
                with w.lock:
                    source_body={'id':id_}
                    if job_id:source_body['job_id']=job_id
                    elif history:source_body['history']=history
                    else:source_body['revision']=w.revision(id_)
                    source_data=self.server.imagelab.variant_source(source_body)
                    ref=w.reference(id_) if seams else None
                    ref_img=Image.open(ref).convert('RGBA') if ref else None
                img=Image.open(io.BytesIO(source_data)).convert('RGBA')
                if ol:
                    ol_color=_parse_color(args.get('outline_color',[None])[0],ol)
                    ol_radius=max(1,min(int(args.get('outline_radius',['2'])[0]),8))
                    result=make_outline(img,ol_color,ol_radius)
                else:
                    if magenta:img=remove_magenta(img)
                    result=clean(img,trim,dark,tint,ref_img,seams and ref_img is not None)
                if ref_img:ref_img.close()
                buf=io.BytesIO();result.save(buf,format='PNG')
                self.send(200,buf.getvalue(),'image/png')
            else: self.send(404, dict(error='No encontrado.'))
        except (ValueError, KeyError, FileNotFoundError) as error:
            self.send(400, dict(error=str(error)))
        except Exception as exc:
            import traceback; traceback.print_exc()
            self.send(500, dict(error=f'Error interno: {type(exc).__name__}: {exc}'))

    def do_POST(self):
        try:
            self.trusted()
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY: raise ValueError('Archivo demasiado grande.')
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                raise ValueError('Formato de petición inválido.')
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/save': result = self.server.workshop.save(body)
            elif self.path == '/api/source-preparation':
                from source_preparation import save
                result=save(self.server.workshop,body)
            elif self.path == '/api/deliveries/prepare': result = self.server.deliveries.start(body.get('scope','complete'),body.get('ids'))
            elif self.path == '/api/deliveries/pull-request': result = self.server.deliveries.start_pr(body['id'],body.get('title'),body.get('draft',False))
            elif self.path == '/api/deliveries/branch': result = self.server.deliveries.branch(body['id'],body.get('name'),body.get('draft') is True)
            elif self.path == '/api/deliveries/push': result = self.server.deliveries.push(body['id'])
            elif self.path == '/api/restore': result = self.server.workshop.restore(body)
            elif self.path == '/api/delete-history': result = self.server.workshop.delete_history(body)
            elif self.path == '/api/upscale/jobs': result = self.server.imagelab.create_upscale(body)
            elif self.path == '/api/asset-audit': result = self.server.audit.start(body.get('ids',list(self.server.workshop.frames)),bool(body.get('strict',False)))
            elif self.path == '/api/variants/refine-alpha': result = self.server.imagelab.refine_alpha(body)
            elif self.path == '/api/variants/extract-alpha': result = self.server.imagelab.extract_variant_alpha(body)
            elif self.path == '/api/variants/import': result = self.server.imagelab.import_variant(body)
            elif self.path == '/api/variants/select': result = self.server.imagelab.select_variant(body)
            elif self.path == '/api/import': result = self.server.workshop.import_png(body)
            elif self.path == '/api/imagelab/jobs': result = self.server.imagelab.create(body)
            elif self.path == '/api/imagelab/apply': result = self.server.imagelab.apply(body['job_id'])
            elif self.path == '/api/imagelab/cancel': result = self.server.imagelab.cancel(body['job_id'])
            elif self.path == '/api/imagelab/delete': result = self.server.imagelab.delete(body['job_id'])
            elif self.path == '/api/imagelab/alpha': result = self.server.imagelab.alpha_variant(body['job_id'])
            elif self.path == '/api/imagelab/approve': result = self.server.imagelab.approve(body)
            elif self.path == '/api/imagelab/revoke': result = self.server.imagelab.revoke(body['id'])
            else: return self.send(404, dict(error='No encontrado.'))
            self.send(200, result)
        except Conflict as error: self.send(409, dict(error=str(error)))
        except (ValueError, KeyError, FileNotFoundError) as error: self.send(400, dict(error=str(error)))
        except Exception: self.send(500, dict(error='No se pudo guardar. Tus cambios siguen en el editor. Revisá espacio y permisos.'))


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = True
    request_queue_size = 64

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(root, port=5215):
    server = LocalServer(('127.0.0.1', port), Handler)
    server.workshop = Workshop(Path(root))
    server.imagelab = ImageLab(server.workshop, atomic, sha, png_size, Conflict)
    from asset_audit import AssetAudit
    server.audit = AssetAudit(server.workshop)
    from deliveries import Deliveries
    server.deliveries = Deliveries(server.workshop,server.imagelab)
    server.imagelab.resume()
    return server


def main():
    parser = argparse.ArgumentParser(description='Monkey Sprite Painter — local')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--port', type=int, default=5215)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = make_server(args.root, args.port)
    except OSError:
        url = f'http://127.0.0.1:{args.port}'
        try:
            with urllib.request.urlopen(url + '/api/health', timeout=3) as response:
                active = json.load(response)
            if active.get('app') != 'monkey-sprite-painter' or Path(active['root']).resolve() != args.root.resolve():
                raise ValueError('Otro programa ocupa el puerto.')
        except Exception:
            raise SystemExit(f'El puerto {args.port} está ocupado. Probá --port 5217.')
        print('El editor ya está abierto: ' + url, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Monkey Sprite Painter\n{url}\nProyecto: {args.root}\nCerrar esta ventana detiene el editor.', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()

