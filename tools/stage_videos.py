#!/usr/bin/env python3
"""Validate and copy supplied cinematic replacements without changing originals."""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {'SINKSHP': 'SINKSHIP'}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def san_metadata(path):
    with path.open('rb') as stream:
        header = stream.read(800)
    if header[:4] != b'ANIM' or header[8:12] != b'AHDR' or len(header) < 792:
        raise ValueError(f'Invalid SAN header: {path}')
    return {'frames': struct.unpack_from('<H', header, 18)[0],
            'fps': struct.unpack_from('<H', header, 790)[0]}


def validate_video(video, original):
    if (video['width'], video['height']) != (2880, 2160):
        raise ValueError('Expected 2880 x 2160 supplied cinematic masters')
    if Fraction(video['r_frame_rate']) != original['fps'] or Fraction(video['avg_frame_rate']) != original['fps']:
        raise ValueError('Replacement frame rate must match original movie')
    frames = int(video['nb_frames'])
    # These supplied versions trim/add ten trailing black frames. Avoid silently
    # accepting an unrelated edit with substantially different timing.
    if frames <= 0 or abs(frames - original['frames']) > 10:
        raise ValueError('Replacement duration differs by more than ten frames')
    return frames


def stage(source, local, probe=None):
    probe = probe or shutil.which('ffprobe') or '/opt/homebrew/bin/ffprobe'
    movies = {p.stem.upper(): p for p in (local / 'game/RESOURCE').glob('*.SAN')}
    if not movies:
        raise ValueError('Import the game discs before staging movies')
    sources = {}
    for path in source.iterdir():
        if path.suffix.lower() != '.mp4':
            continue
        key = path.stem.upper()
        if key in sources:
            raise ValueError(f'Duplicate replacement movie: {key}')
        sources[key] = path
    expected = {ALIASES.get(name, name) for name in movies}
    if set(sources) != expected:
        raise ValueError(f'Movie names do not match: missing={sorted(expected - sources.keys())}, extra={sorted(sources.keys() - expected)}')
    records = []
    # Validate the complete pack before modifying the runtime directory.
    for name, san in sorted(movies.items()):
        path = sources[ALIASES.get(name, name)]
        metadata = json.loads(subprocess.check_output(
            [probe, '-v', 'error', '-show_streams', '-of', 'json', str(path)]))
        videos = [s for s in metadata['streams'] if s['codec_type'] == 'video']
        if len(videos) != 1:
            raise ValueError(f'Expected one video stream: {path}')
        original = san_metadata(san)
        frames = validate_video(videos[0], original)
        records.append({'san': san.name, 'file': path.stem.upper() + '.mp4',
                        'source': str(path.resolve()), 'sha256': digest(path),
                        'width': videos[0]['width'], 'height': videos[0]['height'],
                        'fps': original['fps'], 'frames': frames,
                        'originalFrames': original['frames']})
    destination = local / 'hd/videos'
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for record in records:
        target = destination / record['file']
        if target.exists() and digest(target) == record['sha256']:
            continue
        if target.exists():
            backup = local / 'backups' / ('videos-' + timestamp) / target.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        temporary = target.with_suffix('.mp4.tmp')
        try:
            shutil.copy2(record['source'], temporary)
            if digest(temporary) != record['sha256']:
                raise ValueError(f'Movie changed while copying: {record["source"]}')
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    receipt = local / 'video-staging.json'
    temporary = receipt.with_suffix('.tmp')
    temporary.write_text(json.dumps({'createdAt': timestamp, 'audio': 'original SAN',
                                    'timing': 'original SAN; hold final replacement frame if shorter',
                                    'records': records}, indent=2) + '\n')
    os.replace(temporary, receipt)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, default=Path.home() / 'Desktop/monkey/videos')
    parser.add_argument('--local', type=Path, default=ROOT / '.playtest')
    args = parser.parse_args()
    records = stage(args.source, args.local)
    for record in records:
        print(f'{record["san"]} -> {record["file"]}: {record["frames"]}/{record["originalFrames"]} frames')
    print(f'Staged {len(records)} cinematic replacements')
