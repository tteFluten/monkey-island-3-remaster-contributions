#!/usr/bin/env python3
"""Audit original LB83 bundles and compare local copies without changing game data."""
import argparse
from collections import Counter
import hashlib
import json
import mmap
from pathlib import Path
import struct

from comi_audio import atomic_json, digest

CODECS = {0, 1, 2, 3, 4, 5, 6, 10, 11, 12, 13, 15}


def audit(path):
    result = dict(path=str(path.resolve()), sha256=digest(path), bytes=path.stat().st_size,
                  errors=[], entries=[])
    if path.stat().st_size < 12:
        result['errors'].append('Truncated bundle header')
        return result
    with path.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:4] != b'LB83':
            result['errors'].append('Unsupported bundle format: ' + repr(data[:4]))
            return result
        directory, count = struct.unpack_from('>II', data, 4)
        if directory < 12 or directory + count * 20 > len(data):
            result['errors'].append('Bundle directory exceeds file bounds')
            return result
        names = set()
        for index in range(count):
            pos = directory + index * 20
            name = data[pos:pos+8].split(b'\0')[0].decode('ascii', 'replace')
            ext = data[pos+8:pos+12].split(b'\0')[0].decode('ascii', 'replace')
            name += ('.' + ext) if ext else ''
            offset, size = struct.unpack_from('>II', data, pos + 12)
            entry = dict(index=index, name=name, offset=offset, size=size, errors=[])
            result['entries'].append(entry)
            if name in names:
                entry['errors'].append('Duplicate entry name')
            names.add(name)
            if offset < 12 or offset + size > len(data) or size < 4:
                entry['errors'].append('Entry exceeds file bounds or is too short')
                entry['status'] = 'invalid'
                continue
            tag = data[offset:offset+4]
            entry['tag_hex'] = tag.hex()
            entry['sha256'] = hashlib.sha256(data[offset:offset+size]).hexdigest()
            # PRELOAD is a bundle lookup/cache record, not playable compressed audio.
            if name.upper() == 'PRELOAD':
                entry['status'] = 'metadata'
                continue
            if tag == b'COMP':
                if size < 16:
                    entry['errors'].append('Truncated COMP header')
                else:
                    blocks, _, last_size = struct.unpack_from('>III', data, offset + 4)
                    entry.update(blocks=blocks, last_block_bytes=last_size)
                    if last_size > 8192:
                        entry['errors'].append('Final decoded block exceeds 8192 bytes')
                    if not 0 < blocks <= (size - 16) // 16:
                        entry['errors'].append('Invalid compression-table count')
                    else:
                        for block in range(blocks):
                            start, length, codec, _ = struct.unpack_from('>IIII', data, offset+16+block*16)
                            if start < 16+blocks*16 or not length or start+length > size:
                                entry['errors'].append(f'Block {block} exceeds entry bounds')
                            if codec not in CODECS:
                                entry['errors'].append(f'Block {block} has unknown codec {codec}')
            elif tag == b'iMUS':
                if size < 16 or data[offset+8:offset+12] != b'MAP ':
                    entry['errors'].append('Invalid uncompressed iMUS header')
            else:
                entry['errors'].append('Invalid playable sound header')
            entry['status'] = 'invalid' if entry['errors'] else 'valid_structure'
    result['counts'] = dict(Counter(x['status'] for x in result['entries']))
    return result


def report(target, roots):
    resource = target / '.playtest/game/RESOURCE'
    installed = [audit(resource / name) for name in ['VOXDISK1.BUN', 'VOXDISK2.BUN', 'MUSDISK1.BUN', 'MUSDISK2.BUN']]
    candidates = {}
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else root.rglob('*')
        for path in paths:
            if path.is_file() and path.name.upper() in ('VOXDISK1.BUN', 'VOXDISK2.BUN', 'VOICE.BUN'):
                key = str(path.resolve())
                if key not in candidates:
                    candidates[key] = audit(path)
    unresolved = []
    for bundle in installed:
        if not Path(bundle['path']).name.startswith('VOX'):
            continue
        for entry in bundle['entries']:
            if entry['status'] != 'invalid':
                continue
            matches = []
            for candidate in candidates.values():
                for item in candidate['entries']:
                    if item['name'] == entry['name'] and item['status'] == 'valid_structure':
                        matches.append(dict(bundle=candidate['path'], sha256=item['sha256']))
            unresolved.append(dict(bundle=Path(bundle['path']).name, **entry,
                                   structurally_valid_candidates=matches))
    return dict(version=1, target_workspace=str(target), installed=installed,
                searched_roots=[str(p) for p in roots], candidates=list(candidates.values()),
                unresolved=unresolved, restored_entries=0,
                validation='Structural audit only; valid_structure does not certify decoded audio or matching language.',
                required_replacement=sorted(set(x['bundle'] for x in unresolved)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-workspace', required=True, type=Path)
    parser.add_argument('--source-root', action='append', type=Path, default=[])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repair-manifest', type=Path)
    args = parser.parse_args()
    data = report(args.target_workspace.resolve(), [p.resolve() for p in args.source_root])
    if args.repair_manifest:
        repair = json.loads(args.repair_manifest.read_text())
        if repair['prepared_sha256'] != data['installed'][0]['sha256']:
            raise ValueError('Repair manifest does not match installed bundle')
        data['restored_entries'] = repair.get('total_restored_entries', len(repair['repairs']))
        data['repair_manifest'] = str(args.repair_manifest.resolve())
    atomic_json(args.output, data)
    for bundle in data['installed']:
        print(Path(bundle['path']).name, bundle.get('counts', {}), bundle['errors'])
    print(f"Unresolved speech entries: {len(data['unresolved'])}; restored: {data['restored_entries']}")


if __name__ == '__main__':
    main()
