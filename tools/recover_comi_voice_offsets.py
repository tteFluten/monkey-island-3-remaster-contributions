#!/usr/bin/env python3
"""Recover displaced COMI speech using coherent runs of compression-table matches.

Preparation only. Install/rollback with restore_comi_voices.py and the same work-dir.
Matching lengths alone are never enough: require repeated offset evidence, adjacent
entries, and successful decoding with the game's sanitizer-instrumented codec.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess

from audit_comi_audio import audit, CODECS
from comi_audio import atomic_json, digest
from restore_comi_voices import build_decoder


def scan(data):
    found = {}
    position = 0
    while True:
        position = data.find(b'COMP', position)
        if position < 0:
            return found
        offset = position
        position += 4
        if offset + 16 > len(data):
            continue
        count, _, last = struct.unpack_from('>III', data, offset + 4)
        if not 0 < count < 4096 or last > 8192 or offset + 16 + count * 16 > len(data):
            continue
        rows = [struct.unpack_from('>IIII', data, offset + 16 + i * 16) for i in range(count)]
        # Actual COMI tables describe consecutive compressed blocks. Enforce this
        # stronger constraint before treating random COMP bytes as a candidate.
        end = 16 + count * 16
        for start, size, codec, _ in rows:
            if start != end or size == 0 or offset + start + size > len(data) or codec not in CODECS:
                break
            end = start + size
        else:
            found[offset] = dict(offset=offset, size=end, blocks=count, last_block_bytes=last)


def infer_matches(entries, candidates, minimum_run=3):
    indexed = {e['offset'] for e in entries if e['status'] == 'valid_structure'}
    candidates = {offset: c for offset, c in candidates.items() if offset not in indexed}
    by_size = defaultdict(list)
    for candidate in candidates.values():
        by_size[candidate['size']].append(candidate)
    votes = Counter()
    damaged = [e for e in entries if e['status'] == 'invalid']
    for entry in damaged:
        options = by_size[entry['size']]
        if len(options) == 1:
            votes[options[0]['offset'] - entry['offset']] += 1
    shifts = {delta: count for delta, count in votes.items() if delta and count >= minimum_run}
    matches = []
    for entry in damaged:
        options = [candidates[entry['offset'] + shift] for shift in shifts
                   if entry['offset'] + shift in candidates
                   and candidates[entry['offset'] + shift]['size'] == entry['size']]
        if len(options) == 1:
            candidate = options[0]
            matches.append(dict(**entry, recovered_offset=candidate['offset'],
                                shift=candidate['offset'] - entry['offset']))
    runs = []
    for match in matches:
        if (not runs or match['index'] != runs[-1][-1]['index'] + 1
                or match['shift'] != runs[-1][-1]['shift']
                or match['recovered_offset'] != runs[-1][-1]['recovered_offset'] + runs[-1][-1]['size']):
            runs.append([])
        runs[-1].append(match)
    accepted = [entry for run in runs if len(run) >= minimum_run for entry in run]
    return accepted, shifts, [dict(first=run[0]['name'], last=run[-1]['name'], count=len(run),
                                  shift=run[0]['shift']) for run in runs if len(run) >= minimum_run]


def equivalent_texts(target, name, donor):
    if name == donor or name[2:4] != donor[2:4]:
        raise ValueError('Equivalent lines must be different entries from the same character')
    texts = {name: set(), donor: set()}
    for disc in (1, 2):
        raw = (target / f'.playtest/game/COMI.LA{disc}').read_bytes()
        for entry in texts:
            token = b'/' + entry.removesuffix('.IMX').encode('ascii') + b'/'
            start = 0
            while (start := raw.find(token, start)) >= 0:
                start += len(token)
                end = raw.find(b'\0', start)
                if end >= 0:
                    texts[entry].add(raw[start:end].decode('latin1'))
    normalized = [{tuple(re.findall(r'[a-z0-9]+', text.lower())) for text in values} for values in texts.values()]
    if (any(len(values) != 1 for values in texts.values()) or not normalized[0]
            or any(not words for words in normalized[0]) or normalized[0] != normalized[1]):
        raise ValueError('Equivalent lines do not have the same spoken words')
    return {entry: next(iter(values)) for entry, values in texts.items()}


def prepare(target, source, work, workers=6, equivalents=(), quarantine=()):
    if (work / 'repair.json').exists():
        raise ValueError('Use a new work directory; preserve existing repair/rollback evidence')
    work.mkdir(parents=True, exist_ok=True)
    original = audit(source)
    if original['errors']:
        raise ValueError('Invalid source bundle directory')
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != original['sha256']:
        raise ValueError('Source changed during inspection')
    matches, shifts, runs = infer_matches(original['entries'], scan(data))
    current_path = target / '.playtest/game/RESOURCE/VOXDISK1.BUN'
    current = audit(current_path)
    current_lookup = {e['name']: e for e in current['entries']}
    if current['errors'] or [(e['name'], e['index']) for e in current['entries']] != [
            (e['name'], e['index']) for e in original['entries']]:
        raise ValueError('Target and source bundle directories do not match')
    # Every original healthy payload must still agree; previously repaired entries
    # provide independent byte-for-byte anchors for the inferred displacement.
    for entry in original['entries']:
        if entry['status'] == 'valid_structure' and entry['sha256'] != current_lookup[entry['name']].get('sha256'):
            raise ValueError('Target healthy payload differs: ' + entry['name'])
    anchors = []
    needed = []
    for entry in matches:
        payload = data[entry['recovered_offset']:entry['recovered_offset'] + entry['size']]
        checksum = hashlib.sha256(payload).hexdigest()
        current_entry = current_lookup[entry['name']]
        if current_entry['status'] == 'valid_structure':
            if checksum != current_entry['sha256']:
                raise ValueError('Displacement disagrees with previously repaired entry: ' + entry['name'])
            anchors.append(entry['name'])
        else:
            needed.append(entry)
    decoder = build_decoder(target, work)
    scratch = work / 'validation'
    scratch.mkdir()
    current_data = current_path.read_bytes()
    if hashlib.sha256(current_data).hexdigest() != current['sha256']:
        raise ValueError('Target changed during preparation')
    for pair in equivalents:
        name, donor = pair.split('=', 1)
        if name not in current_lookup or donor not in current_lookup:
            raise ValueError('Equivalent line not found in target bundle')
        if any(entry['name'] == name for entry in needed):
            raise ValueError('Equivalent line overlaps an offset candidate')
        if current_lookup[donor]['status'] != 'valid_structure':
            raise ValueError('Equivalent donor has invalid structure')
        text = equivalent_texts(target, name, donor)
        needed.append(dict(**current_lookup[name], recovered_offset=current_lookup[donor]['offset'],
                           replacement_size=current_lookup[donor]['size'], shift=None,
                           equivalent_donor=donor, equivalent_texts=text))

    def validate(entry):
        compressed, decoded = scratch / (entry['name'] + '.comp'), scratch / (entry['name'] + '.imus')
        origin = current_data if 'equivalent_donor' in entry else data
        size = entry.get('replacement_size', entry['size'])
        payload = origin[entry['recovered_offset']:entry['recovered_offset'] + size]
        compressed.write_bytes(payload)
        result = subprocess.run([str(decoder), str(compressed), str(decoded)], capture_output=True, timeout=20,
                                env={**os.environ, 'UBSAN_OPTIONS': 'halt_on_error=1'})
        raw = decoded.read_bytes() if decoded.exists() else b''
        ok = (result.returncode == 0 and not result.stderr and raw[:4] == b'iMUS' and raw[8:12] == b'MAP '
              and b'FRMT' in raw[:256] and b'DATA' in raw)
        record = dict(name=entry['name'], index=entry['index'], source_offset=entry['recovered_offset'],
                      size=size, shift=entry['shift'], payload_sha256=hashlib.sha256(payload).hexdigest(),
                      decoded_sha256=hashlib.sha256(raw).hexdigest() if ok else None,
                      decode_ok=ok, diagnostic=result.stderr.decode(errors='replace')[:2000])
        if 'equivalent_donor' in entry:
            record.update(equivalent_donor=entry['equivalent_donor'], equivalent_texts=entry['equivalent_texts'])
        compressed.unlink()
        decoded.unlink(missing_ok=True)
        return record

    with ThreadPoolExecutor(max_workers=workers) as pool:
        validation = list(pool.map(validate, needed))
    repairs = [r for r in validation if r['decode_ok']]
    rejected = [r for r in validation if not r['decode_ok']]
    quarantined = []
    for name in quarantine:
        if name not in current_lookup or any(r['name'] == name for r in repairs):
            raise ValueError('Invalid quarantine selection')
        entry = current_lookup[name]
        compressed, decoded = scratch / (name + '.comp'), scratch / (name + '.imus')
        compressed.write_bytes(current_data[entry['offset']:entry['offset'] + entry['size']])
        result = subprocess.run([str(decoder), str(compressed), str(decoded)], capture_output=True, timeout=20,
                                env={**os.environ, 'UBSAN_OPTIONS': 'halt_on_error=1'})
        if result.returncode == 0 and not result.stderr:
            raise ValueError('Refusing to quarantine a decodable entry: ' + name)
        quarantined.append(dict(name=name, index=entry['index'], original_sha256=entry.get('sha256'),
                               payload_sha256=hashlib.sha256(bytes(16)).hexdigest(),
                               reason='Native decoder failed; invalid header triggers existing safe skip',
                               diagnostic=result.stderr.decode(errors='replace')[:2000]))
        compressed.unlink()
        decoded.unlink(missing_ok=True)
    if not repairs:
        raise ValueError('No independently validated displaced entries to recover')
    prepared = work / 'VOXDISK1.BUN'
    shutil.copyfile(current_path, prepared)
    if digest(prepared) != current['sha256']:
        raise ValueError('Target changed during preparation')
    with prepared.open('r+b') as f:
        f.seek(4)
        directory = struct.unpack('>I', f.read(4))[0]
        for record in repairs:
            f.seek(0, 2)
            offset = f.tell()
            start, size = record['source_offset'], record['size']
            origin = current_data if 'equivalent_donor' in record else data
            f.write(origin[start:start + size])
            f.seek(directory + record['index'] * 20 + 12)
            f.write(struct.pack('>II', offset, size))
        for record in quarantined:
            f.seek(0, 2)
            offset = f.tell()
            f.write(bytes(16))
            f.seek(directory + record['index'] * 20 + 12)
            f.write(struct.pack('>II', offset, 16))
    checked = audit(prepared)
    updates = {record['name']: record for record in repairs}
    quarantine_updates = {record['name']: record for record in quarantined}
    for before, after in zip(current['entries'], checked['entries']):
        expected = {**updates, **quarantine_updates}.get(before['name'], {}).get('payload_sha256', before.get('sha256'))
        if after.get('sha256') != expected or (before['name'] in updates and after['status'] != 'valid_structure'):
            raise ValueError('Prepared bundle verification failed: ' + before['name'])
    prior_count = sum(e['status'] == 'invalid' and current_lookup[e['name']]['status'] == 'valid_structure'
                      for e in original['entries'])
    manifest = dict(version=1, status='prepared', recovery_method='displaced compressed payloads',
        target_workspace=str(target), source_bundle=str(source), source_sha256=original['sha256'],
        original_sha256=current['sha256'], prepared_sha256=checked['sha256'],
        donor_sha256=digest(current_path.with_name('VOXDISK2.BUN')), inferred_shifts=shifts,
        coherent_runs=runs, previously_repaired_anchors=anchors, repairs=repairs, rejected=rejected,
        quarantined=quarantined,
        total_restored_entries=prior_count + len(repairs), remaining_invalid=checked['counts'].get('invalid', 0))
    atomic_json(work / 'repair.json', manifest)
    print(f"Prepared {len(repairs)} additional repairs; rejected {len(rejected)} undecodable candidates; "
          f"{manifest['remaining_invalid']} invalid entries remain", flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-workspace', type=Path, required=True)
    parser.add_argument('--source-bundle', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--equivalent-line', action='append', default=[], metavar='TARGET.IMX=DONOR.IMX')
    parser.add_argument('--quarantine-invalid', action='append', default=[], metavar='ENTRY.IMX')
    args = parser.parse_args()
    prepare(args.target_workspace.resolve(), args.source_bundle.resolve(), args.work_dir.resolve(),
            equivalents=args.equivalent_line, quarantine=args.quarantine_invalid)
