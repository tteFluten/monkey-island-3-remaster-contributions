from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import quiver_cannon as q
import quiver_sources as qs

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}">'
       '<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#c83232"/></svg>')


class QuiverSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = Path(self.tmp.name)
        self.root, self.output = root, root/'out'
        sprite = root/'assets/references/topaz-cleaned/costumes/LFLF_0009_AKOS_0032_frame_0.png'
        sprite.parent.mkdir(parents=True)
        image = Image.new('RGBA', (20, 30)); image.paste((200, 50, 50, 255), (2, 2, 18, 28)); image.save(sprite)
        layer = root/'extracted/objects_layers/0009_hook-object_0000.png'
        layer.parent.mkdir(parents=True)
        canvas = Image.new('RGBA', (64, 48)); canvas.paste((200, 50, 50, 255), (10, 12, 20, 30)); canvas.save(layer)
        background = root/'extracted/backgrounds/0009_cannon.png'
        background.parent.mkdir(parents=True); Image.new('RGB', (64, 48), (10, 20, 30)).save(background)
        self.patch = patch.object(qs, 'ROOT', root); self.patch.start()
        self.keys = ['costumes/LFLF_0009_AKOS_0032_frame_0.png', 'objects_layers/0009_hook-object_0000.png',
                     'backgrounds/0009_cannon.png']

    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()

    def fake(self, output_tokens):
        manifest = json.loads((self.output/'manifest.json').read_text())
        calls = []
        def request(endpoint, payload=None):
            calls.append(endpoint)
            if endpoint == '/models':
                return {'data': [{'id': 'arrow-2', 'billing': {'rates': {'input': 0, 'output': 10_000}}}]}, 'm'
            # Registered back onto the padded canvas: draw the sprite's own box.
            record = next(r for r in manifest['records']
                          if (self.output/'references'/r['source']).read_bytes() ==
                          __import__('base64').b64decode(payload['image']['base64']))
            c = record['reference_canvas']
            with Image.open(self.output/'cleaned'/record['source']) as im:
                x0, y0, x1, y1 = im.getchannel('A').getbbox() if im.mode == 'RGBA' else (0, 0, *im.size)
            svg = SVG.format(s=c['side'], x=c['x'] + x0, y=c['y'] + y0, w=x1 - x0, h=y1 - y0)
            return {'id': 'r', 'data': [{'svg': svg}], 'usage': {'input_tokens': 0, 'output_tokens': output_tokens}}, 'x'
        return request, calls

    def test_prepare_crops_layers_and_flags_backgrounds(self):
        qs.prepare(self.output, self.keys)
        records = {r['source']: r for r in json.loads((self.output/'manifest.json').read_text())['records']}
        self.assertEqual(records['objects_layers/0009_hook-object_0000.png']['crop'], [8, 10, 22, 32])
        self.assertEqual(records['objects_layers/0009_hook-object_0000.png']['size'], [14, 22])
        self.assertTrue(records['backgrounds/0009_cannon.png']['opaque'])
        self.assertEqual(records['costumes/LFLF_0009_AKOS_0032_frame_0.png']['input'],
                         'assets/references/topaz-cleaned/costumes/LFLF_0009_AKOS_0032_frame_0.png')
        with self.assertRaises(ValueError): qs.prepare(self.output, self.keys[:1])

    def test_ceiling_stops_before_a_request_could_exceed_it(self):
        qs.prepare(self.output, self.keys)
        request, calls = self.fake(output_tokens=3_000_000)  # $0.30 each at the fake rate
        with patch.object(q, 'request', request), patch.object(qs, 'RESERVE', dict(backgrounds=2.0, default=0.5)):
            qs.generate(self.output, max_usd=1.0)
        # Sprite ($0.30), layer (0.30 + 0.5 reserve <= 1), background needs a $2 reserve: stopped.
        self.assertEqual(calls.count('/svgs/vectorizations'), 2)
        with closing(q.journal(self.output)) as db:
            spent, largest = qs.spent(db, qs.rates(self.output))
            states = [q.job(db, r['artwork_sha256'])[0]
                      for r in json.loads((self.output/'manifest.json').read_text())['records']]
        self.assertAlmostEqual(spent, 0.6); self.assertEqual(states[:2], ['geometry_passed'] * 2)
        self.assertIsNone(states[2])

    def test_rectangular_clip_is_applied_after_render(self):
        qs.prepare(self.output, self.keys[:1], prompt='Redraw {side}')
        record = json.loads((self.output/'manifest.json').read_text())['records'][0]
        c = record['reference_canvas']
        # Curved paths under a band clip: the clip keeps only the top half of the sprite's box.
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}"><defs><clipPath id="k">'
               '<rect transform="translate(0 {y})" width="{s}" height="{h}"/></clipPath></defs>'
               '<g clip-path="url(#k)"><path d="M{x0} {y0} C{x0} {y0} {x1} {y0} {x1} {y0} L{x1} {y1} L{x0} {y1} Z" fill="#c83232"/></g></svg>'
               ).format(s=c['side'], y=c['y'], h=15, x0=c['x'] + 2, y0=c['y'] + 2, x1=c['x'] + 18, y1=c['y'] + 28)
        q.atomic(self.output/'raw'/f"{record['artwork_sha256']}.json", {'data': [{'svg': svg}]})
        report = qs.validate(self.output, record, generated=True)
        self.assertFalse(report['svg_engine_compatible'])
        self.assertEqual(report['corrections'][0]['type'], 'rect-clip-applied-after-render')
        with Image.open(self.output/'4x'/f"{record['artwork_sha256']}.png") as render:
            self.assertEqual(render.getpixel((40, 20))[3], 255)   # inside the band
            self.assertEqual(render.getpixel((40, 100))[3], 0)    # below the band: cleared

    def test_failed_request_is_journaled_and_blocks_reruns(self):
        qs.prepare(self.output, self.keys[:1])
        def broken(endpoint, payload=None):
            if endpoint == '/models':
                return {'data': [{'id': 'arrow-2', 'billing': {'rates': {'output': 1}}}]}, 'm'
            raise TimeoutError()
        with patch.object(q, 'request', broken):
            with self.assertRaises(RuntimeError): qs.generate(self.output, max_usd=5)
            with self.assertRaises(ValueError): qs.generate(self.output, max_usd=5)


if __name__ == '__main__':
    unittest.main()
