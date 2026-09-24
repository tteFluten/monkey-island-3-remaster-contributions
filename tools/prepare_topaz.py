#!/usr/bin/env python3
"""Restore COMI palette transparency without changing source files or canvas sizes."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

import numpy as np
from PIL import Image

VERSION = 1


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    while start < end:
        size = int.from_bytes(data[start + 4:start + 8], 'big')
        if size < 8 or start + size > end:
            raise ValueError(f'Invalid game chunk at {start}')
        yield data[start:start + 4].decode('ascii'), start, data[start + 8:start + size]
        start += size


def game_metadata(game):
    index = {tag: payload for tag, _, payload in chunks((game / 'COMI.LA0').read_bytes())}
    cos = index['DCOS']
    count = struct.unpack_from('<I', cos)[0]
    rooms = cos[4:4 + count]
    offsets = struct.unpack_from('<' + 'I' * count, cos, 4 + count)
    costumes, transparency, objects = {}, {}, {}
    for disc in (1, 2):
        data = (game / f'COMI.LA{disc}').read_bytes()
        top = {tag: (pos, payload) for tag, pos, payload in chunks(data, 8)}
        loff = top['LOFF'][1]
        locations = {loff[1 + i * 5]: struct.unpack_from('<I', loff, 2 + i * 5)[0]
                     for i in range(loff[0])}
        for room, location in locations.items():
            room_size = int.from_bytes(data[location + 12:location + 16], 'big')
            fields = {tag: payload for tag, _, payload in chunks(data, location + 16, location + 8 + room_size)}
            # COMI v8 RMHD consists of six little-endian uint32 fields.
            rmhd = struct.unpack('<6I', fields['RMHD'])
            transparency[str(room)] = rmhd[5]
            for tag, _, payload in chunks(data, location + 16, location + 8 + room_size):
                if tag != 'OBIM':
                    continue
                ob = {t: p for t, _, p in chunks(payload)}
                if 'IMAG' not in ob:
                    continue
                header = ob['IMHD']
                name = header[:40].split(b'\0')[0].decode()
                x, y, w, h = struct.unpack_from('<iiII', header, 48)
                wrap = dict((t, p) for t, _, p in chunks(ob['IMAG']))['WRAP']
                for frame, (t, _, image_data) in enumerate(list(chunks(wrap))[1:]):
                    if t not in ('BOMP', 'SMAP'):
                        raise ValueError(f'Unsupported object codec {t}: {name}')
                    objects[f'{room:04d}_{name}_{frame:04d}.png'] = {
                        'offset': [x, y], 'size': [w, h], 'codec': t,
                        'transparent_index': 255 if t == 'BOMP' else rmhd[5]}
                    if t == 'SMAP':
                        smap = dict((t, p) for t, _, p in chunks(image_data))['BSTR']
                        strips = dict((t, p) for t, _, p in chunks(smap))['WRAP'][8:]
                        offsets_smap = struct.unpack_from('<' + 'I' * (w // 8), strips)
                        codes = [strips[offset - 8] for offset in offsets_smap]
                        objects[f'{room:04d}_{name}_{frame:04d}.png']['transparent_strips'] = [
                            0x22 <= code <= 0x30 or 0x54 <= code <= 0x80 or code >= 0x8f for code in codes]
        for cid, room in enumerate(rooms):
            if room not in locations or not offsets[cid]:
                continue
            pos = locations[room] + offsets[cid]
            if data[pos:pos + 4] != b'AKOS':
                raise ValueError(f'Invalid costume offset: {cid}')
            size = int.from_bytes(data[pos + 4:pos + 8], 'big')
            fields = {tag: payload for tag, _, payload in chunks(data, pos + 8, pos + size)}
            codec = int.from_bytes(fields['AKHD'][8:10], 'little')
            costumes[str(cid)] = {'room': room, 'codec': codec, 'akpl': list(fields['AKPL']),
                                  'rgbs': list(fields.get('RGBS', b''))}
    return {'costumes': costumes, 'transparency': transparency, 'objects': objects}


def costume_rgba(im, metadata, shadow_alpha=128):
    if im.mode != 'P':
        raise ValueError('Expected indexed source PNG')
    indices = np.asarray(im)
    rgba = np.array(im.convert('RGBA'))
    codec = metadata['codec']
    key = 0 if codec == 1 else 255
    shadow = np.zeros(indices.shape, dtype=bool)
    if codec == 1:
        # RGBS is indexed by the local costume index. AKPL maps that index to
        # runtime palette slots. COMI shadow mode 3 blends slots 1..7.
        rgbs = metadata['rgbs']
        if rgbs and im.getpalette()[:len(rgbs)] != rgbs:
            raise ValueError('PNG palette does not match costume RGBS; needs review')
        slots = [i for i, slot in enumerate(metadata['akpl']) if i != 0 and 1 <= slot <= 7]
        shadow = np.isin(indices, slots)
        rgba[shadow, :3] = 0
        rgba[shadow, 3] = shadow_alpha
    elif codec not in (5, 16, 32):
        raise ValueError(f'Unsupported costume codec {codec}')
    rgba[indices == key] = 0
    return Image.fromarray(rgba), int(shadow.sum())


def object_rgba(im, key, transparent_strips=None):
    if im.mode != 'P':
        raise ValueError('Expected indexed object PNG')
    rgba = np.array(im.convert('RGBA'))
    mask = np.asarray(im) == key
    if transparent_strips is not None:
        columns = np.repeat(transparent_strips, 8)
        if len(columns) != im.width:
            raise ValueError('Object strip width does not match PNG')
        mask &= columns[None, :]
    rgba[mask] = 0
    return Image.fromarray(rgba)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source, output, game, shadow_alpha=128):
    output.mkdir(parents=True, exist_ok=True)
    meta = game_metadata(game)
    (output / 'palette-metadata.json').write_text(json.dumps(meta))
    records, failures, unique = [], [], {}
    for folder in ('costumes', 'objects', 'objects_layers'):
        files = sorted((source / folder).glob('*.png'))
        if not files:
            raise ValueError(f'No PNG files in {source / folder}')
        for num, path in enumerate(files):
            relative = f'{folder}/{path.name}'
            target = output / 'cleaned' / relative
            try:
                with Image.open(path) as im:
                    record = {'source': relative, 'source_sha256': digest(path), 'size': list(im.size)}
                    if folder == 'costumes':
                        match = re.fullmatch(r'LFLF_(\d+)_AKOS_(\d+)_frame_(\d+)\.png', path.name)
                        if not match:
                            raise ValueError('Unrecognized costume filename')
                        costume = meta['costumes'][str(int(match[2]))]
                        if costume['room'] != int(match[1]):
                            raise ValueError('Costume room mismatch')
                        clean, count = costume_rgba(im, costume, shadow_alpha)
                        record['shadow_pixels'] = count
                    elif folder == 'objects':
                        key = meta['objects'][path.name]['transparent_index']
                        clean = object_rgba(im, key, meta['objects'][path.name].get('transparent_strips'))
                        record['transparent_index'] = key
                    else:
                        original = source / 'objects' / path.name
                        offset = tuple(meta['objects'][path.name]['offset'])
                        with Image.open(original) as obj:
                            expected = Image.new('P', im.size, 39)
                            expected.paste(obj, offset)
                            if not np.array_equal(np.asarray(expected), np.asarray(im)):
                                raise ValueError('Layer does not match original object placement')
                        clean = Image.new('RGBA', im.size)
                        with Image.open(output / 'cleaned' / 'objects' / path.name) as obj:
                            clean.paste(obj, offset)
                        record.update(derived_from=f'objects/{path.name}', offset=list(offset))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    clean.save(target)
                    record['cleaned_sha256'] = digest(target)
                    if 'derived_from' not in record:
                        record['canonical'] = unique.setdefault(record['cleaned_sha256'], relative)
                    records.append(record)
            except Exception as error:
                failures.append({'source': relative, 'error': str(error)})
            if num % 1000 == 0:
                print(f'{folder}: {num + 1}/{len(files)}; review required: {len(failures)}', flush=True)
    manifest = {'version': VERSION, 'source_root': str(source.resolve()), 'shadow_alpha': shadow_alpha,
                'model': 'Wonder 3.5', 'enhancementStrength': 'high', 'scale': 6,
                'records': records, 'failures': failures}
    tmp = output / 'manifest.json.tmp'
    tmp.write_text(json.dumps(manifest, indent=2))
    tmp.replace(output / 'manifest.json')
    print(json.dumps({'prepared': len(records), 'unique_api_inputs': len(unique),
                      'derived_layers': sum('derived_from' in r for r in records), 'failures': len(failures)}), flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--game', type=Path, default=Path('.playtest/game'))
    parser.add_argument('--shadow-alpha', type=int, choices=range(256), default=128, metavar='0..255')
    args = parser.parse_args()
    prepare(args.source, args.output, args.game, args.shadow_alpha)
