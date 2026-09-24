#!/usr/bin/env python3
"""Prepare, install, or roll back COMI-HD music. Requires ffmpeg and ffprobe."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
import wave

ARCHIVE = 'https://archive.org/metadata/the-curse-of-monkey-island-soundtrack'
DOWNLOAD = 'https://archive.org/download/the-curse-of-monkey-island-soundtrack/'
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / 'downloads/comi-audio'


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        for data in iter(lambda: f.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)


def mapping(target):
    header = target / '.playtest/engine/source/engines/scumm/imuse_digi/dimuse_extmusic_table.h'
    entries = re.findall(r'\{"([^"\n]+)",\s*"([^"\n]+)"\}', header.read_text())
    if not entries or len(dict(entries)) != len(entries):
        raise ValueError('Missing or ambiguous engine music table')
    for _, name in entries:
        if '/' in name or '\\' in name or name in ('.', '..'):
            raise ValueError('Unsafe soundtrack filename')
    return dict(entries), digest(header)


def download(url, dest, expected_size, expected_md5):
    """Resume between files; incomplete files are never treated as valid downloads."""
    if dest.exists() and dest.stat().st_size == expected_size and digest(dest, 'md5') == expected_md5:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + '.part')
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as response, part.open('wb') as output:
                shutil.copyfileobj(response, output)
            if part.stat().st_size != expected_size or digest(part, 'md5') != expected_md5:
                raise ValueError('Download checksum/size mismatch: ' + dest.name)
            part.replace(dest)
            return
        except (OSError, ValueError):
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def wav_info(path):
    with wave.open(str(path), 'rb') as wav:
        info = dict(channels=wav.getnchannels(), sample_width=wav.getsampwidth(),
                    sample_rate=wav.getframerate(), frames=wav.getnframes())
        if info['channels'] != 2 or info['sample_width'] != 2 or not info['frames']:
            raise ValueError('Expected nonempty stereo PCM16 WAV: ' + str(path))
        # Also detect a truncated data chunk, without loading the file into memory.
        frames = 0
        while True:
            chunk = wav.readframes(65536)
            if not chunk:
                break
            frames += len(chunk) // 4
        if frames != info['frames']:
            raise ValueError('Truncated WAV: ' + str(path))
        return info


def convert(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix('.part.wav')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source),
                    '-map', '0:a:0', '-vn', '-ac', '2', '-c:a', 'pcm_s16le', str(part)], check=True)
    info = wav_info(part)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'a:0',
                        '-show_entries', 'stream=sample_rate', '-of', 'json', str(source)]))
    if info['sample_rate'] != int(probe['streams'][0]['sample_rate']):
        raise ValueError('Conversion changed sample rate')
    part.replace(dest)
    return info


def prepare(target, cache, workers):
    cues, table_hash = mapping(target)
    cache.mkdir(parents=True, exist_ok=True)
    metadata_path = cache / 'archive-metadata.json'
    if not metadata_path.exists():
        with urllib.request.urlopen(ARCHIVE, timeout=60) as response:
            atomic_json(metadata_path, json.load(response))
    metadata = json.loads(metadata_path.read_text())
    files = {x['name']: x for x in metadata['files']}
    previous_path = cache / 'manifest.json'
    previous = json.loads(previous_path.read_text()).get('tracks', {}) if previous_path.exists() else {}
    manifest = dict(version=1, archive=ARCHIVE, engine_table_sha256=table_hash,
                    cues=cues, tracks={}, conversion=['-map', '0:a:0', '-vn', '-ac', '2', '-c:a', 'pcm_s16le'])

    def track(name):
        filename = name + '.flac'
        remote = files[filename]
        url = DOWNLOAD + urllib.parse.quote(filename)
        source, wav = cache / 'flac' / filename, cache / 'wav' / (name + '.wav')
        download(url, source, int(remote['size']), remote['md5'])
        sha = digest(source)
        old = previous.get(name, {})
        if (wav.exists() and old.get('source_sha256') == sha
                and old.get('wav_sha256') == digest(wav)):
            info = wav_info(wav)
        else:
            info = convert(source, wav)
        print('Ready: ' + name, flush=True)
        return name, dict(source_url=url, source_sha256=sha, source_md5=remote['md5'],
                          source_bytes=int(remote['size']), wav_sha256=digest(wav), **info)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(track, name) for name in sorted(set(cues.values()))]
        for future in as_completed(futures):
            name, record = future.result()
            manifest['tracks'][name] = record
            # Completed work remains reusable if the process is interrupted.
            atomic_json(previous_path, manifest)
    print(f"Prepared {len(manifest['tracks'])} tracks for {len(cues)} cues", flush=True)


def ensure_stopped(target):
    processes = subprocess.check_output(['ps', '-axo', 'command='], text=True)
    for line in processes.splitlines():
        if str(target / '.playtest/engine/build/scummvm') in line:
            raise RuntimeError('Stop the target playtest before installing or rolling back audio')


def tree_hashes(folder):
    return {str(p.relative_to(folder)): digest(p) for p in sorted(folder.rglob('*')) if p.is_file()}


def recover(local):
    """Recover the narrow interruption window between the two directory renames."""
    journal = local / 'audio-install.json'
    if not journal.exists():
        return None
    data = json.loads(journal.read_text())
    if data['status'] == 'rolling_back':
        active, backup = local / 'hd/audio', Path(data['backup'])
        disabled = Path(data['disabled_audio'])
        if not disabled.exists():
            if tree_hashes(active) != data['installed_hashes']:
                raise ValueError('Audio changed during interrupted rollback')
            active.rename(disabled)
        if data['had_audio'] and backup.exists() and not active.exists():
            backup.rename(active)
        data['status'] = 'rolled_back'
        atomic_json(journal, data)
    if data['status'] == 'staging':
        active, backup = local / 'hd/audio', Path(data['backup'])
        if backup.exists() and not active.exists():
            backup.rename(active)
        elif active.exists() and tree_hashes(active) == data['installed_hashes']:
            data['status'] = 'installed'
            atomic_json(journal, data)
            return data
        data['status'] = 'interrupted'
        atomic_json(journal, data)
    return data


def install(target, cache):
    ensure_stopped(target)
    local = target / '.playtest'
    previous = recover(local)
    cues, table_hash = mapping(target)
    manifest = json.loads((cache / 'manifest.json').read_text())
    if manifest['cues'] != cues or manifest['engine_table_sha256'] != table_hash:
        raise ValueError('Engine mapping changed; prepare again before installing')
    if set(manifest['tracks']) != set(cues.values()):
        raise ValueError('Soundtrack preparation is incomplete')
    for name, record in manifest['tracks'].items():
        wav = cache / 'wav' / (name + '.wav')
        if digest(wav) != record['wav_sha256']:
            raise ValueError('Staged WAV checksum mismatch: ' + name)
        wav_info(wav)
    active = local / 'hd/audio'
    if previous and previous['status'] == 'installed':
        if tree_hashes(active) == previous['installed_hashes']:
            if any(digest(active / (name + '.wav')) != record['wav_sha256']
                   for name, record in manifest['tracks'].items()):
                raise ValueError('Prepared soundtrack changed; roll back before installing the new revision')
            print('Audio already installed; original backup retained')
            return
        raise ValueError('Installed audio changed; inspect it before replacing or rolling back')
    transaction = local / 'audio-backups' / uuid.uuid4().hex
    transaction.mkdir(parents=True)
    stage, backup = transaction / 'stage', transaction / 'audio'
    if active.exists():
        shutil.copytree(active, stage)
    else:
        stage.mkdir()
    for name in manifest['tracks']:
        shutil.copy2(cache / 'wav' / (name + '.wav'), stage / (name + '.wav'))
    atomic_json(stage / '.comi-audio-manifest.json', manifest)
    journal = dict(version=1, status='staging', backup=str(backup), had_audio=active.exists(),
                   installed_hashes=tree_hashes(stage), cache=str(cache))
    atomic_json(local / 'audio-install.json', journal)
    ensure_stopped(target)
    active.parent.mkdir(parents=True, exist_ok=True)
    if active.exists():
        active.rename(backup)
    stage.rename(active)
    journal['status'] = 'installed'
    atomic_json(local / 'audio-install.json', journal)
    print('Installed into ' + str(active))


def rollback(target):
    ensure_stopped(target)
    local = target / '.playtest'
    data = recover(local)
    if data and data['status'] == 'rolled_back':
        print('Audio already rolled back')
        return
    if not data or data['status'] != 'installed':
        raise ValueError('No active installation to roll back')
    active, backup = local / 'hd/audio', Path(data['backup'])
    if tree_hashes(active) != data['installed_hashes']:
        raise ValueError('Audio changed after installation; refusing to overwrite changes')
    if data['had_audio'] and not backup.is_dir():
        raise ValueError('Original backup is missing')
    disabled = backup.parent / 'disabled-audio'
    data.update(status='rolling_back', disabled_audio=str(disabled))
    atomic_json(local / 'audio-install.json', data)
    active.rename(disabled)
    if data['had_audio']:
        backup.rename(active)
    data.update(status='rolled_back', disabled_audio=str(disabled))
    atomic_json(local / 'audio-install.json', data)
    print('Rolled back; downloaded soundtrack retained at ' + str(disabled))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install', 'rollback'])
    parser.add_argument('--target-workspace', required=True, type=Path)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE)
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 9))
    args = parser.parse_args()
    target, cache = args.target_workspace.resolve(), args.cache.resolve()
    lock_path = cache / '.prepare.lock' if args.action == 'prepare' else target / '.playtest/audio-tool.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'prepare':
            prepare(target, cache, args.workers)
        elif args.action == 'install':
            install(target, cache)
        else:
            rollback(target)


if __name__ == '__main__':
    main()
