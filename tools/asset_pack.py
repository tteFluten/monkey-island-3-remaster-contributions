#!/usr/bin/env python3
"""Verify, install, and roll back the versioned remaster pack without downloading media."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def within(root, relative):
    root = root.resolve()
    parts = PurePosixPath(relative)
    if not relative or parts.is_absolute() or '..' in parts.parts or '\\' in relative:
        raise ValueError('Invalid relative path: ' + relative)
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes workspace: ' + relative)
    # Never replace a symlink or walk through one, even if it points inside the workspace.
    if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
        raise ValueError('Symlink in asset path: ' + relative)
    return path


def destination(root, relative):
    if not relative.startswith(('.playtest/hd/', 'upscaled/imported/', 'output/topaz-batch/4x/', 'output/topaz-batch/cleaned/')) and relative not in {
        '.playtest/game/RESOURCE/VOXDISK1.BUN', '.playtest/state.json',
        'output/topaz-batch/manifest.json', 'output/topaz-scenes/plan.json'}:
        raise ValueError('Unsupported installation destination: ' + relative)
    return within(root, relative)


def atomic_json(path, value):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(tmp, path)


def verify(root, media=False):
    manifest = json.loads((root / 'assets/manifest.json').read_text())
    if manifest.get('version') != 1: raise ValueError('Unsupported asset manifest version')
    index = {row['path']: row for row in manifest['files']}
    for row in manifest['files']:
        if row.get('derived_from'):
            source = index.get(row['derived_from'])
            if not source or not source.get('canonical'):
                raise ValueError('Runtime has no canonical master: ' + row['path'])
            if row['transform'].get('source_sha256') != source['sha256']:
                raise ValueError('Runtime derived from an outdated master: ' + row['path'])
            if row['transform']['kind'] == 'copy' and row['sha256'] != source['sha256']:
                raise ValueError('Runtime copy disagrees with canonical master: ' + row['path'])
    seen, destinations, checked_media = set(), set(), set()
    videos = {}
    staging = root / 'assets/metadata/video-staging.json'
    if staging.exists(): videos = {r['file']: r for r in json.loads(staging.read_text())['records']}
    for row in manifest['files']:
        name = row['path']
        if name in seen: raise ValueError('Duplicate asset path: ' + name)
        seen.add(name)
        path = within(root, name)
        if not path.is_file() or path.stat().st_size != row['bytes'] or digest(path) != row['sha256']:
            raise ValueError('Missing or corrupt asset (run git lfs pull): ' + name)
        if row.get('destination'):
            target = row['destination']
            destination(root, target)
            if target in destinations: raise ValueError('Duplicate destination: ' + target)
            destinations.add(target)
        if not media or row['sha256'] in checked_media: continue
        checked_media.add(row['sha256'])
        if path.suffix.lower() == '.png':
            from PIL import Image
            with Image.open(path) as im:
                im.load()
                if im.format != 'PNG' or not all(im.size): raise ValueError('Invalid PNG: ' + name)
                if row.get('image') and row['image'] != dict(width=im.width, height=im.height, mode=im.mode):
                    raise ValueError('Image disagrees with manifest: ' + name)
        elif path.suffix.lower() == '.wav':
            with wave.open(str(path), 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (2, 2, 44100):
                    raise ValueError('Expected stereo PCM16 44.1 kHz: ' + name)
                expected = audio.getnframes() * 4
                if len(audio.readframes(audio.getnframes())) != expected: raise ValueError('Truncated WAV: ' + name)
        elif path.suffix.lower() == '.mp4':
            streams = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)]))['streams']
            video = [s for s in streams if s['codec_type'] == 'video']
            if len(video) != 1: raise ValueError('Expected one video stream: ' + name)
            expected = videos.get(path.name)
            if expected:
                from fractions import Fraction
                s = video[0]
                if (s['width'], s['height'], int(s['nb_frames'])) != (expected['width'], expected['height'], expected['frames']) or Fraction(s['avg_frame_rate']) != expected['fps']:
                    raise ValueError('Video disagrees with staging metadata: ' + name)
    return manifest


def stopped(target):
    owner = target / '.playtest/engine.lock/owner.json'
    if owner.exists():
        value = json.loads(owner.read_text())
        for key in ['serverPid', 'gamePid']:
            if not value.get(key): continue
            try: os.kill(value[key], 0)
            except ProcessLookupError: continue
            raise ValueError('Stop the target workshop/game before installation or rollback')
    binary = str(target / '.playtest/engine/build/scummvm')
    lines = subprocess.check_output(['ps', '-axo', 'command='], text=True).splitlines()
    if any(line.startswith(binary) for line in lines):
        raise ValueError('Stop the target native game first')


@contextlib.contextmanager
def locked(target):
    local = within(target, '.playtest')
    local.mkdir(parents=True, exist_ok=True)
    with (local / 'asset-pack.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stopped(target)
        yield


def installation_plan(root, target, manifest):
    result = []
    for row in manifest['files']:
        if not row.get('destination'): continue
        path = destination(target, row['destination'])
        before = digest(path) if path.is_file() else None
        if row.get('workspace_paths'):
            value = json.loads(within(root, row['path']).read_text())
            for key in row['workspace_paths']:
                if key not in {'source_root', 'source_batch'}: raise ValueError('Unsupported workspace path field')
                value[key] = str(within(target, value[key]))
            data = (json.dumps(value, indent=2) + '\n').encode()
            after = hashlib.sha256(data).hexdigest()
            if before != after: result.append(dict(destination=row['destination'], before=before, after=after, data=data))
            continue
        if row.get('compatible_input_sha256') and before not in {*row['compatible_input_sha256'], row['sha256']}:
            raise ValueError('Unsupported or missing original voice bundle; import the matching English game edition first')
        if before != row['sha256']:
            result.append(dict(destination=row['destination'], source=row['path'], before=before, after=row['sha256']))
    template = root / 'assets/metadata/workshop-state.json'
    if template.exists():
        state_path = destination(target, '.playtest/state.json')
        old = json.loads(state_path.read_text()) if state_path.exists() else {}
        packaged = json.loads(template.read_text())
        settings = dict(disc1=str(Path.home() / 'Desktop/monkey/monkey3-1.iso'),
                        disc2=str(Path.home() / 'Desktop/monkey/monkey3-2.iso'),
                        backgroundFolder=str(target / 'assets/masters/backgrounds'), characterPack='topaz')
        settings.update(old.get('settings', {}))
        state = dict(old, settings=settings,
                     selections={**packaged['selections'], **old.get('selections', {})},
                     variants={**packaged['variants'], **old.get('variants', {})})
        # An authored replacement upgrades only its known predecessor. Keep
        # custom selections, the original-game choice, and fallback variants.
        for key, variant in packaged['variants'].items():
            predecessor = variant.get('params', {}).get('replacesVariantId')
            if predecessor and state['selections'].get(variant['assetId']) == predecessor:
                state['selections'][variant['assetId']] = key
        # Final backgrounds explicitly retire that room's older selections.
        # Preserve local variants and selections for every other asset.
        for key, variant in packaged['variants'].items():
            if variant.get('params', {}).get('finalBackground') is not True: continue
            asset = variant['assetId']
            state['variants'] = {k: v for k, v in state['variants'].items() if v['assetId'] != asset}
            state['variants'][key] = variant
            state['selections'][asset] = key
        data = (json.dumps(state, indent=2) + '\n').encode()
        before = digest(state_path) if state_path.exists() else None
        after = hashlib.sha256(data).hexdigest()
        if before != after: result.append(dict(destination='.playtest/state.json', before=before, after=after, data=data))
    return result


def install(root, target, dry_run=False):
    manifest = verify(root)
    stopped(target)
    if dry_run:
        plan = installation_plan(root, target, manifest)
        return dict(dry_run=True, changed_files=len(plan), destinations=[r['destination'] for r in plan])
    with locked(target):
        # Do not let a second transaction overwrite an interrupted installation.
        receipts = within(target, '.playtest/asset-pack-backups')
        if receipts.exists():
            for p in receipts.glob('*/receipt.json'):
                if json.loads(p.read_text())['status'] == 'applying':
                    raise ValueError('Roll back interrupted transaction first: ' + str(p.parent))
        plan = installation_plan(root, target, manifest)
        if not plan: return dict(changed_files=0, status='already-installed')
        transaction = receipts / uuid.uuid4().hex
        transaction.mkdir(parents=True)
        journal = dict(version=1, status='preparing', files=[])
        receipt = transaction / 'receipt.json'
        atomic_json(receipt, journal)
        for index, row in enumerate(plan):
            current = destination(target, row['destination'])
            stage = transaction / (str(index) + '.new')
            if 'data' in row: stage.write_bytes(row.pop('data'))
            else: shutil.copyfile(within(root, row['source']), stage)
            if digest(stage) != row['after']: raise ValueError('Pack changed while staging: ' + row['destination'])
            row['backup'] = str(index) + '.old'
            row['stage'] = stage.name
            if row['before'] is not None:
                shutil.copyfile(current, transaction / row['backup'])
                if digest(transaction / row['backup']) != row['before']: raise ValueError('Target changed during backup')
            journal['files'].append(row)
        journal['status'] = 'applying'
        atomic_json(receipt, journal)
        try:
            for row in journal['files']:
                path = destination(target, row['destination'])
                if (digest(path) if path.exists() else None) != row['before']: raise ValueError('Target changed during installation')
                path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(transaction / row['stage'], path)
        except BaseException:
            restore(target, transaction, journal)
            raise
        journal['status'] = 'installed'
        atomic_json(receipt, journal)
        return dict(changed_files=len(plan), status='installed', transaction=transaction.name)


def restore(target, transaction, journal):
    # Preflight every target and backup before restoring anything.
    for row in journal['files']:
        path = destination(target, row['destination'])
        current = digest(path) if path.exists() else None
        if current not in {row['before'], row['after']}: raise ValueError('Locally edited file blocks rollback: ' + row['destination'])
        if row['before'] is not None:
            backup = within(transaction, row['backup'])
            if not backup.is_file() or digest(backup) != row['before']: raise ValueError('Missing/corrupt rollback backup')
    for row in reversed(journal['files']):
        path = destination(target, row['destination'])
        if (digest(path) if path.exists() else None) == row['before']: continue
        if row['before'] is None: path.unlink()
        else:
            temporary = path.with_name(path.name + '.restore.tmp')
            shutil.copyfile(within(transaction, row['backup']), temporary)
            os.replace(temporary, path)
    journal['status'] = 'rolled-back'
    atomic_json(transaction / 'receipt.json', journal)


def rollback(target, transaction_id):
    if not transaction_id or any(c not in '0123456789abcdef' for c in transaction_id): raise ValueError('Invalid transaction ID')
    with locked(target):
        transaction = within(target, '.playtest/asset-pack-backups/' + transaction_id)
        journal = json.loads((transaction / 'receipt.json').read_text())
        if journal['status'] == 'rolled-back': return dict(status='already-rolled-back')
        if journal['status'] not in {'installed', 'applying'}: raise ValueError('Transaction did not reach installation')
        restore(target, transaction, journal)
        return dict(status='rolled-back', transaction=transaction_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('verify'); check.add_argument('--media', action='store_true')
    put = commands.add_parser('install'); put.add_argument('--target-workspace', type=Path, required=True); put.add_argument('--dry-run', action='store_true')
    undo = commands.add_parser('rollback'); undo.add_argument('--target-workspace', type=Path, required=True); undo.add_argument('--transaction', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'verify':
            manifest = verify(args.root.resolve(), args.media)
            result = dict(verified_files=len(manifest['files']), logical_bytes=manifest.get('logical_bytes'), unique_bytes=manifest.get('unique_bytes'))
        elif args.command == 'install': result = install(args.root.resolve(), args.target_workspace.resolve(), args.dry_run)
        else: result = rollback(args.target_workspace.resolve(), args.transaction)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__': main()
