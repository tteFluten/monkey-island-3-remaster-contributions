import unittest

import numpy as np

from quiver_curve_style import rounded_path, section, split


class CurveStyleTests(unittest.TestCase):
    def test_split_preserves_endpoints_and_joint(self):
        curve = np.array([[0., 0.], [2., 5.], [8., 5.], [10., 0.]])
        left, right = split(curve, .5)
        np.testing.assert_allclose(left[0], curve[0])
        np.testing.assert_allclose(right[-1], curve[-1])
        np.testing.assert_allclose(left[-1], right[0])
        np.testing.assert_allclose(section(curve, .25, .75)[0], split(curve, .25)[0][-1])

    def test_straight_open_curve_is_not_rounded(self):
        path, joins = rounded_path([[0, 0], [1, 0], [2, 0], [3, 0]], False, 1)
        self.assertEqual(joins, 0)
        self.assertTrue(path.startswith('M0.000000 0.000000'))
        self.assertTrue(path.endswith('3.000000 0.000000'))

    def test_closed_triangle_rounds_closing_join(self):
        points = [[0, 0], [3, 0], [6, 0], [9, 0], [6, 3], [3, 6], [0, 9]]
        path, joins = rounded_path(points, True, 1)
        self.assertEqual(joins, 3)
        self.assertTrue(path.endswith(' Z'))
        self.assertNotIn('nan', path)


if __name__ == '__main__':
    unittest.main()
