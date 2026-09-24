#!/usr/bin/env python3
"""Extract and select cannon animation cels (costume 26) for direct 4x Topaz."""
import argparse
import fcntl
import json
import shutil
from pathlib import Path

from quiver_extract import extract
from prepare_topaz import digest


def prepare(root, game):
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    records = {r['source']: r for r in manifest['records']}
    extracted = root / 'extracted-cannon'
    assets = extract(game, extracted, [26])
    canonical = {r['cleaned_sha256']: r['canonical'] for r in records.values() if 'canonical' in r}
    sources = []
    for cel in assets['records']:
        name = cel['source']
        source = 'costumes/' + name
        sources.append(source)
        cleaned = extracted / 'cleaned' / name
        source_hash = digest(cleaned)
        if source in records:
            if records[source]['cleaned_sha256'] != source_hash:
                raise ValueError(f'Existing cannon source differs: {source}')
            continue
        target = root / 'cleaned' / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cleaned, target)
        indexed = extracted / 'indexed' / name
        record = dict(source=source, source_file=str(indexed.resolve()),
                      source_sha256=digest(indexed), cleaned_sha256=source_hash,
                      size=cel['size'], origin='local-game-extraction',
                      game_resource_sha256=assets['resources']['26']['sha256'],
                      canonical=canonical.setdefault(source_hash, source))
        records[source] = record
        manifest['records'].append(record)
    selection = list(dict.fromkeys(records[s]['canonical'] for s in sources))
    for name, data in [('manifest.json', manifest), ('cannon-sprites-selection.json', selection),
                       ('cannon-sprites-scope.json', dict(room=9, costume=26, scale=4, sources=sources))]:
        temporary = root / (name + '.tmp')
        temporary.write_text(json.dumps(data, indent=2) + '\n')
        temporary.replace(root / name)
    print(f'Prepared {len(sources)} cannon cels / {len(selection)} unique inputs for direct 4x processing.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--game', type=Path, default=Path('.playtest/game'))
    args = parser.parse_args()
    with (args.root / 'batch.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepare(args.root, args.game)
