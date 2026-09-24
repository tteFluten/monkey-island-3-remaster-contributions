#!/usr/bin/env python3
"""Install completed UI outputs at the engine's 4x scale; preserve 6x masters."""
import argparse
import json
from pathlib import Path
from stage_topaz import stage


def stage_ui(batch, local):
    requested = json.loads((batch / 'ui-scope.json').read_text())['sources']
    ready = [s for s in requested if (batch / '6x' / s).is_file()]
    if not ready:
        raise ValueError('No completed UI images to stage')
    if any(not s.startswith('objects/0003_') for s in ready):
        raise ValueError('UI scope must only contain shared room-3 objects')
    scope = batch / 'ui-ready-scope.json'
    scope.write_text(json.dumps({'sources': ready}, indent=2) + '\n')
    stage(batch, local, scope, report_name='ui-staging.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=Path('output/topaz-batch'))
    parser.add_argument('--local', type=Path, default=Path('.playtest'))
    args = parser.parse_args()
    stage_ui(args.batch, args.local)
