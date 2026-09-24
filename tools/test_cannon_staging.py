import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from stage_cannon import stage
from prepare_topaz import digest


class CannonStagingTests(unittest.TestCase):
    def test_exact_four_times_masters_go_to_both_packs_without_touching_other_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            batch, local = Path(directory) / 'batch', Path(directory) / 'local'
            source = 'costumes/LFLF_0009_AKOS_0026_frame_0.png'
            master = batch / '4x' / source
            master.parent.mkdir(parents=True)
            Image.new('RGBA', (12, 8), (50, 100, 150, 128)).save(master)
            before = digest(master)
            (batch / 'manifest.json').write_text(json.dumps(dict(records=[dict(source=source, size=[3, 2])])))
            (batch / 'cannon-sprites-scope.json').write_text(json.dumps(dict(sources=[source])))
            unrelated = local / 'hd/topaz-cannon/costumes/keep.png'
            unrelated.parent.mkdir(parents=True)
            unrelated.write_bytes(b'preserved')
            stage(batch, local)
            for pack in ('topaz-cannon', 'topaz-crisp'):
                output = local / 'hd' / pack / source.replace('_frame_', '_aframe_')
                self.assertEqual(digest(output), before)
            self.assertEqual(digest(master), before)
            self.assertEqual(unrelated.read_bytes(), b'preserved')
            # Reject a wrong-size result before replacing either installed file.
            Image.new('RGBA', (18, 12), 'red').save(master)
            with self.assertRaises(ValueError):
                stage(batch, local)
            self.assertEqual(digest(output), before)


if __name__ == '__main__':
    unittest.main()
