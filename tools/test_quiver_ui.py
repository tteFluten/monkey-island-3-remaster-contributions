import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

import quiver_ui as ui


class QuiverUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output, self.batch, self.local = [self.root / name for name in ('output', 'batch', 'local')]
        records = []
        for index, source in enumerate(ui.SOURCES):
            path = self.batch / 'cleaned' / source
            path.parent.mkdir(parents=True, exist_ok=True)
            im = Image.new('RGBA', (80, 56))
            # Two pointer states are distinct; each pair of arrow states is identical.
            identity = index if index < 2 else index // 2 + 1
            for x in range(25, 40):
                for y in range(16, 35):
                    im.putpixel((x, y), (255, identity, 0, 255))
            im.save(path)
            records.append(dict(source=source, cleaned_sha256=ui.q.sha(path.read_bytes()), size=[80, 56]))
        (self.batch / 'manifest.json').write_text(json.dumps(dict(records=records)))
        ui.prepare(self.output, self.batch)
        self.records = ui.manifest(self.output)['records']
        (self.local / 'game').mkdir(parents=True)
        payload = struct.pack('<I', len(ui.NAMES)) + b''.join(name.encode().ljust(40, b'\0') + bytes(6) for name in ui.NAMES)
        (self.local / 'game/COMI.LA0').write_bytes(b'DOBJ' + struct.pack('>I', len(payload) + 8) + payload)

    def approve(self):
        with ui.q.journal(self.output) as db:
            for r in self.records:
                relative = f'svg/{r["artwork_sha256"]}.svg'
                file = self.output / relative
                file.parent.mkdir(exist_ok=True)
                file.write_text('<svg viewBox="0 0 80 56"><path d="M25 16h15v19H25z"/></svg>')
                ui.q.save_job(db, r['artwork_sha256'], 'accepted',
                              validation=dict(output_hashes={relative: ui.q.sha(file.read_bytes())}))

    def test_exact_selection_deduplicates_and_excludes_other_ui(self):
        self.assertEqual(len(self.records), 18)
        self.assertEqual(len({r['artwork_sha256'] for r in self.records}), 10)
        self.assertEqual(len(ui.manifest(self.output)['pilot_keys']), 3)
        self.assertNotEqual(self.records[0]['artwork_sha256'], self.records[1]['artwork_sha256'])
        self.assertEqual(self.records[2]['artwork_sha256'], self.records[3]['artwork_sha256'])
        before = (self.output / 'manifest.json').read_bytes()
        ui.prepare(self.output, self.batch)
        self.assertEqual(before, (self.output / 'manifest.json').read_bytes())

    def test_alignment_rejects_displacement_erased_interior_and_new_background(self):
        source = Image.open(self.output / 'cleaned' / self.records[0]['source'])
        self.assertTrue(ui.alignment(source, source)['passed'])
        shifted = Image.new('RGBA', source.size)
        shifted.paste(source, (2, 0))
        self.assertFalse(ui.alignment(source, shifted)['passed'])
        erased = source.copy()
        for x in range(29, 36):
            for y in range(20, 30):
                erased.putpixel((x, y), (0, 0, 0, 0))
        self.assertFalse(ui.alignment(source, erased)['passed'])
        self.assertFalse(ui.alignment(source, Image.new('RGBA', source.size, 'white'))['passed'])

    def test_generate_once_per_unique_input_and_resume_without_paid_retries(self):
        posts = []
        def request(endpoint, payload=None):
            if endpoint == '/models':
                return {'data': [{'id': 'arrow-2'}]}, None
            posts.append(payload)
            self.assertFalse(payload['auto_crop'])
            return {'data': [{'svg': '<svg/>'}], 'usage': {'output_tokens': 10}}, 'request-id'
        with patch.object(ui.q, 'request', side_effect=request), patch.object(ui, 'validate', return_value={'passed': True}):
            with self.assertRaisesRegex(ValueError, 'pilots'):
                ui.generate(self.output)
            ui.generate(self.output, pilot=True)
            ui.q.review(self.output, ui.manifest(self.output)['pilot_keys'])
            ui.generate(self.output)
            ui.generate(self.output)
        self.assertEqual(len(posts), 10)

    def test_uncertain_submission_is_never_repeated(self):
        def request(endpoint, payload=None):
            if endpoint == '/models':
                return {'data': [{'id': 'arrow-2'}]}, None
            raise TimeoutError()
        with patch.object(ui.q, 'request', side_effect=request) as mock:
            with self.assertRaisesRegex(RuntimeError, 'Uncertain'):
                ui.generate(self.output, pilot=True)
            count = mock.call_count
            with self.assertRaisesRegex(ValueError, 'no automatic'):
                ui.generate(self.output, pilot=True)
            self.assertEqual(mock.call_count, count)

    def test_cached_validation_uses_native_decoder_at_both_scales(self):
        r = self.records[0]
        key = r['artwork_sha256']
        # Source rectangle (25,16)-(40,35), translated into the padded canvas.
        raw = '<svg viewBox="0 0 96 96"><path fill="#ff0000" d="M33 36h15v19H33z"/></svg>'
        ui.q.atomic(self.output / 'raw' / f'{key}.json', {'data': [{'svg': raw}]})
        with patch.object(ui.q, 'request', side_effect=AssertionError('No API calls')):
            report = ui.validate_job(self.output, r)
            self.assertTrue(report['passed'])
            self.assertEqual(len(report['native']), 2)
            for scale in (4, 6):
                with Image.open(self.output / f'native-{scale}x/{key}.png') as im:
                    self.assertEqual(im.size, (80 * scale, 56 * scale))
                    self.assertEqual(im.getpixel((0, 0))[3], 0)
            ui.q.review(self.output, [key])
            ui.validate_job(self.output, r)
            with ui.q.journal(self.output) as db:
                self.assertEqual(ui.q.job(db, key)[0], 'geometry_passed')

    def test_install_svg_only_preserves_png_and_restores_only_touched_mapping(self):
        self.approve()
        hd = self.local / 'hd'
        (hd / 'objects').mkdir(parents=True)
        svg = hd / Path(ui.SOURCES[0]).with_suffix('.svg')
        svg.write_text('previous SVG')
        png = hd / ui.SOURCES[0]
        png.write_bytes(b'unchanged PNG')
        prior = {'0': {'name': ui.NAMES[0], 'rooms': {'3': {'states': [0]}, '9': {'states': [4]}}},
                 '999': {'name': 'unrelated', 'rooms': {'9': {'states': [0]}}}}
        ui.q.atomic(hd / 'object_map.json', prior)
        ui.install(self.output, self.local)
        ui.install(self.output, self.local)  # Keep the original backup on repeat installation.
        self.assertEqual(len(list((hd / 'objects').glob('*.svg'))), 18)
        self.assertEqual(png.read_bytes(), b'unchanged PNG')
        current = json.loads((hd / 'object_map.json').read_text())
        current['999']['rooms']['9']['states'].append(5)
        current['1']['rooms']['12'] = {'states': [7]}
        ui.q.atomic(hd / 'object_map.json', current)
        ui.install(self.output, self.local, restore=True)
        self.assertEqual(svg.read_text(), 'previous SVG')
        self.assertEqual(len(list((hd / 'objects').glob('*.svg'))), 1)
        restored = json.loads((hd / 'object_map.json').read_text())
        self.assertEqual(restored['0'], prior['0'])
        self.assertEqual(restored['999']['rooms']['9']['states'], [0, 5])
        self.assertEqual(restored['1']['rooms'], {'12': {'states': [7]}})

    def test_install_requires_review_unchanged_hashes_and_stopped_game(self):
        with self.assertRaisesRegex(ValueError, 'accepted'):
            ui.install(self.output, self.local)
        self.approve()
        ui.q.atomic(self.local / 'process.json', {'pid': os.getpid()})
        with self.assertRaisesRegex(RuntimeError, 'Stop the game'):
            ui.install(self.output, self.local)
        (self.local / 'process.json').unlink()
        key = self.records[0]['artwork_sha256']
        (self.output / f'svg/{key}.svg').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            ui.install(self.output, self.local)
        self.assertFalse((self.output / 'installation.json').exists())


if __name__ == '__main__':
    unittest.main()
