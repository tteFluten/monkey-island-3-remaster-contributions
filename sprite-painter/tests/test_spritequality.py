import unittest
from PIL import Image, ImageDraw
from spritequality import assess_fidelity

class FidelityTests(unittest.TestCase):
    def sprite(self):
        im=Image.new('RGBA',(24,24));d=ImageDraw.Draw(im)
        d.rectangle((3,3,20,20),fill=(100,65,20,255),outline=(25,20,15,255),width=2)
        return im
    def test_identical_scaled_sprite_passes(self):
        im=self.sprite();self.assertTrue(assess_fidelity(im,im.resize((96,96)))['passed'])
    def test_brightness_change_rejected(self):
        im=self.sprite();bright=im.copy()
        bright.putdata([tuple(min(255,v+65) for v in p[:3])+(p[3],) for p in im.getdata()])
        self.assertIn('color o sombreado alterado',assess_fidelity(im,bright)['issues'])
    def test_thicker_stroke_rejected(self):
        im=self.sprite();thick=im.copy();ImageDraw.Draw(thick).rectangle((3,3,20,20),outline=(25,20,15,255),width=6)
        self.assertIn('cobertura del trazo oscuro alterada',assess_fidelity(im,thick)['issues'])
    def test_enlarged_subject_rejected(self):
        im=self.sprite();big=Image.new('RGBA',im.size,(100,65,20,255))
        self.assertIn('silueta o espesor alterado',assess_fidelity(im,big)['issues'])
