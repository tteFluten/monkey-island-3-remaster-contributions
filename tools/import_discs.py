#!/usr/bin/env python3
"""Import COMI discs without modifying their contents. Stdout carries progress."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def digest(file):
    h = hashlib.sha256()
    with open(file, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def copy_checked(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(source) != digest(target):
            raise ValueError(f'Conflicting disc files: {target.name}')
        return
    shutil.copyfile(source, target)


def validate_game(folder):
    required = ['COMI.LA0', 'COMI.LA1', 'COMI.LA2']
    required += ['RESOURCE/' + n for n in [
        'MUSDISK1.BUN', 'MUSDISK2.BUN', 'VOXDISK1.BUN', 'VOXDISK2.BUN',
        'FONT0.NUT', 'FONT1.NUT', 'FONT2.NUT', 'FONT3.NUT', 'FONT4.NUT']]
    missing = [p for p in required if not (folder / p).is_file() or (folder / p).stat().st_size == 0]
    if missing:
        raise ValueError('Missing game data: ' + ', '.join(missing))


def import_discs(discs, destination):
    for disc in discs:
        if not disc.is_file() or disc.suffix.lower() != '.iso':
            raise ValueError(f'ISO not found: {disc}')
    if discs[0].resolve() == discs[1].resolve():
        raise ValueError('Select two different discs')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='disc-import-', dir=destination.parent) as staging:
        game = Path(staging) / 'game'
        game.mkdir()
        for index, disc in enumerate(discs):
            print(f'Mounting disc {index + 1}', flush=True)
            mount = Path(staging) / f'mount-{index}'
            mount.mkdir()
            attached = False
            try:
                subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(disc)],
                               check=True, capture_output=True)
                attached = True
                for source in sorted(mount.rglob('*')):
                    if not source.is_file():
                        continue
                    parts = [part.upper() for part in source.relative_to(mount).parts]
                    name = parts[-1]
                    if name in ['COMI.LA0', 'COMI.LA1', 'COMI.LA2']:
                        relative = Path(name)
                    elif 'RESOURCE' in parts[:-1]:
                        relative = Path(*parts[parts.index('RESOURCE'):])
                    else:
                        continue
                    print(f'Copying {relative}', flush=True)
                    copy_checked(source, game / relative)
            finally:
                if attached:
                    result = subprocess.run(['hdiutil', 'detach', str(mount)], capture_output=True)
                    if result.returncode:
                        subprocess.run(['hdiutil', 'detach', '-force', str(mount)], check=True, capture_output=True)
        validate_game(game)
        # Keep an existing working import intact until the new import is complete.
        backup = destination.with_name(destination.name + '.previous')
        if backup.exists():
            raise ValueError(f'Recover or remove the previous import before retrying: {backup}')
        if destination.exists():
            destination.rename(backup)
        try:
            game.rename(destination)
        except Exception:
            if backup.exists():
                backup.rename(destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    print('Game data ready', flush=True)


if __name__ == '__main__':
    try:
        import_discs([Path(sys.argv[1]), Path(sys.argv[2])], Path(sys.argv[3]))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
