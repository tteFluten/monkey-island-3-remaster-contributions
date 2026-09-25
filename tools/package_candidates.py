#!/usr/bin/env python3
"""Package a reviewed list of replacement candidates as canonical 4x masters.

Input JSON: [{"source": "costumes/…png", "candidate": "path/to/4x.png", "state": "validated",
"method": "…", "reference": "optional cleaned input"}]. Each candidate must be exactly 4x its
source. Runtime copies, the cleaned reference, review and library records are updated with it;
object layers derived from a replaced object are rebuilt at their recorded offset, and alias
frames of a replaced frame follow it. Review states are recorded as given, never promoted.
"""
import argparse
import json
from pathlib import Path
import tempfile

from PIL import Image
from import_focus_outputs import Pack
from quiver_cannon import locked
from topaz_character_cutouts import digest
from topaz_scenes import ROOT


def source_size(root, source, reference):
    for path in (root/'assets/references/topaz-cleaned'/source, reference, root/'extracted'/source):
        if path and Path(path).exists():
            with Image.open(path) as image: return image.size
    raise FileNotFoundError(source)


def package(root, items, dry_run=False):
    changed, derived = [], []
    with locked(root/'.context/topaz-packaging'), tempfile.TemporaryDirectory() as temp:
        pack = Pack(root)
        library = {r['source']: r for r in pack.library['records']}
        for item in items:
            source, candidate = item['source'], Path(item['candidate'])
            reference = Path(item['reference']) if item.get('reference') else None
            width, height = source_size(root, source, reference)
            with Image.open(candidate) as image:
                if image.size != (width * 4, height * 4):
                    raise ValueError(f'{source}: candidate {image.size} is not 4x {width}x{height}')
            if dry_run: changed.append(source); continue
            pack.master(source, candidate, item['state'])
            pack.reference(source, reference)
            if reference and source not in pack.known:
                pack.library['records'].append(dict(source=source, cleaned_sha256=digest(reference), canonical=source,
                                                    origin='local-game-extraction'))
                pack.known.add(source)
            pack.reviews[source] = dict(master=str(candidate), sha256=digest(candidate), state=item['state'],
                                        validation_passed=item['state'] == 'validated', derived=False,
                                        method=item.get('method'), **item.get('details', {}))
            changed.append(source)
            # Object layers are the object pasted on a room canvas at a recorded offset.
            for layer in (r for r in library.values() if r.get('derived_from') == source and r.get('offset')):
                with Image.open(root/'assets/masters/topaz-4x'/layer['source']) as old, Image.open(candidate) as obj:
                    canvas = Image.new('RGBA', old.size)
                    canvas.paste(obj.convert('RGBA'), tuple(v * 4 for v in layer['offset']))
                out = Path(temp)/Path(layer['source']).name
                canvas.save(out)
                pack.master(layer['source'], out, 'draft-derived')
                pack.reviews[layer['source']] = dict(master='derived', sha256=digest(out), state='draft-derived',
                                                     derived=True, parent=source, offset=layer['offset'])
                derived.append(layer['source'])
            # Alias frames reuse their parent's artwork.
            for alias, review in list(pack.reviews.items()):
                if review.get('derived') and review.get('parent') == source and alias not in derived:
                    pack.master(alias, candidate, 'draft-derived')
                    pack.reviews[alias] = dict(review, sha256=digest(candidate), state='draft-derived')
                    derived.append(alias)
        if not dry_run: pack.save()
    return dict(packaged=len(changed), derived=derived, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('items', type=Path, help='JSON list of candidates')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true', help='write files; default is a dry run')
    args = parser.parse_args()
    print(json.dumps(package(args.root, json.loads(args.items.read_text()), not args.apply), indent=1))


if __name__ == '__main__':
    main()
