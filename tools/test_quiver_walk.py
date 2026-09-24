import json
from pathlib import Path
import tempfile
import shutil
import unittest
import numpy as np
from unittest.mock import patch

from PIL import Image

import quiver_cannon as q
import quiver_walk as w
from quiver_eye_review import measure


class WalkingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.record = dict(source='LFLF_0001_AKOS_0002_frame_599.png', size=[10, 20],
                           costume=2, cel=599, artwork_sha256='a' * 64,
                           reference_canvas=dict(side=36, x=13, y=8))
        q.atomic(self.output / 'manifest.json', dict(records=[self.record], pilot_keys=['a' * 64]))

    def test_known_padding_maps_back_without_recentering(self):
        # Quiver may choose a different square viewBox. Its scale and the padding
        # added by prepare are known, so no fitted subject bounding box is needed.
        raw = '<svg viewBox="0 0 72 72"><path fill="#bb3322" d="M30 20h12v28H30z"/></svg>'
        q.atomic(self.output / 'raw' / ('a' * 64 + '.json'), dict(data=[dict(svg=raw)]))
        (self.output / 'cleaned').mkdir()
        original = Image.new('RGBA', (10, 20))
        original.paste((187, 51, 34, 255), (2, 2, 8, 16))
        original.save(self.output / 'cleaned' / self.record['source'])
        report = w.validate(self.output, self.record)
        self.assertTrue(report['passed'], report)
        for scale in (4, 6):
            with Image.open(self.output / f'{scale}x' / ('a' * 64 + '.png')) as im:
                self.assertEqual(im.size, (10 * scale, 20 * scale))
                self.assertEqual(im.getpixel((0, 0))[3], 0)
                self.assertEqual(im.getpixel((4 * scale, 5 * scale)), (187, 51, 34, 255))
        self.assertEqual(json.loads((self.output / 'raw' / ('a' * 64 + '.json')).read_text())['data'][0]['svg'], raw)

    def test_unexpected_canvas_rejected(self):
        with self.assertRaisesRegex(ValueError, 'aspect ratio'):
            w.registered_svg('<svg viewBox="0 0 20 30"/>', self.record)

    def test_reviewed_repair_cannot_apply_to_different_provider_response(self):
        raw = '<svg viewBox="0 0 36 36"><path d="M15 10h6v14h-6z"/></svg>'
        key = self.record['artwork_sha256']
        q.atomic(self.output / 'raw' / (key + '.json'), dict(data=[dict(svg=raw)]))
        q.atomic(self.output / 'repairs.json', {key: dict(raw_sha256='wrong', reason='Reviewed eyebrow')})
        with patch.object(w, 'restore_shadow_alpha', return_value=(raw, [])):
            with self.assertRaisesRegex(ValueError, 'does not match'):
                w.validate(self.output, self.record)

    def test_shadow_recovery_excludes_outline_pixels_and_detached_heads(self):
        source = np.zeros((100, 50, 4), dtype=np.uint8)
        source[20:40, 10, 3] = 128  # Source outline fragments, not a floor shadow.
        source[91:96, 10:35, 3] = 128
        mask = w.source_shadow_mask(source, self.record)
        self.assertFalse(mask[:75].any())
        self.assertEqual(int(mask.sum()), 125)
        self.assertFalse(w.source_shadow_mask(source, dict(sprite_role='standing_head')).any())

    def test_eye_review_detects_displacement_in_original_pixel_coordinates(self):
        source = Image.new('RGBA', (30, 40))
        source.paste((247, 247, 231, 255), (10, 8, 14, 12))
        rendered = Image.new('RGBA', (180, 240))
        rendered.paste((247, 247, 231, 255), (12 * 6, 8 * 6, 16 * 6, 12 * 6))
        report = measure(source, rendered, 20)
        self.assertTrue(report['needs_visual_inspection'])
        self.assertEqual(report['eyes'][0]['delta'], [2.0, 0.0])

    def test_uncertain_outcome_not_submitted_again(self):
        db = q.journal(self.output)
        q.save_job(db, 'a' * 64, 'unknown', request_id='prior-request')
        db.close()
        with patch.object(q, 'request', return_value=({'data': [{'id': 'arrow-2'}]}, None)) as request:
            with self.assertRaisesRegex(ValueError, 'no automatic resubmission'):
                w.generate(self.output, True)
            request.assert_not_called()

    def test_batch_requires_accepted_pilot(self):
        with patch.object(q, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'Review the walking pilot'):
                w.generate(self.output, False)
            request.assert_not_called()

    def test_explicit_retry_retains_response_and_usage_but_blocks_unknown(self):
        key = self.record['artwork_sha256']
        db = q.journal(self.output)
        q.atomic(self.output / 'raw' / (key + '.json'), {'id': 'completed-response'})
        q.save_job(db, key, 'unknown', response_id='completed-response')
        with self.assertRaisesRegex(ValueError, 'completed, identified'):
            w.retry_rejected(self.output, [key], 'Missing shirt fill')
        q.save_job(db, key, 'rejected', response_id='completed-response', usage={'output_tokens': 25})
        w.retry_rejected(self.output, [key], 'Missing shirt fill')
        state, details = q.job(db, key)
        self.assertEqual(state, 'retry_ready')
        self.assertEqual(details['previous_attempts'][0]['usage']['output_tokens'], 25)
        self.assertTrue((self.output / 'attempts' / key / '1/raw.json').exists())
        q.status(self.output)
        self.assertEqual(json.loads((self.output / 'status.json').read_text())['usage']['output_tokens'], 25)
        db.close()

    def test_prepare_includes_persistent_idle_head_and_preserves_source_mapping(self):
        sources = self.output / 'source-pack'
        (sources / 'cleaned').mkdir(parents=True)
        records = []
        for cel in (599, 8, 58, 99):
            record = dict(self.record, cel=cel, source=f'cel-{cel}.png',
                          artwork_sha256=str(cel), offsets=[[-17, -211]])
            records.append(record)
            Image.new('RGBA', (10, 20)).save(sources / 'cleaned' / record['source'])
        q.atomic(sources / 'manifest.json', dict(records=records))
        prepared = self.output / 'prepared'
        selections = {1: [8, 58], 2: [599], 3: [8], 5: [58]}
        with patch.object(w, 'resources', return_value=[(2, 1, b'', {}, None)]), \
             patch.object(w, 'cels', side_effect=lambda fields, chore: (selections[chore], [])):
            w.prepare(prepared, Path('unused'), sources, 'vectorization')
            manifest = json.loads((prepared / 'manifest.json').read_text())
            self.assertEqual([r['cel'] for r in manifest['records']], [599, 8, 58])
            self.assertEqual(manifest['scope']['standing_cels'], [8, 58])
            self.assertEqual(manifest['records'][2]['offsets'], [[-17, -211]])
            selections[1].append(99)
            with self.assertRaisesRegex(ValueError, 'initial multipart pose'):
                w.prepare(prepared, Path('unused'), sources, 'vectorization')

    def test_shadow_alpha_corrected_without_changing_gray_clothing(self):
        (self.output / 'cleaned').mkdir()
        original = Image.new('RGBA', (10, 20))
        original.paste((0, 0, 0, 128), (1, 16, 9, 19))
        original.paste((127, 127, 127, 255), (2, 2, 8, 17))
        original.save(self.output / 'cleaned' / self.record['source'])
        raw = '<svg viewBox="0 0 36 36"><path fill="#858281" d="M14 24h8v3h-8z"/><path fill="#7F7F7F" d="M15 10h6v15h-6z"/></svg>'
        q.atomic(self.output / 'raw' / ('a' * 64 + '.json'), dict(data=[dict(svg=raw)]))
        report = w.validate(self.output, self.record)
        self.assertTrue(report['passed'], report)
        self.assertEqual(len(report['corrections']), 1)
        self.assertEqual(report['corrections'][0]['element_index'], 1)
        with Image.open(self.output / '6x' / ('a' * 64 + '.png')) as im:
            self.assertEqual(im.getpixel((3 * 6, 5 * 6)), (127, 127, 127, 255))
            self.assertEqual(im.getpixel((3 * 6, 18 * 6)), (0, 0, 0, 128))

    @unittest.skipUnless(shutil.which('potrace'), 'potrace required for source shadow recovery')
    def test_missing_shadow_restored_as_vectors_without_replacing_body(self):
        (self.output / 'cleaned').mkdir()
        original = Image.new('RGBA', (10, 20))
        original.paste((0, 0, 0, 128), (1, 16, 9, 19))
        original.paste((187, 51, 34, 255), (2, 2, 8, 16))
        original.save(self.output / 'cleaned' / self.record['source'])
        raw = '<svg viewBox="0 0 36 36"><path fill="#bb3322" d="M15 10h6v14h-6z"/></svg>'
        q.atomic(self.output / 'raw' / ('a' * 64 + '.json'), dict(data=[dict(svg=raw)]))
        report = w.validate(self.output, self.record)
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['corrections'][0]['type'], 'restore-missing-source-shadow')
        with Image.open(self.output / '6x' / ('a' * 64 + '.png')) as im:
            self.assertEqual(im.getpixel((3 * 6, 5 * 6)), (187, 51, 34, 255))
            self.assertEqual(im.getpixel((3 * 6, 18 * 6)), (0, 0, 0, 128))
        svg = (self.output / 'svg' / ('a' * 64 + '.svg')).read_text()
        self.assertNotIn('<image', svg)


if __name__ == '__main__':
    unittest.main()
