import unittest
import numpy as np
from PIL import Image, ImageDraw
from refine_topaz_edges import refine


class RefineEdgesTests(unittest.TestCase):
    def test_canvas_transparency_shadow_and_source_are_preserved(self):
        source = Image.new('RGBA', (16, 16))
        draw = ImageDraw.Draw(source)
        draw.rectangle((4, 3, 11, 11), fill=(220, 140, 30, 255), outline=(11, 11, 7, 255))
        draw.rectangle((3, 13, 12, 14), fill=(0, 0, 0, 128))
        before = source.tobytes()
        result = source.resize((96, 96), Image.Resampling.NEAREST)
        output = refine(result, source, crisp=True)
        pixels = np.asarray(output)
        self.assertEqual(output.size, result.size)
        self.assertEqual(output.mode, 'RGBA')
        self.assertEqual(source.tobytes(), before)
        self.assertEqual(tuple(pixels[48, 48]), (220, 140, 30, 255))
        self.assertFalse(pixels[pixels[:, :, 3] == 0].any())
        self.assertTrue(0 < pixels[83, 48, 3] < 192)
        self.assertEqual(tuple(pixels[83, 48, :3]), (0, 0, 0))

    def test_one_source_pixel_stroke_survives(self):
        source = Image.new('RGBA', (16, 16))
        ImageDraw.Draw(source).line((8, 2, 8, 13), fill=(11, 11, 7, 255), width=1)
        output = refine(source.resize((96, 96)), source, crisp=True)
        self.assertGreater(np.asarray(output)[48, :, 3].max(), 200)

    def test_mismatched_geometry_fails(self):
        with self.assertRaises(ValueError):
            refine(Image.new('RGBA', (12, 11)), Image.new('RGBA', (2, 2)))


if __name__ == '__main__':
    unittest.main()
