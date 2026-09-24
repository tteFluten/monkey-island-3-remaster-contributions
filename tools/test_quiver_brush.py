import unittest
import numpy as np
from quiver_brush import brush_contour, path_data, paint


class BrushTests(unittest.TestCase):
    def test_pressure_geometry_is_deterministic_and_centered(self):
        path = dict(points=[[0,0],[3,0],[7,0],[10,0]], closed=False)
        actual = brush_contour(path, .7)
        self.assertEqual(actual, brush_contour(path, .7))
        self.assertTrue(actual.endswith(' Z'))
        vertices = np.array([[float(v) for v in pair.split()] for pair in actual[1:-2].split(' L')])
        self.assertAlmostEqual(vertices[:,0].min(), 0)
        self.assertAlmostEqual(vertices[:,0].max(), 10)
        self.assertAlmostEqual(vertices[:,1].min(), -vertices[:,1].max())
        self.assertLess(abs(vertices[0,1]), vertices[:,1].max())
        self.assertLessEqual(vertices[:,1].max(), .7*1.1/2)

    def test_degenerate_curve_is_empty(self):
        self.assertEqual(brush_contour(dict(points=[[1,1]]*4,closed=False),.7),'')

    def test_original_fill_curve_is_retained(self):
        path = dict(points=[[1,2],[3,4],[5,6],[7,8]], closed=True)
        self.assertEqual(path_data(path), 'M1.00000 2.00000 C3.00000 4.00000 5.00000 6.00000 7.00000 8.00000 Z')
        self.assertEqual(paint(0x801b2330), ('#30231b',128/255))


if __name__ == '__main__': unittest.main()
