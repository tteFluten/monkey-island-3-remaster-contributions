#!/usr/bin/env python3
"""Remove a verified sector insertion inside one compressed COMI voice entry.

Requires intact neighboring entries as offset anchors, a unique decoded result,
and at least one sector of identical source bytes supporting the splice.
Prepares a bundle for restore_comi_voices.py; never installs automatically.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from audit_comi_audio import audit
from comi_audio import atomic_json, digest
from restore_comi_voices import build_decoder


def select_verified(candidates):
    passing = [c for c in candidates if c['decode_ok']]
    if not passing:
        raise ValueError('No complete recording decodes after removing the insertion')
    if len({c['payload_sha256'] for c in passing}) != 1:
        raise ValueError('Ambiguous reconstruction: multiple different recordings decode')
    supported = [c for c in passing if c['equal_before'] + c['equal_after'] >= 2048]
    if not supported:
        raise ValueError('No matching source-sector overlap supports the reconstruction')
    return supported[0]


def prepare(target, source, previous_path, work, name, before_shift, after_shift):
    if work.exists():
        raise ValueError('Choose a new work directory to preserve previous evidence')
    delta = after_shift - before_shift
    if delta <= 0 or delta % 2048:
        raise ValueError('Expected a positive whole-sector insertion')
    previous = json.loads(previous_path.read_text())
    current_path = target / '.playtest/game/RESOURCE/VOXDISK1.BUN'
    current = audit(current_path)
    original = audit(source)
    if current['sha256'] != previous['prepared_sha256'] or original['sha256'] != previous['source_sha256']:
        raise ValueError('Bundle does not match the previous repair evidence')
    entry = next(e for e in original['entries'] if e['name'] == name)
    if current['entries'][entry['index']]['name'] != name:
        raise ValueError('Target directory does not match source')
    if current['entries'][entry['index']]['status'] != 'invalid':
        raise ValueError('Refusing to replace a structurally valid installed recording')
    if not 0 < entry['index'] < len(original['entries']) - 1:
        raise ValueError('Two neighboring entries are required as anchors')
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != original['sha256']:
        raise ValueError('Source changed during preparation')
    start = entry['offset'] + before_shift
    if start < 0 or start + entry['size'] + delta > len(raw):
        raise ValueError('Displacement exceeds source bounds')
    if raw[start:start+4] != b'COMP':
        raise ValueError('Shifted source has no COMP header')
    count = struct.unpack_from('>I', raw, start + 4)[0]
    table_size = 16 + count * 16
    if not 0 < count < 4096 or table_size >= entry['size']:
        raise ValueError('Invalid compression table')
    anchors = []
    for index, shift in [(entry['index'] - 1, before_shift), (entry['index'] + 1, after_shift)]:
        adjacent = original['entries'][index]
        at = adjacent['offset'] + shift
        payload = raw[at:at+adjacent['size']]
        if hashlib.sha256(payload).hexdigest() != current['entries'][index].get('sha256'):
            raise ValueError('Neighboring source bytes do not match an intact installed recording')
        anchors.append(adjacent['name'])
    work.mkdir(parents=True)
    decoder = build_decoder(target, work)
    candidates = []
    for cut in range(((start + table_size + 2047) // 2048) * 2048, start + entry['size'], 2048):
        payload = raw[start:cut] + raw[cut + delta:start + entry['size'] + delta]
        compressed, decoded = work / f'candidate-{cut}.comp', work / f'candidate-{cut}.imus'
        compressed.write_bytes(payload)
        result = subprocess.run([str(decoder), str(compressed), str(decoded)], capture_output=True, timeout=20,
                                env={**os.environ, 'UBSAN_OPTIONS': 'halt_on_error=1'})
        output = decoded.read_bytes() if decoded.exists() else b''
        ok = (result.returncode == 0 and not result.stderr and output[:4] == b'iMUS'
              and output[8:12] == b'MAP ' and b'FRMT' in output[:256] and b'DATA' in output)
        equal_before = equal_after = 0
        for k in range(1, min(cut - start, 32768) + 1):
            if raw[cut - k] != raw[cut + delta - k]:
                break
            equal_before += 1
        for k in range(min(start + entry['size'] - cut, 32768)):
            if raw[cut + k] != raw[cut + delta + k]:
                break
            equal_after += 1
        candidates.append(dict(cut=cut, removed_bytes=delta, decode_ok=ok, equal_before=equal_before,
            equal_after=equal_after, file=str(compressed), payload_sha256=hashlib.sha256(payload).hexdigest(),
            decoded_sha256=hashlib.sha256(output).hexdigest() if ok else None))
        decoded.unlink(missing_ok=True)
    atomic_json(work / 'splice-candidates.json', candidates)
    selected = select_verified(candidates)
    payload = Path(selected['file']).read_bytes()
    prepared = work / 'VOXDISK1.BUN'
    shutil.copyfile(current_path, prepared)
    if digest(prepared) != current['sha256']:
        raise ValueError('Installed bundle changed during preparation')
    with prepared.open('r+b') as f:
        f.seek(4)
        directory = struct.unpack('>I', f.read(4))[0]
        f.seek(0, 2)
        offset = f.tell()
        f.write(payload)
        f.seek(directory + entry['index'] * 20 + 12)
        f.write(struct.pack('>II', offset, len(payload)))
    checked = audit(prepared)
    for old, new in zip(current['entries'], checked['entries']):
        expected = selected['payload_sha256'] if old['name'] == name else old.get('sha256')
        if new.get('sha256') != expected:
            raise ValueError('Prepared bundle verification failed')
    repair = dict(name=name, index=entry['index'], method='verified duplicated-sector removal',
                  payload_sha256=selected['payload_sha256'], decoded_sha256=selected['decoded_sha256'],
                  source_offset=start, before_shift=before_shift, after_shift=after_shift,
                  removed_bytes=delta, anchors=anchors, accepted_splice=selected['cut'])
    manifest = dict(version=1, status='prepared', target_workspace=str(target), original_sha256=current['sha256'],
        prepared_sha256=checked['sha256'], donor_sha256=digest(current_path.with_name('VOXDISK2.BUN')),
        source_sha256=original['sha256'], previous_repair=str(previous_path), repairs=[repair],
        total_restored_entries=previous['total_restored_entries'] + 1,
        remaining_invalid=checked['counts'].get('invalid', 0))
    atomic_json(work / 'repair.json', manifest)
    print(f"Prepared verified repair for {name}; {manifest['remaining_invalid']} entries remain unavailable")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-workspace', required=True, type=Path)
    parser.add_argument('--source-bundle', required=True, type=Path)
    parser.add_argument('--previous-repair', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--before-shift', required=True, type=int)
    parser.add_argument('--after-shift', required=True, type=int)
    args = parser.parse_args()
    prepare(args.target_workspace.resolve(), args.source_bundle.resolve(), args.previous_repair.resolve(),
            args.work_dir.resolve(), args.entry, args.before_shift, args.after_shift)
