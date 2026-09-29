"""Non-destructive, exact-palette preparation of generation sources."""
import io
import json
import re
import time
from PIL import Image
import numpy as np


def settings(body):
    colors = body.get('colors', [])
    tolerance = body.get('tolerance', 0)
    if not isinstance(colors, list) or len(colors) > 64 or any(not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colors):
        raise ValueError('Elegí hasta 64 colores RGB.')
    if type(tolerance) is not int or not 0 <= tolerance <= 64:
        raise ValueError('La tolerancia debe estar entre 0 y 64.')
    return dict(colors=list(dict.fromkeys(c.lower() for c in colors)), tolerance=tolerance)


def remove_colors(image, colors, tolerance=0):
    pixels = np.array(image.convert('RGBA'))
    visible = pixels[:, :, 3] > 0
    removed = np.zeros(visible.shape, dtype=bool)
    rgb = pixels[:, :, :3].astype(np.int16)
    for color in colors:
        target = np.array([int(color[i:i+2], 16) for i in (1, 3, 5)], dtype=np.int16)
        removed |= visible & (np.abs(rgb-target).max(axis=2) <= tolerance)
    if visible.any() and np.array_equal(removed, visible):
        raise ValueError('Estos colores eliminan todo el dibujo. Quitá alguno o bajá la tolerancia.')
    pixels[removed] = 0
    return Image.fromarray(pixels), int(removed.sum())


def metadata(work, asset):
    work.frame(asset)
    path = work.store/'sources'/asset/'current.json'
    return json.loads(path.read_text()) if path.exists() else None


def reference(work, asset):
    original = work.reference(asset)
    meta = metadata(work, asset)
    if not meta:
        return original
    from server import sha
    if not original or sha(original.read_bytes()) != meta['original_sha256']:
        raise ValueError('El original cambió. Revisá de nuevo los colores excluidos antes de generar.')
    version = meta['revision']
    if not re.fullmatch(r'[a-f0-9]{64}', version):
        raise ValueError('Preparación de original inválida.')
    return work.store/'sources'/asset/(version+'.png')


def snapshot(work, asset):
    meta = metadata(work, asset)
    return dict(id=asset, preparation=meta, original='/api/reference?id='+asset,
                image='/api/source-image?id='+asset+('&v='+meta['revision'] if meta else ''))


def save(work, body):
    from server import atomic, sha
    ids = body.get('ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 512 or any(not isinstance(i,str) for i in ids):
        raise ValueError('Seleccioná entre 1 y 512 cuadros.')
    ids = list(dict.fromkeys(ids))
    for asset in ids: work.frame(asset)
    config = settings(body)
    results = []
    with work.lock:
        for asset in ids:
            try:
                folder = work.store/'sources'/asset
                if body.get('reset') is True:
                    (folder/'current.json').unlink(missing_ok=True)
                    results.append(dict(id=asset, reset=True))
                else:
                    original = work.reference(asset)
                    if not original: raise ValueError('No hay original asociado.')
                    from server import _cached_read
                    data = _cached_read(original)
                    with Image.open(io.BytesIO(data)) as image:
                        cleaned, count = remove_colors(image, **config)
                    buffer = io.BytesIO(); cleaned.save(buffer, format='PNG')
                    output = buffer.getvalue(); revision = sha(output)
                    meta = dict(**config, revision=revision, original_sha256=sha(data),
                                removed_pixels=count, saved_at=time.time(), width=cleaned.width,height=cleaned.height)
                    # Immutable snapshots retain every previous preparation.
                    atomic(folder/(revision+'.png'), output)
                    atomic(folder/(revision+'.json'), json.dumps(meta).encode())
                    atomic(folder/'current.json', json.dumps(meta).encode())
                    results.append(dict(id=asset, preparation=meta))
                work.catalog_cache.pop(asset,None);work._open_cache.pop(asset,None)
                work.changes.publish(asset,'source')
            except (ValueError,OSError) as error:
                results.append(dict(id=asset,error=str(error)))
    return dict(results=results)
