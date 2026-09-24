import unittest
import xml.etree.ElementTree as ET

from quiver_ui_clip import flatten, polygons, clip
from quiver_cannon import normalize_svg


class ClipTests(unittest.TestCase):
    def test_relative_subpaths_reset_to_start_after_close(self):
        self.assertEqual(polygons('m10 20h5v5h-5z m10 0h1v1h-1z'),
                         [[(10, 20), (15, 20), (15, 25), (10, 25)],
                          [(20, 20), (21, 20), (21, 21), (20, 21)]])

    def test_intersection_retains_only_inside_coordinates(self):
        points = clip([(-1, -1), (3, -1), (3, 3), (-1, 3)], (0, 0, 2, 2))
        self.assertEqual(set(points), {(0, 0), (2, 0), (2, 2), (0, 2)})
        self.assertEqual(clip([(3, 3), (4, 3), (4, 4)], (0, 0, 2, 2)), [])

    def test_plain_rectangular_clip_becomes_valid_paths(self):
        raw = '<svg viewBox="0 0 40 40"><defs><clipPath id="a"><rect transform="translate(10 20)" width="5" height="5"/></clipPath></defs><g clip-path="url(#a)"><path d="M0 0H40V40H0Z"/></g></svg>'
        result, corrections = flatten(raw)
        self.assertEqual(len(corrections), 1)
        normalize_svg(result, [40, 40])
        path = next(n for n in ET.fromstring(result).iter() if n.tag == 'path')
        self.assertEqual(set(polygons(path.get('d'))[0]), {(10, 20), (15, 20), (15, 25), (10, 25)})

    def test_only_noop_alpha_mask_is_removed(self):
        raw = '<svg viewBox="0 0 40 40"><mask id="m" x="0" y="0" width="40" height="40" style="mask-type:alpha" maskUnits="userSpaceOnUse"><rect width="40" height="40" fill="#aabbcc"/></mask><g mask="url(#m)"><path d="M5 5h10v10H5z"/></g></svg>'
        result, corrections = flatten(raw)
        self.assertEqual(len(corrections), 1)
        normalize_svg(result, [40, 40])
        for bad in (raw.replace('mask-type:alpha', 'mask-type:luminance'),
                    raw.replace('fill="#aabbcc"', 'fill="#aabbcc" opacity="0.5"'),
                    raw.replace('<rect width="40"', '<rect width="20"')):
            with self.assertRaises(ValueError):
                flatten(bad)

    def test_unsupported_content_stays_rejected(self):
        for raw in ('<svg viewBox="0 0 40 40"><image href="file:///tmp/a"/></svg>',
                    '<svg viewBox="0 0 40 40"><script/></svg>'):
            result, _ = flatten(raw)
            with self.assertRaises(ValueError):
                normalize_svg(result, [40, 40])
        with self.assertRaises(ValueError):
            polygons('M0 0 C1 2 3 4 5 6z')


if __name__ == '__main__':
    unittest.main()
