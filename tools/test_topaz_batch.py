import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from prepare_topaz import costume_rgba, object_rgba, digest
from topaz_batch import API, job_key, run, restore_alpha, materialize


class TransparencyTests(unittest.TestCase):
    def indexed(self, pixels, palette):
        pixels = np.array(pixels, dtype=np.uint8)
        im = Image.frombytes('P', (pixels.shape[1], pixels.shape[0]), pixels.tobytes())
        im.putpalette(palette + [0] * (768 - len(palette)))
        return im

    def test_shadow_marker_and_real_red_are_distinct(self):
        palette = [0, 0, 0, 180, 20, 5, 180, 20, 5, 0, 0, 0]
        im = self.indexed([[0, 1, 2, 3]], palette)
        out, count = costume_rgba(im, {'codec': 1, 'akpl': [0, 6, 30, 0], 'rgbs': palette})
        self.assertEqual(list(out.getdata()), [(0, 0, 0, 0), (0, 0, 0, 128), (180, 20, 5, 255), (0, 0, 0, 255)])
        self.assertEqual(count, 1)

    def test_opaque_smap_strip_keeps_its_key_colored_paint(self):
        im = self.indexed([[5] * 16], [0] * 768)
        out = object_rgba(im, 5, [True, False])
        self.assertEqual(list(out.getchannel('A').getdata()), [0] * 8 + [255] * 8)

    def test_palette_mismatch_fails_closed(self):
        im = self.indexed([[1]], [0, 0, 0, 255, 0, 0])
        with self.assertRaises(ValueError):
            costume_rgba(im, {'codec': 1, 'akpl': [0, 1], 'rgbs': [255, 0, 0]})

    def test_alpha_restored_and_wrong_dimensions_rejected(self):
        source = Image.new('RGBA', (2, 3), (0, 0, 0, 128))
        out = restore_alpha(Image.new('RGB', (12, 18), (63, 63, 63)), source)
        self.assertEqual(out.getpixel((5, 5)), (0, 0, 0, 128))
        with self.assertRaises(ValueError):
            restore_alpha(Image.new('RGB', (10, 10)), source)

    def test_generated_matte_noise_does_not_contaminate_shadow(self):
        source = Image.new('RGBA', (2, 3), (0, 0, 0, 128))
        out = restore_alpha(Image.new('RGB', (12, 18), (0, 255, 255)), source)
        self.assertEqual(out.getpixel((5, 5)), (0, 0, 0, 128))


class FakeAPI:
    def __init__(self):
        self.submissions = 0
        self.fail_download = False

    def balance(self):
        return 100

    def estimate(self, size):
        return {'credits': 1}

    def submit(self, path, size):
        self.submissions += 1
        return {'process_id': 'saved-job'}

    def call(self, route):
        return {'status': 'Completed'}

    def download(self, pid, destination):
        if self.fail_download:
            raise RuntimeError('network failure')
        Image.new('RGB', (12, 18), 'red').save(destination)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        path = self.root / 'cleaned/objects/a.png'
        path.parent.mkdir(parents=True)
        Image.new('RGBA', (2, 3), 'red').save(path)
        self.record = {'source': 'objects/a.png', 'canonical': 'objects/a.png',
                       'size': [2, 3], 'cleaned_sha256': digest(path)}
        self.manifest = {'version': 1, 'records': [self.record]}
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self):
        self.temp.cleanup()

    def test_direct_four_times_batch_is_separate_from_six_times(self):
        api = FakeAPI()
        api.download = lambda pid, destination: Image.new('RGB', (8, 12), 'blue').save(destination)
        run(self.root, api, 1, 1, scale=4)
        with Image.open(self.root / '4x' / self.record['source']) as output:
            self.assertEqual(output.size, (8, 12))
        self.assertFalse((self.root / '6x' / self.record['source']).exists())
        self.assertNotEqual(job_key(self.record, 4), job_key(self.record, 6))
        run(self.root, api, 1, 1, scale=4)
        self.assertEqual(api.submissions, 1)
        run(self.root, FakeAPI(), 1, 1)
        self.assertTrue((self.root / '6x' / self.record['source']).exists())

    def test_api_uses_requested_four_times_dimensions(self):
        key = self.root / 'fake-key'
        key.write_text('test-only')
        api = API(key, scale=4)
        requests = []
        api.call = lambda route, fields=None, image=None: requests.append(fields) or {'process_id': 'fake'}
        api.estimate((20, 30))
        api.submit(self.root / 'unused.png', (20, 30))
        for fields in requests:
            self.assertEqual((fields['output_width'], fields['output_height']), (80, 120))
            self.assertEqual(fields['model'], 'Wonder 3.5')
        with self.assertRaises(ValueError):
            run(self.root, api, 1, 1, scale=6)

    def test_resume_download_does_not_pay_twice(self):
        api = FakeAPI()
        api.fail_download = True
        with self.assertRaises(RuntimeError):
            run(self.root, api, 1, 1)
        api.fail_download = False
        run(self.root, api, 1, 1)
        run(self.root, api, 1, 1)
        self.assertEqual(api.submissions, 1)

    def test_credit_cap_prevents_submission(self):
        api = FakeAPI()
        run(self.root, api, 1, 0)
        self.assertEqual(api.submissions, 0)

    def test_deferred_download_resumes_without_repaying(self):
        api = FakeAPI()
        api.fail_download = True
        run(self.root, api, 1, 1, defer_downloads=True)
        self.assertEqual(json.loads((self.root / 'progress.json').read_text())['state'], 'downloads_pending')
        run(self.root, api, 1, 1, defer_downloads=True)
        self.assertEqual(api.submissions, 1)
        api.fail_download = False
        run(self.root, api, 1, 0)
        self.assertEqual(api.submissions, 1)
        self.assertTrue((self.root / '6x/objects/a.png').exists())

    def test_balance_rechecked_before_paid_submission(self):
        api = FakeAPI()
        balances = iter([100, 0])
        api.balance = lambda: next(balances)
        run(self.root, api, 1, 100)
        self.assertEqual(api.submissions, 0)

    def test_priority_reorders_without_losing_remaining_queue(self):
        path = self.root / 'cleaned/objects/b.png'
        Image.new('RGBA', (2, 3), 'blue').save(path)
        record = {**self.record, 'source': 'objects/b.png', 'canonical': 'objects/b.png',
                  'cleaned_sha256': digest(path)}
        self.manifest['records'].append(record)
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))
        api = FakeAPI()
        run(self.root, api, 1, 1, priority_prefixes=['objects/b'])
        self.assertTrue((self.root / '6x/objects/b.png').exists())
        self.assertFalse((self.root / '6x/objects/a.png').exists())
        run(self.root, api, 1, 1, priority_prefixes=['objects/b'])
        self.assertTrue((self.root / '6x/objects/a.png').exists())

    def test_timeout_keeps_job_for_resume(self):
        api = FakeAPI()
        api.call = lambda route: {'status': 'Processing'}
        with self.assertRaises(TimeoutError):
            run(self.root, api, 1, 1, timeout=-1)
        api.call = lambda route: {'status': 'Completed'}
        run(self.root, api, 1, 1)
        self.assertEqual(api.submissions, 1)

    def test_layer_uses_scaled_offset_and_preserves_dimensions(self):
        run(self.root, FakeAPI(), 1, 1)
        self.manifest['records'].append({'source': 'objects_layers/a.png',
                                        'derived_from': 'objects/a.png', 'size': [8, 8], 'offset': [2, 1]})
        materialize(self.root, self.manifest)
        with Image.open(self.root / '6x/objects_layers/a.png') as layer:
            self.assertEqual(layer.size, (48, 48))
            self.assertEqual(layer.getpixel((0, 0))[3], 0)
            self.assertEqual(layer.getpixel((12, 6))[3], 255)

    def test_incremental_results_publish_alias_before_its_layer(self):
        run(self.root, FakeAPI(), 1, 1)
        self.manifest['records'].extend([
            {**self.record, 'source': 'objects/alias.png'},
            {'source': 'objects_layers/alias.png', 'derived_from': 'objects/alias.png',
             'size': [8, 8], 'offset': [2, 1]},
        ])
        materialize(self.root, self.manifest, {'objects/a.png'})
        self.assertTrue((self.root / '6x/objects/alias.png').exists())
        with Image.open(self.root / '6x/objects_layers/alias.png') as layer:
            self.assertEqual(layer.getpixel((12, 6))[3], 255)

    def test_changed_input_stops_before_submission(self):
        (self.root / 'cleaned/objects/a.png').write_bytes(b'changed')
        api = FakeAPI()
        with self.assertRaises(ValueError):
            run(self.root, api, 1, 1)
        self.assertEqual(api.submissions, 0)


if __name__ == '__main__':
    unittest.main()
