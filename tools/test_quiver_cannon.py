import contextlib
import io
import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from quiver_cannon import (alignment, atomic, generate, install, job, journal,
                           normalize_svg, review, save_job, status, validate_one)
from quiver_extract import decode_cel, sha


class DecoderTests(unittest.TestCase):
    def test_column_major_runs(self):
        result = decode_cel(bytes([0x12, 0x22, 0x32]), 3, 2, 1, 16)
        np.testing.assert_array_equal(result, [[1, 2, 3], [1, 2, 3]])

    def test_extended_run(self):
        np.testing.assert_array_equal(decode_cel(bytes([0x30, 20]), 4, 5, 1, 16), np.full((5, 4), 3))

    def test_bomp_literal_repeat_and_transparency(self):
        a = bytes([3, 7, 2, 8, 255])
        b = bytes([1, 4])
        result = decode_cel(struct.pack('<H', len(a)) + a + struct.pack('<H', len(b)) + b, 4, 2, 5, 256)
        np.testing.assert_array_equal(result, [[7, 7, 8, 255], [4, 255, 255, 255]])

    def test_truncated_bomp_rejected(self):
        with self.assertRaises(ValueError):
            decode_cel(b'\x06\x00\x01', 2, 2, 5, 256)


class GeometryTests(unittest.TestCase):
    def test_uniform_canvas_transform_preserves_margins(self):
        svg = normalize_svg('<svg viewBox="0 0 20 40" fill="none"><path d="M2 3h4" stroke="red"/></svg>', [10, 20])
        self.assertIn('width="60"', svg)
        self.assertIn('height="120"', svg)
        self.assertIn('scale(0.5)', svg)
        self.assertIn('fill="none"', svg)

    def test_square_canvas_rejected_for_tall_sprite(self):
        with self.assertRaisesRegex(ValueError, 'aspect ratio'):
            normalize_svg('<svg viewBox="0 0 80 80"/>', [70, 230])

    def test_active_embedded_external_content_rejected(self):
        for content in ('<script/>', '<image href="data:image/png;base64,abc"/>',
                        '<path onload="alert(1)"/>', '<path fill="url(https://example.com/a)"/>'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                normalize_svg(f'<svg viewBox="0 0 10 10">{content}</svg>', [10, 10])

    def test_local_gradient_allowed(self):
        normalize_svg('<svg viewBox="0 0 10 10"><defs><linearGradient id="g"><stop offset="0" stop-color="red"/></linearGradient></defs><path fill="url( #g )"/></svg>', [10, 10])

    def test_alignment_passes_identical_and_rejects_shift_or_background(self):
        a = Image.new('RGBA', (20, 30)); a.paste((180, 60, 50, 255), (4, 3, 12, 27))
        self.assertTrue(alignment(a, a.resize((120, 180), Image.Resampling.NEAREST))['passed'])
        shifted = Image.new('RGBA', a.size); shifted.paste(a, (5, 0))
        self.assertFalse(alignment(a, shifted)['passed'])
        self.assertFalse(alignment(a, Image.new('RGBA', a.size, 'white'))['passed'])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'output'; self.output.mkdir()
        self.record = dict(source='LFLF_0009_AKOS_0030_frame_0.png', costume=30, room=9, cel=0,
                           size=[2, 3], character='Guybrush', artwork_sha256='a' * 64)
        self.manifest = dict(records=[self.record], pilot_keys=['a' * 64], references={'Guybrush': self.record['source']})
        atomic(self.output / 'manifest.json', self.manifest)
        self.db = journal(self.output)
        self.addCleanup(self.db.close)

    def test_uncertain_submission_never_repeated(self):
        save_job(self.db, 'a' * 64, 'unknown', request_id='saved')
        with patch('quiver_cannon.request', return_value=({'data': [{'id': 'arrow-2'}]}, None)) as call:
            with self.assertRaisesRegex(RuntimeError, 'no automatic resubmission'):
                generate(self.output, pilot=True)
            self.assertEqual([c.args[0] for c in call.call_args_list], ['/models'])

    def test_full_run_requires_reviewed_pilots(self):
        with patch('quiver_cannon.request') as call:
            with self.assertRaisesRegex(RuntimeError, 'visual review'):
                generate(self.output)
            call.assert_not_called()

    def test_review_cannot_override_rejected_geometry(self):
        save_job(self.db, 'a' * 64, 'rejected')
        with self.assertRaises(ValueError):
            review(self.output, ['a' * 64])

    def test_review_retains_usage_and_request_id(self):
        save_job(self.db, 'a' * 64, 'geometry_passed', request_id='example', usage={'input_tokens': 3})
        review(self.output, ['a' * 64])
        state, details = job(self.db, 'a' * 64)
        self.assertEqual(state, 'accepted'); self.assertEqual(details['request_id'], 'example')

    def test_install_refuses_partial_pack(self):
        with self.assertRaisesRegex(ValueError, 'all selected'):
            install(self.output, Path(self.temp.name) / 'hd')

    def test_install_restore_preserves_prior_files(self):
        hd = Path(self.temp.name) / 'hd'; original = hd / 'costumes/existing.png'
        original.parent.mkdir(parents=True); original.write_bytes(b'untouched')
        prior = hd / 'quiver-cannon/old.txt'; prior.parent.mkdir(); prior.write_text('previous')
        (self.output / '4x').mkdir()
        (self.output / 'svg').mkdir()
        (self.output / '6x').mkdir()
        paths = [self.output / '4x' / ('a' * 64 + '.png'), self.output / 'svg' / ('a' * 64 + '.svg'), self.output / '6x' / ('a' * 64 + '.png')]
        Image.new('RGBA', (8, 12), (120, 30, 20, 128)).save(paths[0])
        paths[1].write_text('<svg viewBox="0 0 2 3"><path d="M0 0h2v3H0z"/></svg>')
        Image.new('RGBA', (12, 18), (120, 30, 20, 128)).save(paths[2])
        hashes = {str(p.relative_to(self.output)): sha(p.read_bytes()) for p in paths}
        save_job(self.db, 'a' * 64, 'accepted', validation={'output_hashes': hashes})
        install(self.output, hd)
        self.assertEqual((hd / 'quiver-cannon/costumes/LFLF_0009_AKOS_0030_aframe_0.svg').read_bytes(), paths[1].read_bytes())
        self.assertEqual(list((hd / 'quiver-cannon/costumes').glob('*.png')), [])
        self.assertEqual(original.read_bytes(), b'untouched')
        install(self.output, hd, restore=True)
        # Restoration can be followed by another install/restore cycle.
        install(self.output, hd, runtime_format='png')
        self.assertTrue((hd / 'quiver-cannon/costumes/LFLF_0009_AKOS_0030_aframe_0.png').exists())
        install(self.output, hd, restore=True)
        self.assertEqual(prior.read_text(), 'previous')
        self.assertEqual(original.read_bytes(), b'untouched')

    def test_recorded_token_cost(self):
        atomic(self.output / 'model.json', {'billing': {'rates': {'input': 400000, 'output': 2000000}}})
        save_job(self.db, 'a' * 64, 'rejected', usage={'input_tokens': 779, 'output_tokens': 9653})
        with contextlib.redirect_stdout(io.StringIO()):
            status(self.output)
        report = json.loads((self.output / 'status.json').read_text())
        self.assertAlmostEqual(report['estimated_usd_at_recorded_rates'], .196176)
        self.assertFalse(report['complete'])

    def test_status_counts_selected_records_but_keeps_excluded_usage(self):
        save_job(self.db, 'a' * 64, 'accepted', usage={'input_tokens': 3})
        save_job(self.db, 'b' * 64, 'rejected', usage={'input_tokens': 7})
        with contextlib.redirect_stdout(io.StringIO()): status(self.output)
        report = json.loads((self.output / 'status.json').read_text())
        self.assertEqual(report['counts'], {'accepted': 1, 'not_submitted': 0})
        self.assertEqual(report['usage']['input_tokens'], 10)
        self.assertTrue(report['complete'])

    def test_rasterize_both_scales_from_cached_vector(self):
        record = dict(self.record, size=[20, 30])
        (self.output / 'cleaned').mkdir()
        source = Image.new('RGBA', (20, 30))
        source.paste((170, 45, 30, 255), (5, 5, 15, 25))
        source.save(self.output / 'cleaned' / record['source'])
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 30"><path fill="#aa2d1e" d="M5 5h10v20H5z"/></svg>'
        atomic(self.output / 'raw' / ('a' * 64 + '.json'), {'data': [{'svg': svg}]})
        report = validate_one(self.output, record)
        self.assertTrue(report['passed'], report)
        for scale in (4, 6):
            with Image.open(self.output / f'{scale}x' / ('a' * 64 + '.png')) as im:
                self.assertEqual(im.size, (20 * scale, 30 * scale))
                self.assertEqual(im.getpixel((0, 0))[3], 0)
        save_job(self.db, 'a' * 64, 'geometry_passed', validation=report)
        review(self.output, ['a' * 64])
        # A modified artifact cannot be installed under a stale review.
        (self.output / 'svg' / ('a' * 64 + '.svg')).write_text('<svg/>')
        with self.assertRaisesRegex(ValueError, 'changed'):
            install(self.output, Path(self.temp.name) / 'hd')


if __name__ == '__main__':
    unittest.main()
