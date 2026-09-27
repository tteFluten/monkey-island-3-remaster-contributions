import unittest
import numpy as np
from PIL import Image
from alpha_cleanup import remove_magenta

class MagentaTests(unittest.TestCase):
    def test_key_unmix_and_preserve_interior(self):
        p=np.full((15,15,4),(255,0,255,255),dtype=np.uint8)
        p[3:12,3:12]=(20,20,20,255)
        p[2,3:12]=(138,10,138,255)
        p[6:9,6:9]=(255,0,255,255)
        out=np.array(remove_magenta(Image.fromarray(p)))
        self.assertEqual(out.shape,p.shape)
        self.assertTrue((out[0,:,3]==0).all())
        self.assertTrue((out[2,4:11,:3]==20).all())
        self.assertTrue(((out[2,4:11,3]>110)&(out[2,4:11,3]<145)).all())
        self.assertTrue((out[7,7]==p[7,7]).all())
        self.assertTrue((out[4,4]==p[4,4]).all())

    def test_no_magenta_reports_error(self):
        with self.assertRaises(ValueError):remove_magenta(Image.new('RGBA',(10,10),'white'))

    def test_nonstandard_background_and_thick_spill(self):
        p=np.full((30,30,4),(227,0,195,255),dtype=np.uint8)
        p[8:22,8:22]=(125,10,108,255)
        p[12:18,12:18]=(20,20,20,255)
        out=np.array(remove_magenta(Image.fromarray(p)))
        self.assertTrue((out[0,:,3]==0).all())
        self.assertEqual(tuple(out[10,15,:3]),(20,20,20))
        self.assertTrue(np.array_equal(out[12:18,12:18],p[12:18,12:18]))
