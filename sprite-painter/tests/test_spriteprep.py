import unittest
from PIL import Image, ImageDraw
from spriteprep import smooth_mask

class MaskTests(unittest.TestCase):
    def test_contour_never_expands_canvas_or_source_bounds(self):
        image=Image.new('RGBA',(35,15))
        draw=ImageDraw.Draw(image);draw.polygon([(2,8),(31,2),(32,9),(21,12),(3,11)],fill=(40,25,5,255))
        mask=smooth_mask(image,(140,60));self.assertEqual(mask.size,(140,60))
        source=image.getchannel('A').getbbox();result=mask.getbbox()
        self.assertGreaterEqual(result[0],source[0]*4);self.assertGreaterEqual(result[1],source[1]*4)
        self.assertLessEqual(result[2],source[2]*4);self.assertLessEqual(result[3],source[3]*4)
        self.assertTrue(any(0<v<255 for _,v in mask.getcolors(256)))

    def test_holes_and_separate_components_survive(self):
        image=Image.new('RGBA',(20,20));draw=ImageDraw.Draw(image)
        draw.rectangle((1,1,12,17),fill='white');draw.rectangle((4,5,9,12),fill=(0,0,0,0));draw.rectangle((16,5,18,8),fill='white')
        mask=smooth_mask(image,(80,80))
        self.assertEqual(mask.getpixel((24,32)),0)
        self.assertEqual(mask.getpixel((68,24)),255)
        self.assertEqual(mask.getpixel((58,24)),0)
