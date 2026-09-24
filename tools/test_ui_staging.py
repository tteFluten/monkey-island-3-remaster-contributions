import json
import struct
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from stage_ui import stage_ui
from prepare_ui_batch import prepare
from prepare_topaz import digest


class UIStagingTests(unittest.TestCase):
    def test_only_completed_ui_is_staged_at_four_times_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch, local = root / 'batch', root / 'local'
            source = 'objects/0003_system-cursor-icon_0000.png'
            menu = 'objects/0092_saveload-checkbox_0000.png'
            master = batch / '6x' / source
            master.parent.mkdir(parents=True)
            Image.new('RGBA', (12, 18), (180, 50, 10, 128)).save(master)
            before = digest(master)
            clean = batch / 'cleaned' / source
            clean.parent.mkdir(parents=True)
            Image.new('RGBA', (2, 3), (180, 50, 10, 128)).save(clean)
            record = dict(source=source, canonical=source, size=[2, 3])
            (batch / 'manifest.json').write_text(json.dumps(dict(records=[record, dict(source=menu, canonical=menu, size=[2, 3])])))
            scope = prepare(batch)
            self.assertEqual(scope['sources'], [source])
            index = struct.pack('<I', 1) + b'system-cursor-icon'.ljust(40, b'\0') + bytes(6)
            (local / 'game').mkdir(parents=True)
            (local / 'game/COMI.LA0').write_bytes(b'DOBJ' + struct.pack('>I', len(index) + 8) + index)
            (local / 'hd').mkdir()
            previous = {'900': {'name': 'unrelated', 'rooms': {'9': {'states': [0]}}}}
            (local / 'hd/object_map.json').write_text(json.dumps(previous))
            (local / 'topaz-staging.json').write_text('character report preserved')
            stage_ui(batch, local)
            with Image.open(local / 'hd' / source) as staged:
                self.assertEqual(staged.size, (8, 12))
                self.assertEqual(staged.getpixel((5, 5))[3], 128)
            self.assertEqual(digest(master), before)
            self.assertEqual((local / 'topaz-staging.json').read_text(), 'character report preserved')
            report = json.loads((local / 'ui-staging.json').read_text())
            self.assertEqual(report['scale'], 4)
            mapping = json.loads((local / 'hd/object_map.json').read_text())
            self.assertEqual(mapping['900'], previous['900'])
            self.assertEqual(mapping['0']['rooms']['3']['states'], [0])
            self.assertFalse((local / 'hd' / menu).exists())


if __name__ == '__main__':
    unittest.main()
