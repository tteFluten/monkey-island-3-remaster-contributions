import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deliveries import Deliveries, digest, encode, git, safe_path
import test_server as fixtures

class DeliveryTests(unittest.TestCase):
    def test_paths_cannot_escape_asset_package(self):
        for path in ('../secret','.context/secrets/key','assets/../../key','assets/x\\y','C:/key'):
            with self.assertRaises(ValueError):safe_path(path)

    def test_snapshot_lfs_branch_keeps_working_tree_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source='costumes/LFLF_0009_AKOS_0025_frame_0.png';master='assets/masters/topaz-4x/'+source;runtime='assets/runtime/topaz-cannon/'+source.replace('_frame_','_aframe_')
            image=fixtures.png();checksum=digest(image)
            rows=[dict(path=master,canonical=True,source_id=source,sha256=checksum,bytes=len(image),category='masters/topaz-4x',image=dict(width=8,height=8,mode='RGBA')),dict(path=runtime,derived_from=master,transform=dict(kind='copy',source_sha256=checksum),sha256=checksum,bytes=len(image),category='runtime/topaz-cannon')]
            for path in (master,runtime,'assets/references/topaz-cleaned/'+source):
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(image)
            (root/'assets/manifest.json').write_bytes(encode(dict(version=1,files=rows)))
            (root/'assets/metadata').mkdir();(root/'assets/metadata/topaz-scene-plan.json').write_bytes(encode(dict(scenes=[dict(id='room-0009',sources=[dict(source=source)])])))
            (root/'.gitattributes').write_text('*.png filter=lfs diff=lfs merge=lfs -text\n')
            git(root,'init');git(root,'config','user.name','Delivery test');git(root,'config','user.email','test@example.invalid');git(root,'lfs','install','--local')
            git(root,'add','assets','.gitattributes');git(root,'commit','-m','fixture');base=git(root,'rev-parse','HEAD').decode().strip();git(root,'update-ref','refs/remotes/origin/main',base)
            (root/'unrelated.txt').write_text('Keep staged');git(root,'add','unrelated.txt');staged=git(root,'write-tree')
            work=fixtures.painter.Workshop(root);id_=next(iter(work.frames));approval={id_:dict(sha256=checksum)}
            manager=Deliveries(work,SimpleNamespace(approvals=lambda:approval));manager.analyze('interior')
            self.assertEqual(manager.report['status'],'ready',manager.report)
            report=manager.branch(manager.report['id'],'scene-1-ship-v1')
            self.assertEqual(git(root,'write-tree'),staged)
            self.assertEqual(git(root,'rev-parse','HEAD').decode().strip(),base)
            self.assertEqual((root/master).read_bytes(),image)
            pointer=git(root,'show',report['commit']+':'+master)
            self.assertTrue(pointer.startswith(b'version https://git-lfs.github.com/spec/v1'))
            approval.clear();manager.report.pop('branch',None)
            with self.assertRaisesRegex(ValueError,'aprobación'):manager.branch(manager.report['id'],'another-branch')

    def test_cannot_label_blocked_delivery_as_reviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=SimpleNamespace(store=Path(tmp),root=Path(tmp));manager=Deliveries(work,None)
            manager.report=dict(id='test',status='blocked')
            with self.assertRaisesRegex(ValueError,'pendientes'):manager.branch('test')
