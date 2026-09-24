import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from validate_rope_cutout import validate_rope


class RopeValidationTests(unittest.TestCase):
    def fixture(self, root):
        source=np.zeros((30,20,4),dtype='uint8');source[2:28,8:12]=[100,60,10,255]
        Image.fromarray(source).save(root/'source.png')
        rgba=np.array(Image.fromarray(source).resize((80,120),Image.Resampling.NEAREST))
        # One-pixel stair-step smoothing: close to the reference but <90% IoU.
        rgba[8:112,32,3]=0;rgba[8:112,47,3]=0
        rgba[:,:,:3]=[100,60,10]
        return rgba

    def check(self, root, rgba, change_rgb=False):
        Image.fromarray(rgba[:,:,:3]).save(root/'raw.png')
        if change_rgb:rgba=rgba.copy();rgba[50,40,0]=255
        Image.fromarray(rgba).save(root/'result.png')
        return validate_rope(root/'result.png',root/'raw.png',root/'source.png')

    def test_half_source_pixel_edge_smoothing_is_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);r=self.check(root,self.fixture(root))
            self.assertFalse(r['character_validation_passed'])
            self.assertTrue(r['passed'])

    def test_truncated_end_and_gap_are_rejected(self):
        for region in ((95,112),(50,62)):
            with self.subTest(region=region), tempfile.TemporaryDirectory() as temp:
                root=Path(temp);rgba=self.fixture(root);rgba[region[0]:region[1],:,3]=0
                self.assertFalse(self.check(root,rgba)['passed'])

    def test_changed_rgb_excessive_thinning_and_fringe_are_rejected(self):
        for defect in ('rgb','thin','fringe'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temp:
                root=Path(temp);rgba=self.fixture(root)
                if defect=='thin':rgba[:,32:38,3]=0
                if defect=='fringe':rgba[10:100,60:70,3]=64
                self.assertFalse(self.check(root,rgba,change_rgb=defect=='rgb')['passed'])


if __name__=='__main__':unittest.main()
