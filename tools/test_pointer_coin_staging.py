import json
from pathlib import Path
import struct
import tempfile
import unittest

from PIL import Image
from stage_pointer_coin import stage, digest


class PointerCoinStagingTests(unittest.TestCase):
    def fixture(self, root):
        package, local, originals = root / 'package', root / 'local', root / 'originals'
        cursors = package / 'cursors-6x/antialiased'
        coins = package / 'coin-6x/costumes'
        for p in (cursors, coins, originals, local / 'game', local / 'hd'):
            p.mkdir(parents=True)
        names = ['system-cursor-icon'] + [f'arrow-{i}' for i in range(14)]
        index = struct.pack('<I', len(names))
        manifest = {}
        for name in names:
            index += name.encode().ljust(40, b'\0') + bytes(6)
            for state in (0, 1):
                filename = f'0003_{name}_{state:04d}.png'
                manifest[filename] = {}
                Image.new('RGBA', (2, 3)).save(originals / filename)
                im = Image.new('RGBA', (12, 18))
                im.paste((255, state * 100, 0, 255), (3, 3, 9, 15))
                im.save(cursors / filename)
        (package / 'cursors-6x/manifest.json').write_text(json.dumps(manifest))
        (local / 'game/COMI.LA0').write_bytes(b'DOBJ' + struct.pack('>I', len(index) + 8) + index)
        (local / 'hd/object_map.json').write_text('{"900":{"name":"untouched","rooms":{}}}')
        for frame in range(63, 68):
            im = Image.new('RGBA', (696, 708))
            im.paste((200, 140, 30, 255), (30, 30, 666, 678))
            im.save(coins / f'LFLF_0001_AKOS_0001_aframe_{frame}.png')
        return package, local, originals

    def test_stages_all_states_without_modifying_masters_or_unrelated_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            package, local, originals = self.fixture(Path(directory))
            masters = {p: digest(p) for p in package.rglob('*.png')}
            report = stage(package, local, originals)
            self.assertEqual(len(report['files']), 35)
            for record in report['files']:
                dest = local / 'hd' / record['target']
                self.assertEqual(digest(dest), record['destination_sha256'])
                with Image.open(dest) as im:
                    self.assertEqual(list(im.size), record['size'])
                    self.assertEqual(im.mode, 'RGBA')
                    self.assertEqual(im.getchannel('A').getextrema()[0], 0)
            self.assertEqual(masters, {p: digest(p) for p in masters})
            self.assertIn('900', json.loads((local / 'hd/object_map.json').read_text()))
            self.assertEqual(digest(local / 'hd/objects/0003_system-cursor-icon_0000.png'),
                             digest(local / 'hd/objects/0003_system-cursor-icon_0001.png'))

    def test_invalid_last_coin_leaves_install_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            package, local, originals = self.fixture(Path(directory))
            bad = package / 'coin-6x/costumes/LFLF_0001_AKOS_0001_aframe_67.png'
            Image.new('RGB', (696, 708)).save(bad)
            before = (local / 'hd/object_map.json').read_bytes()
            with self.assertRaises(ValueError):
                stage(package, local, originals)
            self.assertEqual((local / 'hd/object_map.json').read_bytes(), before)
            self.assertEqual(list((local / 'hd').rglob('*.png')), [])
            self.assertFalse((local / 'pointer-coin-staging.json').exists())


if __name__ == '__main__':
    unittest.main()
