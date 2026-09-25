import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from scene_sheets import MAX_EDGE, MAX_PIXELS, build, digest, lookup, parse_ids


def png(path, size, color=(200, 40, 40, 255), mode='RGBA'):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(path)
    return path


class SceneSheetTests(unittest.TestCase):
    def fixture(self, root, frames=25):
        for n in range(frames):
            png(root/f'extracted/costumes/LFLF_0009_AKOS_0027_frame_{n}.png', (20, 30), 3, 'P')
            png(root/f'assets/references/topaz-cleaned/costumes/LFLF_0009_AKOS_0027_frame_{n}.png', (20, 30))
        for n in (0, 2):  # frame 1 has no master
            png(root/f'assets/masters/topaz-4x/costumes/LFLF_0009_AKOS_0027_frame_{n}.png', (80, 120))
        # A costume stored in this room but absent from the scene data.
        png(root/'assets/references/topaz-cleaned/costumes/LFLF_0009_AKOS_0025_frame_0.png', (20, 30))
        png(root/'assets/masters/topaz-4x/costumes/LFLF_0009_AKOS_0025_frame_0.png', (80, 120))
        png(root/'extracted/objects/0009_hook_0000.png', (18, 24), 5, 'P')
        png(root/'assets/masters/topaz-4x/objects/0009_hook_0000.png', (72, 96))
        # Placeholder index 39 shares its colour with paint index 7: cropping must compare indices.
        layer = Image.new('P', (64, 48), 39); layer.putpalette([0, 0, 0] * 256); layer.paste(7, (10, 12, 20, 30))
        (root/'extracted/objects_layers').mkdir(parents=True); layer.save(root/'extracted/objects_layers/0009_hook_0000.png')
        png(root/'extracted/backgrounds/0009_cannon.png', (64, 48), (10, 20, 30))
        master_bg = png(root/'assets/masters/backgrounds/abc.png', (384, 288), (10, 20, 30))
        master = root/'assets/masters/topaz-4x/costumes/LFLF_0009_AKOS_0027_frame_0.png'
        (root/'assets/metadata').mkdir(parents=True)
        (root/'assets/metadata/artwork-review.json').write_text(json.dumps({
            'costumes/LFLF_0009_AKOS_0027_frame_0.png': dict(state='validated', sha256=digest(master)),
            'costumes/LFLF_0009_AKOS_0027_frame_2.png': dict(state='rejected', sha256='stale')}))
        (root/'assets/manifest.json').write_text(json.dumps(dict(files=[
            dict(path='assets/masters/backgrounds/abc.png', sha256=digest(master_bg), canonical=True,
                 asset_id='background-room-9', review_status='unreviewed')])))
        assets = [dict(type='character', name='LFLF_0009_AKOS_0027',
                       originalPath='extracted/costumes/LFLF_0009_AKOS_0027_frame_0.png',
                       metadata=dict(akosId='LFLF_0009_AKOS_0027', roomNumber=9)),
                  dict(type='object', name='0009_hook_0000', originalPath='extracted/objects/0009_hook_0000.png',
                       metadata=dict(roomNumber=9)),
                  dict(type='background', name='0009_cannon', originalPath='extracted/backgrounds/0009_cannon.png',
                       metadata=dict(roomNumber=9))]
        scene = dict(scene=dict(id='s9', name='cannon', roomNumber=9), assets={str(i): a for i, a in enumerate(assets)})
        (root/'data/scenes').mkdir(parents=True)
        (root/'data/scenes/s9.json').write_text(json.dumps(scene))
        return scene

    def test_every_source_maps_to_one_tile_within_page_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scene = self.fixture(root)
            folder, built, index = build(root, scene, page=(400, 300))
            tiles = index['tiles']
            self.assertEqual(sum(1 for k in tiles if k.startswith('C1.')), 25)
            self.assertEqual({k for k in tiles if not k.startswith('C1.')}, {'C2.0', 'O1.0', 'L1.0', 'B1'})
            self.assertTrue(index['groups']['C2']['not_in_scene_data'])
            self.assertIsNone(tiles['C2.0']['source'])
            self.assertEqual(tiles['C1.1']['state'], 'missing')
            self.assertEqual(tiles['C1.0']['state'], 'validated')
            self.assertEqual(tiles['C1.2']['master']['review_sha256'], 'stale')
            self.assertEqual(tiles['B1']['master']['path'], 'assets/masters/backgrounds/abc.png')
            self.assertEqual(tiles['L1.0']['crop'], [8, 10, 22, 32])
            self.assertIn('review --source costumes/LFLF_0009_AKOS_0027_frame_0.png', tiles['C1.0']['review_command'])
            pages = {n for _, names, _ in built for n in names}
            self.assertGreater(len([n for n in pages if n.startswith('characters')]), 1)
            for name in pages:
                w, h = Image.open(folder/name).size
                self.assertLessEqual(max(w, h), MAX_EDGE); self.assertLessEqual(w * h, MAX_PIXELS)
            for t in tiles.values():
                self.assertIn(t['page'], pages)
                x0, y0, x1, y1 = t['bbox']
                self.assertTrue(0 <= x0 < x1 <= 400 and 0 <= y0 < y1 <= 300, t)
            text = (folder/'index.md').read_text()
            self.assertIn('C1** LFLF_0009_AKOS_0027', text)
            self.assertIn('missing: 1', text)

    def test_sampling_and_masters_only_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scene = self.fixture(root, frames=10)
            _, _, index = build(root, scene, categories=('characters',), frame_step=3)
            self.assertEqual(sorted(k for k in index['tiles'] if k.startswith('C1.')),
                             ['C1.0', 'C1.3', 'C1.6', 'C1.9'])
            self.assertEqual(index['groups']['C1']['skipped_frames'], [1, 2, 4, 5, 7, 8])
            _, _, index = build(root, scene, categories=('characters',), masters_only=True, force=True)
            self.assertEqual(sorted(k for k in index['tiles'] if k.startswith('C1.')), ['C1.0', 'C1.2'])
            self.assertIn('C1.1', index['groups']['C1']['omitted_no_master'])

    def test_unchanged_inputs_reuse_pages_and_partial_builds_keep_other_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scene = self.fixture(root, frames=3)
            folder, built, _ = build(root, scene)
            self.assertFalse(any(reuse for _, _, reuse in built))
            _, built, _ = build(root, scene)
            self.assertTrue(all(reuse for _, _, reuse in built))
            png(root/'assets/masters/topaz-4x/objects/0009_hook_0000.png', (72, 96), (0, 0, 255, 255))
            _, built, index = build(root, scene, categories=('objects',))
            self.assertEqual([(c, r) for c, _, r in built], [('objects', False)])
            self.assertIn('C1.0', index['tiles']); self.assertIn('B1', index['tiles'])
            self.assertIn('## characters', (folder/'index.md').read_text())

    def test_lookup_round_trips_ids_ranges_and_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scene = self.fixture(root, frames=5)
            build(root, scene)
            found = lookup(root, scene, ['C1.1-3', 'O1'])
            self.assertEqual(sorted(found), ['C1.1', 'C1.2', 'C1.3', 'O1'])
            self.assertEqual(found['C1.2']['source']['path'], 'extracted/costumes/LFLF_0009_AKOS_0027_frame_2.png')
            self.assertEqual(found['O1']['tile_ids'], ['O1.0'])
            self.assertEqual(parse_ids(['C3.10-12', 'B1']), ['C3.10', 'C3.11', 'C3.12', 'B1'])
            with self.assertRaises(SystemExit): lookup(root, scene, ['C9.0'])

    def test_runtime_copies_are_linked_and_unlinked_room_files_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scene = self.fixture(root, frames=1)
            runtime = png(root/'assets/runtime/topaz-crisp/costumes/LFLF_0009_AKOS_0027_aframe_0.png', (80, 120))
            stray = png(root/'assets/runtime/costumes/LFLF_0009_AKOS_0027_aframe_7.png', (80, 120))
            png(root/'assets/runtime/costumes/LFLF_0010_AKOS_0001_aframe_0.png', (8, 8))  # other room
            manifest = json.loads((root/'assets/manifest.json').read_text())
            manifest['files'].append(dict(path='assets/runtime/topaz-crisp/costumes/LFLF_0009_AKOS_0027_aframe_0.png',
                                          derived_from='assets/masters/topaz-4x/costumes/LFLF_0009_AKOS_0027_frame_0.png'))
            (root/'assets/manifest.json').write_text(json.dumps(manifest))
            folder, _, index = build(root, scene)
            self.assertEqual(index['tiles']['C1.0']['master']['runtime'],
                             [dict(path='assets/runtime/topaz-crisp/costumes/LFLF_0009_AKOS_0027_aframe_0.png',
                                   sha256=digest(runtime))])
            self.assertEqual(index['unreferenced'], ['assets/runtime/costumes/LFLF_0009_AKOS_0027_aframe_7.png'])
            self.assertIn('Room files not on any sheet: 1', (folder/'index.md').read_text())
            stray.unlink()
            _, _, index = build(root, scene)
            self.assertEqual(index['unreferenced'], [])

    def test_scope_adds_shared_costumes_icons_and_local_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scene = self.fixture(root, frames=1)
            png(root/'.context/scene-sheets/originals/indexed/LFLF_0009_AKOS_0032_frame_0.png', (10, 10), 1, 'P')
            png(root/'.context/scene-sheets/originals/cleaned/LFLF_0009_AKOS_0032_frame_0.png', (10, 10))
            png(root/'extracted/costumes/LFLF_0001_AKOS_0002_frame_0.png', (10, 10), 1, 'P')
            png(root/'extracted/objects/0003_hook-icon-object_0000.png', (10, 10), 1, 'P')
            scope = root/'coverage.json'
            scope.write_text(json.dumps(dict(scenes={'9': dict(assets=[dict(source=k) for k in (
                'costumes/LFLF_0001_AKOS_0002_frame_0.png', 'costumes/LFLF_0001_AKOS_0002_frame_1.png',
                'costumes/LFLF_0009_AKOS_0032_frame_0.png', 'objects/0003_hook-icon-object_0000.png')])})))
            folder, _, index = build(root, scene, scope=scope)
            by_key = {t['key']: t for t in index['tiles'].values()}
            self.assertEqual(by_key['costumes/LFLF_0009_AKOS_0032_frame_0.png']['source']['path'],
                             '.context/scene-sheets/originals/indexed/LFLF_0009_AKOS_0032_frame_0.png')
            self.assertIsNone(by_key['costumes/LFLF_0001_AKOS_0002_frame_1.png']['source'])
            self.assertIn('objects/0003_hook-icon-object_0000.png', by_key)
            self.assertEqual(index['scope']['not_on_sheets'], [])
            text = (folder/'index.md').read_text()
            self.assertIn('4 sources, 0 not on sheets', text)
            self.assertIn('Tiles with no file anywhere (native cel not extracted): 1', text)

    def test_oversized_pages_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); scene = self.fixture(root, frames=1)
            with self.assertRaises(SystemExit): build(root, scene, page=(1568, 1568))


if __name__ == '__main__':
    unittest.main()
