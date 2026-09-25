#!/usr/bin/env python3
"""Package finished scene-focus Topaz outputs from another workspace without changing reviews.

Reads each focus batch's manifest.json, jobs.json, 4x/ and prepared/cleaned/ directly, so
outputs that were never installed locally are packaged as well. Review state follows the
automated result (validated/rejected; alias copies are draft-derived). An explicit user
approval is carried into artwork-review.json only where the source workspace's install
receipt records it for the same bytes. Existing canonical masters that differ are left
untouched and reported, never overwritten.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from PIL import Image
from quiver_cannon import atomic, locked
from topaz_character_cutouts import digest
from topaz_scenes import ROOT, read

FOCUS = 'output/topaz-scenes/focus-0009-0011'
EXTRACTION = '.context/scene-focus/extracted-missing'
APPROVAL = ('review_status', 'approved_by', 'approved_at')


def collect(workspace):
    """Finished outputs per source, verified against their job and cleaned-input hashes."""
    found, problems, unfinished = {}, [], []
    for batch in sorted((workspace/FOCUS).iterdir()):
        if not (batch/'jobs.json').exists(): continue
        jobs = read(batch/'jobs.json')
        for record in read(batch/'manifest.json')['records']:
            source = record['source']
            job, output = jobs.get(source, {}), batch/'4x'/source
            validation = job.get('validation')
            if not validation or not output.exists():
                unfinished.append(f'{batch.name}:{source}'); continue
            sha = digest(output)
            cleaned = batch/'prepared/cleaned'/source
            if sha != validation['sha256']:
                problems.append(f'{batch.name}:{source} output changed after validation'); continue
            if not cleaned.exists() or digest(cleaned) != record['cleaned_sha256']:
                problems.append(f'{batch.name}:{source} cleaned input missing or changed'); continue
            item = dict(master=output, sha256=sha, state='validated' if validation['passed'] else 'rejected',
                        validation=validation, validation_passed=validation['passed'], derived=False,
                        batch=batch.name, cleaned=cleaned, cleaned_sha256=record['cleaned_sha256'],
                        updated_at=job.get('updated_at', 0))
            if source not in found or item['updated_at'] >= found[source]['updated_at']:
                found[source] = item
    return found, problems, unfinished


def aliases(workspace, receipt):
    pairs = dict(read(workspace/FOCUS/'awaiting-continuation/plan.json', {}).get('aliases', {}))
    pairs.update({s: a['parent'] for s, a in receipt.items() if a.get('derived') and a.get('parent')})
    return pairs


def plan_import(root, workspace):
    receipt = read(workspace/'.playtest/draft-install/receipt.json', {'assets': {}})['assets']
    found, problems, unfinished = collect(workspace)
    for source, parent in aliases(workspace, receipt).items():
        if source in found or parent not in found: continue
        base = found[parent]
        cleaned = workspace/EXTRACTION/'cleaned'/Path(source).name
        found[source] = dict(base, state='draft-derived', derived=True, parent=parent, batch=base['batch'],
                             cleaned=cleaned if cleaned.exists() else None,
                             cleaned_sha256=digest(cleaned) if cleaned.exists() else None)
    for source, item in found.items():
        approved = receipt.get(source, {})
        if approved.get('review_status') == 'approved' and approved.get('sha256') == item['sha256']:
            item.update({k: approved[k] for k in APPROVAL if k in approved})
    manifest = read(root/'assets/manifest.json')
    index = {r['path']: r for r in manifest['files']}
    new, same, conflicts = {}, [], []
    for source, item in sorted(found.items()):
        existing = index.get('assets/masters/topaz-4x/' + source)
        if existing and existing['sha256'] == item['sha256']: same.append(source)
        elif existing: conflicts.append(source)
        else: new[source] = item
    return dict(new=new, same=same, conflicts=conflicts, problems=problems, unfinished=unfinished)


class Pack:
    """Manifest, review and library records, updated together; register() copies one packaged file."""
    def __init__(self, root):
        self.root = root
        self.manifest = read(root/'assets/manifest.json')
        self.index = {r['path']: r for r in self.manifest['files']}
        self.reviews = read(root/'assets/metadata/artwork-review.json')
        self.library = read(root/'assets/metadata/topaz-library.json')
        self.known = {r['source'] for r in self.library['records']}

    def register(self, name, origin, category, source, state, destination, **extra):
        target = self.root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        checksum = digest(origin)
        if not target.exists() or digest(target) != checksum: shutil.copy2(origin, target)
        with Image.open(target) as image:
            image.load()
            dimensions = dict(width=image.width, height=image.height, mode=image.mode)
        row = dict(path=name, sha256=checksum, bytes=target.stat().st_size, category=category,
                   source_id=source, review_status=state, destination=destination, image=dimensions, **extra)
        if name in self.index: self.index[name].update(row)
        else: self.manifest['files'].append(row); self.index[name] = row

    def master(self, source, origin, state):
        """Canonical 4x master plus its runtime copies (existing derived copies, else both Topaz packs)."""
        name = 'assets/masters/topaz-4x/' + source
        self.register(name, origin, 'masters/topaz-4x', source, state, 'output/topaz-batch/4x/' + source, canonical=True)
        runtime = [r['path'] for r in self.manifest['files'] if r.get('derived_from') == name]
        if not runtime and source.startswith('costumes/'):
            runtime = [f'assets/runtime/{pack}/{source.replace("_frame_", "_aframe_")}' for pack in ('topaz-cannon', 'topaz-crisp')]
        elif not runtime and source.startswith(('objects/', 'objects_layers/')):
            runtime = ['assets/runtime/' + source]  # engine: hd/objects/%04d_%s_%04d.png
        for path in runtime:
            self.register(path, origin, 'runtime/' + path.split('/')[2], source, state,
                          '.playtest/hd/' + path.split('/', 2)[2], derived_from=name,
                          transform=dict(kind='copy', source_sha256=digest(origin)))
        return name

    def reference(self, source, origin):
        name = 'assets/references/topaz-cleaned/' + source
        if origin and name not in self.index:
            self.register(name, origin, 'references/topaz-cleaned', source, 'original-reference',
                          'output/topaz-batch/cleaned/' + source)

    def save(self):
        self.library['records'].sort(key=lambda r: r['source'])
        for name, value in (('artwork-review.json', self.reviews), ('topaz-library.json', self.library)):
            path = 'assets/metadata/' + name
            atomic(self.root/path, value)
            self.index[path].update(sha256=digest(self.root/path), bytes=(self.root/path).stat().st_size)
        categories = defaultdict(lambda: dict(files=0, bytes=0)); unique = {}
        for row in self.manifest['files']:
            categories[row['category']]['files'] += 1
            categories[row['category']]['bytes'] += row['bytes']
            unique[row['sha256']] = row['bytes']
        self.manifest.update(categories=dict(categories), logical_bytes=sum(r['bytes'] for r in self.manifest['files']),
                             unique_bytes=sum(unique.values()), updated_at=datetime.now(timezone.utc).isoformat())
        atomic(self.root/'assets/manifest.json', self.manifest)


def apply(root, workspace, plan):
    extraction = read(workspace/EXTRACTION/'extraction.json', {'records': []})
    extracted = {r['source']: r for r in extraction['records']}
    with locked(root/'.context/topaz-packaging'):
        pack = Pack(root)
        for source, item in plan['new'].items():
            pack.master(source, item['master'], item['state'])
            pack.reference(source, item['cleaned'])
            review = dict(master=f"source:{workspace.name}/{item['master'].relative_to(workspace).as_posix()}",
                          sha256=item['sha256'], state=item['state'], validation=item['validation'],
                          validation_passed=item['validation_passed'], derived=item['derived'], batch=item['batch'])
            review.update({k: item[k] for k in ('parent',) + APPROVAL if k in item})
            pack.reviews[source] = review
            origin = extracted.get(Path(source).name)
            if source not in pack.known and item['cleaned_sha256']:
                record = dict(source=source, cleaned_sha256=item['cleaned_sha256'], canonical=source,
                              origin='local-game-extraction')
                if origin:
                    record.update(source_file=f'source:{workspace.name}/{EXTRACTION}/indexed/{Path(source).name}',
                                  source_sha256=origin['source_sha256'], size=origin['size'])
                pack.library['records'].append(record); pack.known.add(source)
        pack.save()


def summary(plan):
    new = plan['new']
    return dict(new=len(new), states=dict(Counter(i['state'] for i in new.values())),
                approved_by_user=sum(1 for i in new.values() if i.get('review_status') == 'approved'),
                per_costume=dict(Counter(s.split('_frame_')[0] for s in new)),
                already_present=len(plan['same']), conflicts=plan['conflicts'], problems=plan['problems'],
                unfinished=len(plan['unfinished']))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workspace', type=Path, required=True, help='workspace holding the focus batches')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true', help='write files; default is a dry run')
    args = parser.parse_args()
    plan = plan_import(args.root, args.workspace.resolve())
    if args.apply: apply(args.root, args.workspace.resolve(), plan)
    print(json.dumps(dict(summary(plan), applied=args.apply), indent=1))


if __name__ == '__main__':
    main()
