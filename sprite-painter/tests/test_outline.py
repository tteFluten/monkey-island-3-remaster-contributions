import unittest
import numpy as np
from PIL import Image
from alpha_cleanup import outline

class OutlineTests(unittest.TestCase):
    def test_both_widths_preserve_art_and_dimensions(self):
        pixels=np.zeros((30,30,4),dtype=np.uint8);pixels[10:20,10:20]=(20,50,90,255)
        for preset,width,color in [('white-2',2,(255,255,255)),('red-4',4,(255,59,15))]:
            out=np.array(outline(Image.fromarray(pixels),preset))
            self.assertEqual(out.shape,pixels.shape)
            self.assertTrue(np.array_equal(out[10:20,10:20],pixels[10:20,10:20]))
            self.assertEqual(tuple(out[15,10-width]),(*color,255))
            self.assertEqual(out[15,9-width,3],0)

    def test_opaque_background_is_not_outlined(self):
        with self.assertRaisesRegex(ValueError,'transparencia'):
            outline(Image.new('RGBA',(20,20),'white'),'white-2')
