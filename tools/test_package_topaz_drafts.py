import tempfile
import shutil
import unittest
from pathlib import Path

from PIL import Image
from asset_pack import verify
from package_topaz_drafts import package
from quiver_cannon import atomic
from topaz_character_cutouts import digest
from topaz_scenes import read


class PackagingTests(unittest.TestCase):
    def fixture(self,root):
        files=[]
        def metadata(path,value):
            atomic(root/path,value)
            files.append(dict(path=path,sha256=digest(root/path),bytes=(root/path).stat().st_size,
                              category='metadata',review_status='unreviewed'))
        sources=['costumes/LFLF_0001_AKOS_0006_frame_1.png','objects/0019-test_0000.png',
                 'objects/0003_inventory-bg-object_0000.png']
        assets={};records=[]
        for source in sources:
            master=root/'output/topaz-scenes/room-0019/4x'/source
            master.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGBA',(16,20),(50,100,130,255)).save(master)
            assets[source]=dict(master=str(master),sha256=digest(master),state='rejected',validation_passed=False)
            clean=root/'output/topaz-batch/cleaned'/source;clean.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGBA',(4,5),(50,100,130,255)).save(clean)
            records.append(dict(source=source,cleaned_sha256=digest(clean)))
            runtime=([f'{pack}/{source.replace("_frame_","_aframe_")}' for pack in ('topaz-cannon','topaz-crisp')]
                     if source.startswith('costumes/') else [source])
            for target in runtime:
                path=root/'.playtest/hd'/target;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(master.read_bytes())
        inventory=sources[-1];name='assets/masters/ui-4x/'+inventory
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(Path(assets[inventory]['master']).read_bytes())
        files.append(dict(path=name,sha256=digest(path),bytes=path.stat().st_size,category='masters/ui-4x',
                          canonical=True,review_status='manual-replacement',
                          destination='output/topaz-batch/4x/'+inventory))
        metadata('assets/metadata/artwork-review.json',{inventory:dict(state='manual-replacement')})
        metadata('assets/metadata/topaz-library.json',dict(records=[records[-1]]))
        scene=dict(id='room-0019',sources=[dict(source=s) for s in sources])
        metadata('assets/metadata/topaz-scene-plan.json',dict(scenes=[scene]))
        metadata('assets/runtime/object_map.json',{})
        atomic(root/'.playtest/hd/object_map.json',{})
        atomic(root/'output/topaz-scenes/plan.json',dict(scenes=[scene]))
        atomic(root/'output/topaz-batch/manifest.json',dict(records=records))
        atomic(root/'.playtest/draft-install/receipt.json',dict(assets=assets))
        atomic(root/'assets/manifest.json',dict(version=1,files=files))
        return sources

    def test_characters_objects_and_manual_inventory_remain_portable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sources=self.fixture(root)
            self.assertEqual(package(root)['new_assets'],2)
            verify(root,media=True)
            self.assertEqual(package(root)['new_assets'],0)
            verify(root,media=True)
            manifest=read(root/'assets/manifest.json')
            inventory=[r for r in manifest['files'] if r.get('destination')=='output/topaz-batch/4x/'+sources[-1]]
            self.assertEqual(len(inventory),1)
            self.assertEqual(inventory[0]['review_status'],'manual-replacement')
            reviews=read(root/'assets/metadata/artwork-review.json')
            self.assertEqual(reviews[sources[0]]['state'],'rejected')
            self.assertEqual(reviews[sources[-1]]['state'],'manual-replacement')

    def test_changed_runtime_is_rejected_before_pack_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sources=self.fixture(root)
            before=(root/'assets/manifest.json').read_bytes()
            (root/'.playtest/hd'/sources[1]).write_bytes(b'changed')
            with self.assertRaises(ValueError):package(root)
            self.assertEqual(before,(root/'assets/manifest.json').read_bytes())
            self.assertFalse((root/'assets/masters/topaz-4x').exists())

    def test_new_room_is_packaged_with_current_workspace_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sources=self.fixture(root)
            atomic(root/'assets/metadata/topaz-scene-plan.json',dict(scenes=[]))
            package(root)
            plan=read(root/'assets/metadata/topaz-scene-plan.json')
            self.assertEqual([s['id'] for s in plan['scenes']],['room-0019'])
            self.assertEqual(plan['total_sources'],len(sources))
            reviews=read(root/'assets/metadata/artwork-review.json')
            self.assertTrue(reviews[sources[0]]['master'].startswith(f'source:{root.name}/output/'))
            verify(root,media=True)

    def test_staged_runtime_can_be_packaged_without_touching_live_textures(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sources=self.fixture(root)
            staged=root/'.context/staged'
            shutil.copytree(root/'.playtest',staged)
            live=root/'.playtest/hd'/sources[1]
            live.write_bytes(b'live texture must remain untouched')
            self.assertEqual(package(root,staged)['new_assets'],2)
            self.assertEqual(live.read_bytes(),b'live texture must remain untouched')
            verify(root,media=True)


if __name__=='__main__':unittest.main()
