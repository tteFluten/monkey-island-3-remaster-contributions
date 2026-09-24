#!/usr/bin/env python3
"""Read-only coverage audit for cannon/waterline, including native unplanned cels."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from prepare_topaz import chunks
from quiver_extract import resources
from topaz_scenes import read

ROOMS = (9, 11)
# These inventory resources support the opening cannon/waterline interactions.
ITEMS = ('two-balloons', 'string-balloon', 'hook', 'ramrod', 'cutlass', 'skeleton-arm')


def audit(root):
    game = root / '.playtest/game'
    plan = read(root / 'output/topaz-scenes/plan.json')
    entries = {e['source']: e for s in plan['scenes'] for e in s['sources']}
    installed = read(root / '.playtest/draft-install/receipt.json')['assets']
    index = next(p for t, _, p in chunks((game / 'COMI.LA0').read_bytes()) if t == 'DCOS')
    count = struct.unpack_from('<I', index)[0]
    room_ids = index[4:4 + count]
    selected = [i for i, room in enumerate(room_ids) if room in ROOMS] + [2]
    native = []
    for cid, room, raw, fields, palette in resources(game, selected):
        cels = struct.unpack('<6H', fields['AKHD'][:12])[3]
        native.append(dict(costume=cid, resource_room=room, cels=cels,
                           sources=[f'costumes/LFLF_{room:04}_AKOS_{cid:04}_frame_{i}.png'
                                    for i in range(cels)]))
    scopes = {}
    for room in ROOMS:
        sources = {s for r in native if r['resource_room'] == room or r['costume'] == 2
                   for s in r['sources']}
        sources.update(e['source'] for scene in plan['scenes'] if scene['room'] == room for e in scene['sources'])
        sources.update('objects/' + p.name for p in (root / 'extracted/objects').glob(f'{room:04}_*.png'))
        for name in ITEMS:
            sources.update('objects/' + p.name for p in (root / 'extracted/objects').glob(f'0003_{name}-icon-object_*.png'))
        rows = []
        for source in sorted(sources):
            asset = installed.get(source, {})
            rows.append(dict(source=source, planned=source in entries,
                             state=asset.get('state', 'missing'),
                             validation_passed=asset.get('validation_passed', False),
                             sha256=asset.get('sha256'),
                             visual_approval='not-established-by-this-audit'))
        background = root / f'.playtest/hd/backgrounds/bg_{room:04}.png'
        scopes[str(room)] = dict(sources=len(rows), states=dict(Counter(r['state'] for r in rows)),
                                unplanned=sum(not r['planned'] for r in rows),
                                background_installed=background.exists(), assets=rows)
    missing = [s for r in native for s in r['sources'] if s not in entries]
    return dict(rooms=list(ROOMS), broad_continuation=('paused' if (root / 'output/topaz-scenes/stop-after-current').exists() else 'not_paused'), scene_signoff=False,
                native_resources=native, native_cels=sum(r['cels'] for r in native),
                native_cels_missing_from_previous_plan=len(missing), unplanned_native_sources=missing,
                scenes=scopes, notes=[
                    'Resource ownership plus shared Guybrush and opening inventory icons; runtime interaction review remains required.',
                    'Missing means no selected Topaz draft. Native/legacy fallback may still be playable.',
                    'Validation and installation are not visual or animation approval.',
                    'Background checks establish installation only, not quality approval.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('.context/scene-focus/coverage.json'))
    args = parser.parse_args()
    report = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('native_resources','unplanned_native_sources','scenes')}))
    for room, scene in report['scenes'].items():
        print(room, {k:v for k,v in scene.items() if k != 'assets'})


if __name__ == '__main__':
    main()
