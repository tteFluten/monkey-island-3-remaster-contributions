#!/usr/bin/env python3
"""Prepare missing English speech from an independently verified matching bundle.

Never installs automatically. Use restore_comi_voices.py install/rollback with
the resulting work directory. Media and source provenance remain outside Git.
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


def select_replacements(current, donor, original_takes=()):
    if current['errors'] or donor['errors']:
        raise ValueError('Invalid bundle directory')
    old, new = current['entries'], donor['entries']
    names = [e['name'] for e in old]
    if names != [e['name'] for e in new] or len(set(names)) != len(names):
        raise ValueError('Donor directory does not match installed edition')
    original_takes = set(original_takes)
    if not original_takes <= set(names):
        raise ValueError('Unknown original-take name')
    repairs, anchors = [], []
    for a, b in zip(old, new):
        if b['status'] not in ('valid_structure', 'metadata'):
            raise ValueError('Donor contains a damaged entry: ' + b['name'])
        if a['status'] == 'invalid' or a['name'] in original_takes:
            if b['status'] != 'valid_structure':
                raise ValueError('Cannot replace playable audio with metadata')
            repairs.append((a, b))
        elif a.get('sha256') != b.get('sha256'):
            raise ValueError('Healthy recording differs: ' + a['name'])
        elif a['status'] == 'valid_structure':
            anchors.append(a['name'])
    # An isolated matching filename is insufficient to establish language/edition.
    if len(anchors) < 100:
        raise ValueError('Insufficient identical healthy recordings to verify donor edition')
    if not repairs:
        raise ValueError('No entries need replacement')
    return repairs, anchors


def prepare(target, donor_path, previous_path, provenance_path, work, original_takes=()):
    if work.exists():
        raise ValueError('Use a new work directory to preserve previous repair evidence')
    current_path = target / '.playtest/game/RESOURCE/VOXDISK1.BUN'
    previous = json.loads(previous_path.read_text())
    current, donor = audit(current_path), audit(donor_path)
    if (previous['prepared_sha256'] != current['sha256'] or
            previous['target_workspace'] != str(target)):
        raise ValueError('Previous repair does not match target')
    provenance = json.loads(provenance_path.read_text())
    if provenance['downloaded_bundle_sha256'] != donor['sha256']:
        raise ValueError('Donor checksum does not match download provenance')
    selected, anchors = select_replacements(current, donor, original_takes)
    work.mkdir(parents=True)
    decoder = build_decoder(target, work)
    records = []
    with donor_path.open('rb') as source:
        for broken, replacement in selected:
            source.seek(replacement['offset'])
            payload = source.read(replacement['size'])
            if hashlib.sha256(payload).hexdigest() != replacement['sha256']:
                raise ValueError('Donor changed during preparation')
            compressed = work / (broken['name'] + '.comp')
            decoded = work / (broken['name'] + '.imus')
            compressed.write_bytes(payload)
            result = subprocess.run([str(decoder), str(compressed), str(decoded)],
                capture_output=True, timeout=30,
                env={**os.environ, 'UBSAN_OPTIONS': 'halt_on_error=1'})
            data = decoded.read_bytes() if decoded.exists() else b''
            if (result.returncode or result.stderr or data[:4] != b'iMUS' or
                    data[8:12] != b'MAP ' or b'FRMT' not in data[:256] or b'DATA' not in data):
                raise ValueError('Native decoder rejected ' + broken['name'])
            records.append(dict(name=broken['name'], index=broken['index'],
                method='matching English donor bundle', donor_offset=replacement['offset'],
                size=replacement['size'], payload_sha256=replacement['sha256'],
                decoded_sha256=digest(decoded), previously_unavailable=broken['status'] == 'invalid',
                replaces_alternate_take=broken['name'] in original_takes))
    prepared = work / 'VOXDISK1.BUN'
    shutil.copyfile(current_path, prepared)
    if digest(prepared) != current['sha256'] or digest(donor_path) != donor['sha256']:
        raise ValueError('Bundle changed during preparation')
    with prepared.open('r+b') as output:
        output.seek(4)
        directory = struct.unpack('>I', output.read(4))[0]
        for record in records:
            payload = (work / (record['name'] + '.comp')).read_bytes()
            output.seek(0, 2)
            offset = output.tell()
            output.write(payload)
            output.seek(directory + record['index'] * 20 + 12)
            output.write(struct.pack('>II', offset, len(payload)))
    checked = audit(prepared)
    if checked['errors'] or checked['counts'].get('invalid', 0):
        raise ValueError('Prepared bundle still has invalid entries')
    for result, expected in zip(checked['entries'], donor['entries']):
        if result.get('sha256') != expected.get('sha256'):
            raise ValueError('Prepared recording differs from verified donor')
    newly_restored = sum(r['previously_unavailable'] for r in records)
    manifest = dict(version=1, status='prepared', target_workspace=str(target),
        original_sha256=current['sha256'], prepared_sha256=checked['sha256'],
        donor_sha256=digest(current_path.with_name('VOXDISK2.BUN')),
        external_donor_sha256=donor['sha256'], external_donor=str(donor_path),
        source_provenance=provenance, previous_repair=str(previous_path),
        shared_healthy_identical=len(anchors), repairs=records,
        total_restored_entries=previous['total_restored_entries'] + newly_restored,
        newly_restored_entries=newly_restored, remaining_invalid=0,
        all_installed_entries_identical_to_donor=True)
    atomic_json(work / 'repair.json', manifest)
    print(f'Prepared {newly_restored} missing recordings and {len(records)-newly_restored} original takes; '
          f'{len(anchors)} intact recordings match donor exactly')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-workspace', required=True, type=Path)
    parser.add_argument('--donor-bundle', required=True, type=Path)
    parser.add_argument('--previous-repair', required=True, type=Path)
    parser.add_argument('--source-provenance', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--restore-original-take', action='append', default=[])
    args = parser.parse_args()
    prepare(args.target_workspace.resolve(), args.donor_bundle.resolve(), args.previous_repair.resolve(),
            args.source_provenance.resolve(), args.work_dir.resolve(), args.restore_original_take)
