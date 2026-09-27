import unittest
import numpy as np
from PIL import Image
from alpha_cleanup import clean

class CleanupTests(unittest.TestCase):
    def test_open_cut_preserves_rgba_but_other_edges_are_cleaned(self):
        original=Image.new('RGBA',(20,20))
        for y in range(2,18):
            for x in range(5,15):original.putpixel((x,y),(230,170,130,255) if 6<x<13 else (25,20,15,255))
        source=original.resize((80,80),Image.Resampling.NEAREST)
        plain=clean(source,.5,tint_strength=1)
        protected=clean(source,.5,tint_strength=1,reference=original,protect_seams=True)
        self.assertEqual(protected.getpixel((28,71)),source.getpixel((28,71)))
        self.assertNotEqual(plain.getpixel((28,71)),source.getpixel((28,71)))
        self.assertLess(protected.getpixel((20,40))[3],source.getpixel((20,40))[3])

    def test_tint_removes_light_rim_without_changing_alpha_or_interior(self):
        image=Image.new('RGBA',(11,11),(0,0,0,0))
        for y in range(2,9):
            for x in range(2,9):image.putpixel((x,y),(35,22,15,255))
        for y in range(2,9):image.putpixel((2,y),(180,150,120,180))
        plain=clean(image,.5);tinted=clean(image,.5,tint_strength=1)
        self.assertEqual(plain.getchannel('A').tobytes(),tinted.getchannel('A').tobytes())
        self.assertLess(tinted.getpixel((2,5))[0],plain.getpixel((2,5))[0])
        self.assertEqual(tinted.getpixel((5,5)),plain.getpixel((5,5)))
        self.assertLess(clean(image,0,tint_strength=1).getpixel((2,5))[0],180)

    def test_tint_does_not_invent_ink_or_wrap_across_canvas(self):
        image=Image.new('RGBA',(12,9),(0,0,0,0))
        for y in range(9):
            image.putpixel((0,y),(180,150,120,180))
            image.putpixel((11,y),(15,10,5,255))
        self.assertEqual(clean(image,0,tint_strength=1).tobytes(),image.tobytes())
        with self.assertRaises(ValueError):clean(image,0,tint_strength=float('nan'))

    def test_preserves_rgb_and_never_expands_alpha(self):
        image=Image.new('RGBA',(9,9),(100,60,30,0))
        for x in range(2,7):
            for y in range(2,7):image.putpixel((x,y),(100,60,30,255))
        result=clean(image,.5)
        a=np.asarray(image);b=np.asarray(result)
        self.assertTrue(np.array_equal(a[...,:3],b[...,:3]))
        self.assertTrue(np.all(b[...,3]<=a[...,3]))
        self.assertLess(b[...,3].sum(),a[...,3].sum())
        self.assertEqual(result.size,image.size)
        self.assertEqual(result.getpixel((4,4))[3],255)

    def test_dark_line_is_protected_more_than_bright_fringe(self):
        dark=Image.new('RGBA',(7,7),(20,20,20,255))
        bright=Image.new('RGBA',(7,7),(180,180,180,255))
        self.assertGreater(clean(dark,1).getpixel((0,3))[3],clean(bright,1).getpixel((0,3))[3])
        self.assertEqual(clean(dark,0).tobytes(),dark.tobytes())
        with self.assertRaises(ValueError):clean(dark,float('nan'))
