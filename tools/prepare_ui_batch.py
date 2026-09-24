#!/usr/bin/env python3
"""Select supplied cursor/navigation and inventory art; no fonts, menus or API calls."""
import argparse
import json
from pathlib import Path


def prepare(root):
    records = json.loads((root / 'manifest.json').read_text())['records']
    sources = [r['source'] for r in records if r['source'].startswith('objects/0003_')]
    by_source = {r['source']: r for r in records}
    if not sources:
        raise ValueError('Prepare the supplied game assets first')
    # Room 3 is COMI's shared inventory/cursor resource room. Room 92 is the
    # save/load/options artwork and is intentionally excluded from this batch.
    selection = list(dict.fromkeys(by_source[s]['canonical'] for s in sources))
    for source in selection:
        if source not in by_source or not (root / 'cleaned' / source).is_file():
            raise ValueError(f'Missing prepared canonical image: {source}')
    scope = dict(model='Wonder 3.5', scale=6, enhancement='high',
                 sources=sources, unique_inputs=len(selection),
                 excluded=['save/load/options artwork', 'fonts', 'backgrounds', 'characters'])
    for filename, value in [('ui-scope.json', scope), ('ui-selection.json', selection)]:
        temporary = root / (filename + '.tmp')
        temporary.write_text(json.dumps(value, indent=2) + '\n')
        temporary.replace(root / filename)
    print(f'Prepared {len(sources)} UI images from {len(selection)} unique inputs; no API calls.')
    return scope


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('output/topaz-batch'))
    prepare(parser.parse_args().root)
