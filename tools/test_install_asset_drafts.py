from pathlib import Path
import tempfile
import unittest

from PIL import Image
from install_asset_drafts import install
from quiver_cannon import atomic
from topaz_character_cutouts import digest
from topaz_scenes import read


class DraftInstallTests(unittest.TestCase):
    def fixture(self,root):
        out=root/'scenes';batch=root/'batch';local=root/'local';local.mkdir()
        source='costumes/LFLF_0016_AKOS_0094_frame_0.png';alias='costumes/LFLF_0051_AKOS_0255_frame_0.png'
        master=out/'room-0016/4x'/source;master.parent.mkdir(parents=True)
        Image.new('RGBA',(16,20),(150,70,20,240)).save(master)
        atomic(out/'room-0016/jobs.json',{source:dict(state='rejected',validation=dict(passed=False,sha256=digest(master)))})
        atomic(batch/'manifest.json',dict(records=[dict(source=s,size=[4,5],cleaned_sha256='input') for s in (source,alias)]))
        atomic(out/'plan.json',dict(source_batch=str(batch),scenes=[dict(id='room-0016',sources=[dict(source=source,size=[4,5],operation='upscale-matting'),dict(source=alias,size=[4,5],operation='alias',parent=source)])]))
        return out,local,source,alias,master

    def test_rejected_drafts_and_aliases_install_without_approval_and_back_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out,local,s,a,master=self.fixture(root)
            target=local/'hd/topaz-cannon'/s.replace('_frame_','_aframe_');target.parent.mkdir(parents=True);target.write_bytes(b'old')
            before=(out/'room-0016/jobs.json').read_bytes();r=install(out,local)
            self.assertEqual(r['new_or_changed'],2)
            self.assertEqual(target.read_bytes(),master.read_bytes())
            self.assertEqual((Path(r['backup'])/'runtime'/target.relative_to(local)).read_bytes(),b'old')
            self.assertEqual((local/'hd/topaz-crisp'/a.replace('_frame_','_aframe_')).read_bytes(),master.read_bytes())
            self.assertEqual((out/'room-0016/jobs.json').read_bytes(),before)
            self.assertFalse((out/'reviews').exists())
            self.assertEqual(install(out,local)['new_or_changed'],0)

    def test_tampering_and_live_game_block_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out,local,s,a,master=self.fixture(root)
            master.write_bytes(b'bad')
            with self.assertRaises(ValueError):install(out,local)
            self.assertFalse((local/'hd').exists())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out,local,s,a,master=self.fixture(root)
            import os
            atomic(local/'process.json',dict(pid=os.getpid()))
            with self.assertRaises(RuntimeError):install(out,local)
            self.assertFalse((local/'hd').exists())


if __name__=='__main__':unittest.main()
