import unittest
from PIL import Image,ImageDraw
from asset_audit import compare

class AuditTests(unittest.TestCase):
    def source(self):
        image=Image.new('RGBA',(20,20))
        ImageDraw.Draw(image).rectangle((4,4,15,15),fill=(160,80,30,255),outline=(20,20,20,255),width=2)
        return image
    def test_same_asset_at_4x_has_no_flags(self):
        source=self.source()
        report=compare(source,source.resize((80,80),Image.Resampling.NEAREST))
        self.assertTrue(report['passed'],report)
    def test_flags_color_and_shape_separately(self):
        source=self.source();changed=source.copy()
        ImageDraw.Draw(changed).rectangle((6,6,13,13),fill=(20,200,230,255))
        self.assertIn('Color desviado',compare(source,changed)['issues'])
        moved=Image.new('RGBA',source.size);moved.paste(source,(4,0))
        self.assertIn('Forma desviada',compare(source,moved)['issues'])
    def test_transparent_rgb_does_not_trigger_color_alarm(self):
        a=Image.new('RGBA',(8,8),(255,0,255,0));b=Image.new('RGBA',(32,32),(0,255,0,0))
        self.assertTrue(compare(a,b)['passed'])
