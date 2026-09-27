import unittest
import numpy as np
from PIL import Image
from inventory_states import highlight

class InventoryTests(unittest.TestCase):
    def test_red_state_keeps_illustration_and_canvas(self):
        a=np.zeros((32,32,4),dtype=np.uint8);a[12:20,12:20]=(20,100,190,255)
        out=np.array(highlight(Image.fromarray(a),(255,59,15),(8,8)))
        self.assertEqual(out.shape,a.shape)
        self.assertTrue(np.array_equal(out[12:20,12:20],a[12:20,12:20]))
        self.assertEqual(tuple(out[10,15]),(255,59,15,255))
        self.assertEqual(out[0,0,3],0)
