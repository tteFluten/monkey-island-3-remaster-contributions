import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
import quiver_cannon as q
import quiver_cannon_sequence as cannon


class CannonSequenceTests(unittest.TestCase):
    def fixture(self, root):
        output, local = root / 'output', root / 'local'
        output.mkdir()
        records = []
        with q.journal(output) as db:
            for cel in range(14):
                key = str(cel)
                records.append(dict(source=f'LFLF_0009_AKOS_0026_frame_{cel}.png', room=9, costume=26, cel=cel, size=[5, 5], artwork_sha256=key))
                hashes = {}
                for folder, ext in [('svg', 'svg'), ('4x', 'png'), ('6x', 'png'), ('native-4x', 'png')]:
                    p = output / folder / f'{key}.{ext}'
                    p.parent.mkdir(exist_ok=True)
                    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 5 5"><path d="M0 0L5 0L5 5Z"/></svg>')
                    hashes[str(p.relative_to(output))] = q.sha(p.read_bytes())
                q.save_job(db, key, 'accepted', validation=dict(output_hashes=hashes))
        q.atomic(output / 'manifest.json', dict(records=records, pilot_keys=['0']))
        return output, local

    def test_merge_preserves_characters_and_refuses_modified_outputs_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            output, local = self.fixture(Path(temp))
            costume = local / 'hd/quiver-cannon/costumes'
            costume.mkdir(parents=True)
            existing = costume / 'LFLF_0009_AKOS_0002_aframe_599.svg'
            existing.write_text('existing character')
            cannon.install(output, local)
            self.assertEqual(existing.read_text(), 'existing character')
            self.assertEqual(len(list(costume.glob('*.svg'))), 15)
            before = {p.name: p.read_bytes() for p in costume.iterdir()}
            (output / 'svg/13.svg').write_text('tampered')
            with self.assertRaises(ValueError): cannon.install(output, local)
            self.assertEqual(before, {p.name: p.read_bytes() for p in costume.iterdir()})

    def test_edge_smoothing_passes_but_displacement_and_background_fail(self):
        original = Image.new('RGBA', (100, 100))
        ImageDraw.Draw(original).rectangle((0, 20, 70, 80), fill='brown')
        smoothed = Image.new('RGBA', original.size)
        ImageDraw.Draw(smoothed).rectangle((0, 19, 70, 81), fill='brown')
        self.assertTrue(cannon.alignment(original, smoothed)['passed'])
        moved = Image.new('RGBA', original.size)
        ImageDraw.Draw(moved).rectangle((0, 16, 70, 76), fill='brown')
        self.assertFalse(cannon.alignment(original, moved)['passed'])
        self.assertFalse(cannon.alignment(original, Image.new('RGBA', original.size, 'white'))['passed'])

    def test_uncertain_job_never_repeats_paid_request(self):
        with tempfile.TemporaryDirectory() as temp:
            output, _ = self.fixture(Path(temp))
            with q.journal(output) as db: q.save_job(db, '0', 'unknown')
            with patch.object(q, 'request') as request:
                with self.assertRaises(ValueError): cannon.generate(output, True)
                request.assert_not_called()

if __name__ == '__main__': unittest.main()
