"""Lossless COMI cel extraction for the room-9 character pack.

Codec layout follows the pinned ScummVM AKOS/BOMP decoder. Game data stays local.
"""
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from prepare_topaz import chunks, costume_rgba


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode_cel(data, width, height, codec, colors):
    if not 0 < width * height <= 4096 * 4096:
        raise ValueError('Invalid cel size')
    if codec == 1:
        shift, mask = {16: (4, 15), 32: (3, 7), 64: (2, 3)}[colors]
        result = bytearray()
        pos = 0
        while len(result) < width * height:
            code = data[pos]
            pos += 1
            count = code & mask
            if not count:
                count = data[pos]
                pos += 1
            if not count:
                raise ValueError('Zero-length costume run')
            result.extend(bytes([code >> shift]) * count)
        return np.frombuffer(result[:width * height], dtype=np.uint8).reshape((height, width), order='F')
    if codec == 5:
        result = np.full((height, width), 255, dtype=np.uint8)
        pos = 0
        for y in range(height):
            length = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            end = pos + length
            if end > len(data):
                raise ValueError('Truncated BOMP row')
            x = 0
            while pos < end and x < width:
                code = data[pos]
                pos += 1
                count = (code >> 1) + 1
                size = 1 if code & 1 else count
                if pos + size > end:
                    raise ValueError('Truncated BOMP run')
                pixels = data[pos:pos + size]
                pos += size
                if code & 1:
                    pixels *= count
                copied = min(count, width - x)
                result[y, x:x + copied] = list(pixels[:copied])
                x += copied
            pos = end
        return result
    raise ValueError(f'Unsupported codec {codec}')


def resources(game, selected):
    index = dict((t, p) for t, _, p in chunks((game / 'COMI.LA0').read_bytes()))['DCOS']
    count = struct.unpack_from('<I', index)[0]
    rooms = index[4:4 + count]
    offsets = struct.unpack_from('<' + 'I' * count, index, 4 + count)
    found = {}
    for disc in (1, 2):
        data = (game / f'COMI.LA{disc}').read_bytes()
        top = {t: p for t, _, p in chunks(data, 8)}
        loff = top['LOFF']
        locations = {loff[1 + i * 5]: struct.unpack_from('<I', loff, 2 + i * 5)[0]
                     for i in range(loff[0])}
        for cid in selected:
            room = rooms[cid]
            if room not in locations or not offsets[cid]:
                continue
            location = locations[room]
            pos = location + offsets[cid]
            size = int.from_bytes(data[pos + 4:pos + 8], 'big')
            if data[pos:pos + 4] != b'AKOS':
                raise ValueError(f'Invalid AKOS {cid}')
            raw = data[pos:pos + size]
            if cid in found:
                if sha(raw) != found[cid]:
                    raise ValueError(f'Discs disagree for costume {cid}')
                continue
            found[cid] = sha(raw)
            fields = {t: p for t, _, p in chunks(raw, 8)}
            room_size = int.from_bytes(data[location + 12:location + 16], 'big')
            room_fields = {t: p for t, _, p in chunks(data, location + 16, location + 8 + room_size)}
            pals = dict((t, p) for t, _, p in chunks(room_fields['PALS']))['WRAP']
            palette = next(p for t, _, p in chunks(pals) if t == 'APAL')
            yield cid, room, raw, fields, palette
    if set(selected) != set(found):
        raise ValueError(f'Missing costumes: {set(selected) - set(found)}')


def extract(game, output, selected):
    records, metadata = [], {}
    for cid, room, raw, fields, room_palette in resources(game, selected):
        header = struct.unpack('<6H', fields['AKHD'][:12])
        codec = header[4]
        akpl = fields['AKPL']
        palette = fields.get('RGBS', room_palette) if codec == 1 else room_palette
        # RGBS already uses the local AKPL indices for COMI codec 1.
        meta = {'codec': codec, 'akpl': list(akpl), 'rgbs': list(fields.get('RGBS', b''))}
        resource_dir = output / 'resources' / str(cid)
        resource_dir.mkdir(parents=True, exist_ok=True)
        for tag in ('AKCH', 'AKSQ', 'AKOF', 'AKCI', 'AKPL', 'RGBS'):
            if tag in fields:
                (resource_dir / f'{tag}.bin').write_bytes(fields[tag])
        metadata[str(cid)] = dict(room=room, header=list(header), sha256=sha(raw), palette=list(palette), akpl=list(akpl))
        entries = list(struct.iter_unpack('<IH', fields['AKOF']))
        if len(entries) != header[3]:
            raise ValueError(f'Cel count mismatch for {cid}')
        cd_ends = sorted(set(cd for cd, _ in entries) | {len(fields['AKCD'])})
        for cel, (cd, ci) in enumerate(entries):
            width, height = struct.unpack_from('<HH', fields['AKCI'], ci)
            end = next(v for v in cd_ends if v > cd)
            indices = decode_cel(fields['AKCD'][cd:end], width, height, codec, len(akpl))
            indexed = Image.fromarray(indices, 'P')
            indexed.putpalette(palette + bytes(768 - len(palette)))
            clean, shadows = costume_rgba(indexed, meta)
            if codec == 5:
                # COMI's BOMP shadow mode 3 uses runtime palette slots 0..7.
                # These are shadow selectors, not the orange/brown palette paint.
                rgba = np.array(clean)
                shadow = indices < 8
                rgba[shadow] = (0, 0, 0, 128)
                clean = Image.fromarray(rgba)
                shadows = int(shadow.sum())
            name = f'LFLF_{room:04d}_AKOS_{cid:04d}_frame_{cel}.png'
            for folder, im in (('indexed', indexed), ('cleaned', clean)):
                target = output / folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                im.save(target)
            key = sha(struct.pack('<II', width, height) + clean.tobytes())
            records.append(dict(source=name, costume=cid, room=room, cel=cel,
                                size=[width, height], offset_source='AKSQ draw commands (signed int16)',
                                codec=codec, source_sha256=sha(indexed.tobytes() + bytes(palette)),
                                artwork_sha256=key, shadow_pixels=shadows))
    manifest = dict(version=1, room=9, model='arrow-2', master_scale=6, runtime_scale=4,
                    resources=metadata, records=records)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'extraction.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest
