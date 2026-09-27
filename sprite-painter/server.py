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

PNG = b'\x89PNG\r\n\x1a\n'
MAX_BODY = 48 * 1024 * 1024


@lru_cache(maxsize=192)
def thumbnail(path, modified, reference):
    data = Path(path).read_bytes()
    png_size(data)
    try:
        from PIL import Image
    except ImportError:
        return data
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert('RGBA')
        image.thumbnail((240, 180), Image.Resampling.NEAREST if reference else Image.Resampling.LANCZOS)
        result = io.BytesIO(); image.save(result, format='PNG')
        return result.getvalue()


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
        self.lock = threading.RLock()
        self.reload()

    def register(self, path, category, name=None, dimensions=None):
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
        return id_

    def reload(self):
        with self.lock:
            self.reference.cache_clear()
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

    @lru_cache(maxsize=4096)
    def reference(self, id_):
        relative = self.frame(id_)['path']
        prefix = next((p for p in ('assets/masters/topaz-4x/', 'assets/masters/ui-4x/') if relative.startswith(p)), None)
        if prefix is None:
            return None
        # The cleaned files retain original colors and restore game transparency.
        # Raw extraction can contain palette-key backgrounds and shadow indices.
        for folder in ('assets/references/topaz-cleaned', 'extracted'):
            candidate = (self.root / folder / relative.removeprefix(prefix)).resolve()
            if candidate.is_relative_to(self.root) and candidate.is_file():
                return candidate
        return None

    def revision(self, id_):
        p = self.draft(id_)
        if not p.exists():
            return None
        # Include metadata so concurrent alignment-only edits also conflict.
        return self.metadata(id_).get('revision') or sha(p.read_bytes())

    def metadata(self, id_):
        p = self.store / 'edits' / (id_ + '.json')
        return json.loads(p.read_text()) if p.exists() else {}

    def open(self, id_):
        with self.lock:
            original = self.original(id_).read_bytes()
            size = png_size(original)
            revision = self.revision(id_)
            meta = self.metadata(id_)
            return dict(frame=self.frame(id_), width=size[0], height=size[1],
                        revision=revision, offset=meta.get('offset', [0, 0]),
                        current_sha256=meta.get('sha256') if revision else sha(original),
                        selected_variant=meta.get('selected_variant'),
                        original=f'/api/image?id={id_}&original=1',
                        image=f'/api/image?id={id_}&v={revision or "base"}')

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
            return dict(revision=revision, saved=str(previous), offset=offset)

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
            return dict(id=self.register(path, 'Importados · ' + session, dimensions=list(size)))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, value, mime='application/json'):
        data = json.dumps(value, ensure_ascii=False).encode() if mime == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

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
            elif parsed.path == '/api/imagelab/status':
                self.send(200, self.server.imagelab.status())
            elif parsed.path == '/api/deliveries':
                self.send(200,self.server.deliveries.snapshot())
            elif parsed.path == '/api/imagelab/jobs':
                self.send(200, dict(jobs=self.server.imagelab.list(args.get('asset',[None])[0]),approvals=self.server.imagelab.approvals()))
            elif parsed.path == '/api/imagelab/job':
                self.send(200, self.server.imagelab.read(args['id'][0]))
            elif parsed.path == '/api/imagelab/image':
                folder=self.server.imagelab.folder(args['id'][0])
                name='input.png' if 'input' in args else ('provider.png' if 'raw' in args else 'candidate.png')
                if 'input' in args and (folder/'alpha-source.png').exists():
                    name='alpha-source.png'
                self.send(200, (folder/name).read_bytes(), 'image/png')
            elif parsed.path == '/api/imagelab/reference':
                asset=args['id'][0];w.frame(asset);approval=self.server.imagelab.approvals().get(asset)
                path=self.server.imagelab.root/'references'/approval['file'] if approval else w.original(asset)
                self.send(200,path.read_bytes(),'image/png')
            elif parsed.path == '/api/imagelab/prepared':
                from PIL import Image
                from spriteprep import clean_base
                path=w.reference(args['id'][0])
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
                frames=[]
                for f in w.frames.values():
                    ref=w.reference(f['id'])
                    variant=w.metadata(f['id']).get('selected_variant',{})
                    edge_cleaned=variant.get('operation')=='local-alpha' or variant.get('model','').startswith('Limpieza de borde')
                    frames.append(dict(f, edited=w.draft(f['id']).exists(), revision=w.revision(f['id']), edge_cleaned=edge_cleaned,has_reference=ref is not None,
                        reference_kind='original-preparado' if ref and 'topaz-cleaned' in ref.parts else 'original'))
                self.send(200, dict(frames=frames, root=str(w.root), store=str(w.store)))
            elif parsed.path == '/api/thumbnail':
                id_ = args['id'][0]
                reference = args.get('reference', ['0'])[0] == '1'
                path = w.reference(id_) if reference else w.draft(id_) if w.draft(id_).exists() else w.original(id_)
                if path is None: return self.send(404, dict(error='No hay un original asociado por nombre exacto.'))
                self.send(200, thumbnail(str(path), path.stat().st_mtime_ns, reference), 'image/png')
            elif parsed.path == '/api/open':
                self.send(200, w.open(args['id'][0]))
            elif parsed.path == '/api/image':
                id_ = args['id'][0]
                p = w.original(id_) if 'original' in args or not w.draft(id_).exists() else w.draft(id_)
                data = p.read_bytes()
                png_size(data)
                self.send(200, data, 'image/png')
            elif parsed.path == '/api/reference':
                reference=w.reference(args['id'][0])
                if reference is None: return self.send(404, dict(error='No hay original asociado a este asset.'))
                data=reference.read_bytes();png_size(data)
                self.send(200, data, 'image/png')
            elif parsed.path == '/api/history':
                id_ = args['id'][0]; w.frame(id_)
                folder = w.store / 'history' / id_
                names = sorted((p.name for p in folder.glob('*.png')), reverse=True)
                self.send(200, dict(items=names))
            elif parsed.path == '/api/version':
                id_ = args['id'][0]; w.frame(id_)
                name = args['name'][0]
                if not re.fullmatch(r'\d+-before\.png', name): raise ValueError('Versión inválida.')
                data = (w.store / 'history' / id_ / name).read_bytes()
                self.send(200, data, 'image/png')
            elif parsed.path == '/confite/':
                self.send(200, (Path(__file__).parent / 'confite' / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            elif parsed.path in ('/', '/app.js', '/style.css', '/confite-link.js', '/confite-workshop.css', '/workshop-theme.css', '/asset-browser.js', '/imagelab-ui.js', '/asset-review.js', '/deliveries-ui.js'):
                names = {'/': ('index.html', 'text/html; charset=utf-8'),
                         '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                         '/confite-link.js': ('confite-link.js', 'text/javascript; charset=utf-8'),
                         '/confite-workshop.css': ('confite-workshop.css', 'text/css; charset=utf-8'),
                         '/workshop-theme.css': ('workshop-theme.css', 'text/css; charset=utf-8'),
                         '/asset-browser.js': ('asset-browser.js', 'text/javascript; charset=utf-8'),
                         '/asset-review.js': ('asset-review.js', 'text/javascript; charset=utf-8'),
                         '/deliveries-ui.js': ('deliveries-ui.js', 'text/javascript; charset=utf-8'),
                         '/imagelab-ui.js': ('imagelab-ui.js', 'text/javascript; charset=utf-8'),
                         '/style.css': ('style.css', 'text/css; charset=utf-8')}
                name, mime = names[parsed.path]
                self.send(200, (Path(__file__).parent / name).read_bytes(), mime)
            else: self.send(404, dict(error='No encontrado.'))
        except (ValueError, KeyError, FileNotFoundError) as error:
            self.send(400, dict(error=str(error)))
        except Exception:
            self.send(500, dict(error='No se pudo leer el archivo. Revisá permisos y espacio en disco.'))

    def do_POST(self):
        try:
            self.trusted()
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY: raise ValueError('Archivo demasiado grande.')
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                raise ValueError('Formato de petición inválido.')
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/save': result = self.server.workshop.save(body)
            elif self.path == '/api/deliveries/prepare': result = self.server.deliveries.start(body.get('scope','complete'))
            elif self.path == '/api/deliveries/branch': result = self.server.deliveries.branch(body['id'],body.get('name'),body.get('draft') is True)
            elif self.path == '/api/deliveries/push': result = self.server.deliveries.push(body['id'])
            elif self.path == '/api/restore': result = self.server.workshop.restore(body)
            elif self.path == '/api/upscale/jobs': result = self.server.imagelab.create_upscale(body)
            elif self.path == '/api/asset-audit': result = self.server.audit.start(body.get('ids',list(self.server.workshop.frames)),bool(body.get('strict',False)))
            elif self.path == '/api/variants/refine-alpha': result = self.server.imagelab.refine_alpha(body)
            elif self.path == '/api/variants/select': result = self.server.imagelab.select_variant(body)
            elif self.path == '/api/import': result = self.server.workshop.import_png(body)
            elif self.path == '/api/imagelab/jobs': result = self.server.imagelab.create(body)
            elif self.path == '/api/imagelab/apply': result = self.server.imagelab.apply(body['job_id'])
            elif self.path == '/api/imagelab/cancel': result = self.server.imagelab.cancel(body['job_id'])
            elif self.path == '/api/imagelab/alpha': result = self.server.imagelab.alpha_variant(body['job_id'])
            elif self.path == '/api/imagelab/approve': result = self.server.imagelab.approve(body)
            elif self.path == '/api/imagelab/revoke': result = self.server.imagelab.revoke(body['id'])
            else: return self.send(404, dict(error='No encontrado.'))
            self.send(200, result)
        except Conflict as error: self.send(409, dict(error=str(error)))
        except (ValueError, KeyError, FileNotFoundError) as error: self.send(400, dict(error=str(error)))
        except Exception: self.send(500, dict(error='No se pudo guardar. Tus cambios siguen en el editor. Revisá espacio y permisos.'))


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

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

