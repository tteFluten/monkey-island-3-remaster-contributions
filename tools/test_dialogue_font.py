"""Validate actual font coverage, transparent atlas cells and native metrics."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from prepare_dialogue_font import ROOT, character, make_atlas, nut_height, prepare, unicode_cmap


class DialogueFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = ROOT / '.playtest/hd/dialogue-font/efmi.TTF'
        if not cls.font.exists():
            cls.font = ROOT / '.context/attachments/ZmOmnY/efmi.TTF'
        if not cls.font.exists():
            raise unittest.SkipTest('Supply efmi.TTF locally to exercise actual font rasterization')
        cls.atlas, cls.binary, cls.details = make_atlas(cls.font, 30)
        cls.magic, cls.scale, cls.height, cls.cw, cls.ch = struct.unpack_from('<4sHHHH', cls.binary)

    def metric(self, code):
        return struct.unpack_from('<HHh', self.binary, 12 + code * 6)

    def cell(self, code):
        x, y = code % 16 * self.cw, code // 16 * self.ch
        return self.atlas.crop((x, y, x+self.cw, y+self.ch))

    def test_format_and_proportional_advances(self):
        self.assertEqual((self.magic, self.scale, self.height, self.ch), (b'DLG1', 4, 30, 120))
        self.assertEqual(len(self.binary), 1548)
        self.assertEqual(self.atlas.size, (self.cw*16, self.ch*16))
        self.assertGreater(self.metric(ord('W'))[1], self.metric(ord('i'))[1])

    def test_space_advances_without_visible_ink(self):
        self.assertEqual(self.metric(32)[0], 1)
        self.assertGreater(self.metric(32)[1], 0)
        self.assertIsNone(self.cell(32).getbbox())

    def test_character_mapping_and_missing_glyph_fallback(self):
        cmap = unicode_cmap(self.font.read_bytes())
        for code in (ord('A'), ord('g'), ord('?'), ord('!'), ord("'"), 233):
            self.assertIsNotNone(character(code, cmap))
            self.assertEqual(self.metric(code)[0], 1)
            self.assertIsNotNone(self.cell(code).getbbox())
        for code in (0, 9, 10, 31, 127, 129):
            self.assertIsNone(character(code, cmap))
            self.assertEqual(self.metric(code), (0, 0, 0))
            self.assertIsNone(self.cell(code).getbbox())
        self.assertIsNone(character(ord('A'), set()))

    def test_descenders_baseline_and_antialiasing(self):
        self.assertGreater(self.cell(ord('g')).getbbox()[3], self.cell(ord('A')).getbbox()[3])
        pixels = list(self.cell(ord('A')).getdata())
        self.assertTrue(any(0 < a < 255 for r,g,b,a in pixels))
        self.assertTrue(any(r == g == b == 0 and a == 255 for r,g,b,a in pixels))
        self.assertTrue(any(r == g == b == 255 and a == 255 for r,g,b,a in pixels))
        for code in range(256):
            if self.metric(code)[0]:
                cell = self.cell(code)
                # Each cell has padding on its right; no ink leaks into its neighbor.
                self.assertIsNone(cell.crop((self.cw-1, 0, self.cw, self.ch)).getbbox())

    def test_native_six_times_atlas_and_invalid_scale(self):
        atlas, binary, details = make_atlas(self.font, 30, 6)
        magic, scale, height, cw, ch = struct.unpack_from('<4sHHHH', binary)
        self.assertEqual((scale, height, ch), (6, 30, 180))
        self.assertEqual(atlas.size, (cw * 16, ch * 16))
        self.assertGreater(details['font_size_hd'], self.details['font_size_hd'])
        with self.assertRaises(ValueError):
            make_atlas(self.font, 30, 5)

    def test_repeatable_staging_and_source_preserved(self):
        resources = ROOT / '.playtest/game/RESOURCE'
        if not (resources / 'FONT0.NUT').exists():
            self.skipTest('Imported original NUT files required')
        original = self.font.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory)
            prepare(self.font, dest, resources)
            before = {str(p.relative_to(dest)): hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob("*") if p.is_file()}
            prepare(dest / 'efmi.TTF', dest, resources)
            after = {str(p.relative_to(dest)): hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual((dest / 'efmi.TTF').read_bytes(), original)
            for slot in range(5):
                self.assertEqual(struct.unpack_from('<H', (dest / '4x' / f'FONT{slot}.dat').read_bytes(), 6)[0],
                                 nut_height(resources / f'FONT{slot}.NUT'))


if __name__ == '__main__':
    unittest.main()
