"""Backed-up PNG replacements shared by the preview editor and draft installer."""
import argparse
import contextlib
import io
import json
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image
from quiver_cannon import atomic, locked
from topaz_character_cutouts import digest
from topaz_scenes import read, SOURCE

TOPAZ = re.compile(r'^output/(?:topaz-batch|topaz-cannon-objectmatting|topaz-character-objectmatting|topaz-difficulty-knife|topaz-scenes/(?:room-\d{4}|derived|preview-derived))/4x/(.+)$')
EDITED = re.compile(r'^output/asset-edits/versions/[a-f0-9]{64}/(.+)$')


def image_size(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Use a single-frame PNG image')
        image.load()
        return image.size, image.mode


def resolve_url(root, url):
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc:
        raise ValueError('Only workspace asset URLs can be replaced')
    name = unquote(parsed.path)
    if name.startswith('/api/assets/file/'):
        relative = name[len('/api/assets/file/'):]
    elif name.startswith('/files/'):
        relative = name[len('/files/'):]
    else:
        raise ValueError('Unknown asset URL')
    if '\\' in relative or '\x00' in relative or any(p in ('', '.', '..') for p in relative.split('/')):
        raise ValueError('Invalid asset path')
    match = TOPAZ.fullmatch(relative) or EDITED.fullmatch(relative)
    source = match[1] if match else None
    if source:
        if not SOURCE.fullmatch(source): raise ValueError('Invalid Topaz source')
    elif not re.fullmatch(r'(extracted|upscaled|previews)/[a-zA-Z0-9_./ -]+\.png', relative):
        raise ValueError('Only current 4× Topaz outputs and library PNGs can be replaced')
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()): raise ValueError('Asset is outside the workspace')
    return target, source


def overrides(output, entries):
    """Verified manual pixels take precedence over provider outputs and repairs."""
    base = output.parent / 'asset-edits'
    records = {}
    for source, edit in read(base / 'manifest.json', {}).get('overrides', {}).items():
        if not SOURCE.fullmatch(source) or source not in entries: raise ValueError('Unknown manual asset')
        sha = edit['sha256']
        if not re.fullmatch('[a-f0-9]{64}', sha): raise ValueError('Invalid manual asset hash')
        master = base / 'versions' / sha / source
        if not master.resolve().is_relative_to(base.resolve()) or digest(master) != sha:
            raise ValueError('Manual asset changed')
        size, mode = image_size(master.read_bytes())
        if size != tuple(v * 4 for v in entries[source]['size']) or mode != 'RGBA':
            raise ValueError('Invalid manual asset canvas')
        records[source] = dict(master=str(master.resolve()), sha256=sha, state='manual-edit',
                               validation_passed=False, derived=False, manual=True)
    return records


def replace(root, url, expected, data):
    if not re.fullmatch('[a-f0-9]{64}', expected): raise ValueError('Missing image revision; reopen the editor')
    if not data or len(data) > 32 * 1024 * 1024: raise ValueError('PNG must be between 1 byte and 32 MB')
    size, mode = image_size(data)
    target, source = resolve_url(root, url)
    out = root / 'output/topaz-scenes'
    local = root / '.playtest'
    with locked(local / 'draft-install'):
        edits = root / 'output/asset-edits'
        manifest = read(edits / 'manifest.json', {'overrides': {}})
        current = target
        if source:
            entries = {e['source']: e for s in read(out / 'plan.json')['scenes'] for e in s['sources']}
            entry = entries.get(source)
            if not entry or entry['operation'] in ('preserve', 'empty'): raise ValueError('This asset cannot be replaced')
            if size != tuple(v * 4 for v in entry['size']) or mode != 'RGBA':
                raise ValueError('Replacement must keep the 4× RGBA canvas dimensions')
            prior = manifest['overrides'].get(source)
            if prior: current = Path(overrides(out, entries)[source]['master'])
        if not current.is_file() or digest(current) != expected:
            raise ValueError('This asset changed since the editor opened. Reopen it before saving.')
        if image_size(current.read_bytes())[0] != size: raise ValueError('Replacement dimensions must match the preview')
        stamp = str(time.time_ns())
        backup = local / 'backups' / ('asset-edit-' + stamp)
        backup.mkdir(parents=True)
        shutil.copy2(current, backup / 'previous.png')
        import hashlib
        sha = hashlib.sha256(data).hexdigest()
        if source:
            saved = edits / 'versions' / sha / source
        else:
            saved = target
        saved.parent.mkdir(parents=True, exist_ok=True)
        temporary = saved.with_name(saved.name + '.' + stamp + '.tmp')
        temporary.write_bytes(data)
        temporary.replace(saved)
        if source:
            if (edits / 'manifest.json').exists(): shutil.copy2(edits / 'manifest.json', backup / 'manifest.json')
            manifest['overrides'][source] = dict(sha256=sha, saved_at=time.time(), previous_sha256=expected)
            atomic(edits / 'manifest.json', manifest)
        result = dict(sha256=sha, url='/files/' + saved.relative_to(root).as_posix() + '?v=' + sha,
                      source=source, backup=str(backup), installed=False)
        atomic(backup / 'receipt.json', result)
    # Installer holds the same lock, rereads the current override, and refuses
    # runtime writes while a game is running. Saving the edit itself still works.
    if source:
        try:
            from install_asset_drafts import install
            with contextlib.redirect_stdout(io.StringIO()): install(out, local)
            result.update(installed=True, message='Asset replaced and installed in both game packs.')
        except Exception as error:
            result.update(message='Asset replaced. Game installation is pending: ' + str(error))
    else:
        result['message'] = 'Asset replaced. The previous PNG is backed up.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--url', required=True)
    parser.add_argument('--expected', required=True)
    args = parser.parse_args()
    try:
        result = replace(args.root.resolve(), args.url, args.expected, sys.stdin.buffer.read(32 * 1024 * 1024 + 1))
        print(json.dumps(result))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__': main()
