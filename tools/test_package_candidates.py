import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from package_candidates import package
from topaz_character_cutouts import digest


def png(path, size, color=(200, 40, 40, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGBA', size, color).save(path)
    return path


class PackageCandidateTests(unittest.TestCase):
    def fixture(self, root):
        png(root/'assets/references/topaz-cleaned/objects/0009_hook_0000.png', (6, 5))
        old = png(root/'assets/masters/topaz-4x/objects/0009_hook_0000.png', (24, 20), (0, 0, 0, 255))
        runtime = png(root/'assets/runtime/objects/0009_hook_0000.png', (24, 20), (0, 0, 0, 255))
        layer = png(root/'assets/masters/topaz-4x/objects_layers/0009_hook_0000.png', (64, 48), (0, 0, 0, 0))
        png(root/'assets/references/topaz-cleaned/costumes/LFLF_0009_AKOS_0027_frame_1.png', (5, 7))
        rows = [dict(path=p.relative_to(root).as_posix(), sha256=digest(p), bytes=p.stat().st_size, category=c,
                     review_status='rejected', **extra)
                for p, c, extra in ((old, 'masters/topaz-4x', dict(canonical=True)),
                                    (runtime, 'runtime/objects', dict(derived_from='assets/masters/topaz-4x/objects/0009_hook_0000.png')),
                                    (layer, 'masters/topaz-4x', dict(canonical=True)))]
        metadata = root/'assets/metadata'; metadata.mkdir(parents=True)
        (metadata/'artwork-review.json').write_text(json.dumps({
            'costumes/LFLF_0009_AKOS_0027_frame_2.png': dict(derived=True, parent='costumes/LFLF_0009_AKOS_0027_frame_1.png')}))
        (metadata/'topaz-library.json').write_text(json.dumps(dict(records=[
            dict(source='objects_layers/0009_hook_0000.png', derived_from='objects/0009_hook_0000.png', offset=[3, 2])])))
        rows += [dict(path=f'assets/metadata/{n}', sha256='', bytes=0, category='metadata')
                 for n in ('artwork-review.json', 'topaz-library.json')]
        (root/'assets/manifest.json').write_text(json.dumps(dict(files=rows)))

    def test_packages_masters_runtime_layers_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            hook = png(root/'new/hook.png', (24, 20), (10, 200, 10, 255))
            rope = png(root/'new/rope.png', (20, 28), (120, 80, 20, 255))
            items = [dict(source='objects/0009_hook_0000.png', candidate=str(hook), state='validated', method='topaz'),
                     dict(source='costumes/LFLF_0009_AKOS_0027_frame_1.png', candidate=str(rope), state='draft-redraw',
                          method='quiver-arrow-2-prompted-redraw')]
            self.assertEqual(package(root, items, dry_run=True)['packaged'], 2)
            self.assertEqual(digest(root/'assets/masters/topaz-4x/objects/0009_hook_0000.png'),
                             digest(root/'assets/runtime/objects/0009_hook_0000.png'))  # dry run left files alone
            result = package(root, items)
            self.assertEqual(sorted(result['derived']), ['costumes/LFLF_0009_AKOS_0027_frame_2.png',
                                                         'objects_layers/0009_hook_0000.png'])
            manifest = {r['path']: r for r in json.loads((root/'assets/manifest.json').read_text())['files']}
            self.assertEqual(manifest['assets/runtime/objects/0009_hook_0000.png']['sha256'], digest(hook))
            self.assertEqual(manifest['assets/masters/topaz-4x/objects/0009_hook_0000.png']['review_status'], 'validated')
            for pack in ('topaz-cannon', 'topaz-crisp'):
                row = manifest[f'assets/runtime/{pack}/costumes/LFLF_0009_AKOS_0027_aframe_1.png']
                self.assertEqual((row['sha256'], row['review_status']), (digest(rope), 'draft-redraw'))
            with Image.open(root/'assets/masters/topaz-4x/objects_layers/0009_hook_0000.png') as layer:
                self.assertEqual(layer.getpixel((12, 8)), (10, 200, 10, 255))
                self.assertEqual(layer.getpixel((11, 8))[3], 0)
            self.assertEqual(manifest['assets/masters/topaz-4x/costumes/LFLF_0009_AKOS_0027_frame_2.png']['sha256'], digest(rope))
            reviews = json.loads((root/'assets/metadata/artwork-review.json').read_text())
            self.assertEqual(reviews['costumes/LFLF_0009_AKOS_0027_frame_1.png']['state'], 'draft-redraw')
            self.assertFalse(reviews['costumes/LFLF_0009_AKOS_0027_frame_1.png']['validation_passed'])
            self.assertEqual(reviews['costumes/LFLF_0009_AKOS_0027_frame_2.png']['state'], 'draft-derived')

    def test_rejects_candidates_that_are_not_exactly_4x(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            wrong = png(root/'new/hook.png', (25, 20))
            with self.assertRaises(ValueError):
                package(root, [dict(source='objects/0009_hook_0000.png', candidate=str(wrong), state='validated')])


if __name__ == '__main__':
    unittest.main()
