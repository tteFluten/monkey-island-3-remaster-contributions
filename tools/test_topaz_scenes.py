import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from topaz_batch import job_key
from topaz_character_cutouts import digest, run
from topaz_scenes import prepare, prepare_scene, materialize, process, review_scene, install_scene
from test_topaz_character_cutouts import FakeAPI


class SceneTests(unittest.TestCase):
    def fixture(self, root):
        batch=root/'batch'; records=[]
        definitions=[('objects/0009_hook_0000.png',(18,24),(20,90,150,180)),
                     ('objects/0010_same-hook_0000.png',(18,24),(20,90,150,180)),
                     ('objects/0009_solid_0000.png',(24,30),(150,110,50,255)),
                     ('objects_layers/0009_hook_0000.png',(40,50),None),
                     ('objects/0087_easyhard_0000.png',(24,30),(150,110,50,255)),
                     ('objects_layers/0087_easyhard_0000.png',(40,50),None)]
        for source,size,color in definitions:
            clean=batch/'cleaned'/source;clean.parent.mkdir(parents=True,exist_ok=True)
            im=Image.new('RGBA',size,color or (0,0,0,0));im.save(clean)
            record=dict(source=source,size=list(size),cleaned_sha256=digest(clean),canonical=source)
            if source.startswith('objects_layers/'):
                record.update(derived_from=source.replace('objects_layers/','objects/'),offset=[3,5]);record.pop('canonical')
            records.append(record)
        (batch/'manifest.json').write_text(json.dumps(dict(records=records)))
        return batch

    def test_plan_deduplicates_across_scenes_and_preserves_difficulty_art(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); batch=self.fixture(root); plan=prepare(root/'scenes',batch)
            self.assertEqual([s['room'] for s in plan['scenes']],[9,87,10])
            entries={e['source']:e for s in plan['scenes'] for e in s['sources']}
            self.assertEqual(entries['objects/0010_same-hook_0000.png']['parent'],'objects/0009_hook_0000.png')
            self.assertEqual(entries['objects/0009_solid_0000.png']['operation'],'upscale-only')
            self.assertEqual(entries['objects_layers/0009_hook_0000.png']['operation'],'derive-layer')
            self.assertTrue(all(e['operation']=='preserve' for e in plan['scenes'][1]['sources']))
            self.assertEqual(plan['scenes'][0]['minimum_new_credits'],3)

    @patch('topaz_character_cutouts.time.sleep',return_value=None)
    def test_cached_opaque_art_and_derived_layers_make_no_paid_requests(self,sleep):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); batch=self.fixture(root); output=root/'scenes';plan=prepare(output,batch)
            record=next(r for r in json.loads((batch/'manifest.json').read_text())['records'] if 'solid' in r['source'])
            cached=batch/'raw'/(job_key(record,4)+'.png');cached.parent.mkdir();Image.new('RGB',(96,120),(150,110,50)).save(cached)
            base=prepare_scene(output,plan['scenes'][0],batch);api=FakeAPI()
            run(base,api,0,sources=[record['source']],require_pilots=False)
            self.assertEqual(api.paid,[])
            self.assertEqual(Image.open(base/'4x'/record['source']).getchannel('A').getextrema(),(255,255))
            source='objects/0009_hook_0000.png'; target=base/'4x'/source;target.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGBA',(72,96),(20,90,150,180)).save(target)
            jobs=json.loads((base/'jobs.json').read_text());jobs[source]=dict(state='validated',validation=dict(passed=True,sha256=digest(target)))
            (base/'jobs.json').write_text(json.dumps(jobs));materialize(output,plan)
            alias=output/'derived/4x/objects/0010_same-hook_0000.png'
            self.assertEqual(alias.read_bytes(),target.read_bytes())
            layer=Image.open(output/'derived/4x/objects_layers/0009_hook_0000.png')
            self.assertEqual(layer.size,(160,200));self.assertEqual(layer.getpixel((12,20)),(20,90,150,180))
            self.assertEqual(layer.getpixel((0,0))[3],0)
            self.assertFalse((output/'derived/4x/objects_layers/0087_easyhard_0000.png').exists())

    def test_review_install_preserves_background_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);batch=self.fixture(root);output=root/'scenes';plan=prepare(output,batch)
            base=prepare_scene(output,plan['scenes'][0],batch)
            source='objects/0009_hook_0000.png';target=base/'4x'/source;target.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGBA',(72,96),(20,90,150,180)).save(target)
            (base/'jobs.json').write_text(json.dumps({source:dict(state='validated',validation=dict(passed=True,sha256=digest(target)))}))
            materialize(output,plan);local=root/'local';(local/'game').mkdir(parents=True)
            import struct
            payload=struct.pack('<I',1)+b'hook'.ljust(46,b'\0')
            (local/'game/COMI.LA0').write_bytes(b'DOBJ'+struct.pack('>I',len(payload)+8)+payload)
            background=local/'hd/backgrounds/0087.png';background.parent.mkdir(parents=True);background.write_bytes(b'original-background')
            with self.assertRaises(ValueError):install_scene(output,9,local,completed_only=True)
            review_scene(output,[source]);install_scene(output,9,local,completed_only=True)
            self.assertEqual((local/'hd'/source).read_bytes(),target.read_bytes())
            self.assertTrue((local/'hd/objects_layers/0009_hook_0000.png').exists())
            self.assertEqual(background.read_bytes(),b'original-background')
            before=(local/'hd'/source).read_bytes();target.write_bytes(b'changed')
            with self.assertRaises(ValueError):install_scene(output,9,local,completed_only=True)
            self.assertEqual((local/'hd'/source).read_bytes(),before)
            with self.assertRaises(ValueError):install_scene(output,10,local,completed_only=True)

    @patch('topaz_scenes.active_character',return_value=False)
    def test_previous_crisp_frames_run_before_unrelated_later_scenes(self,active):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);batch=self.fixture(root);output=root/'scenes'
            manifest=json.loads((batch/'manifest.json').read_text())
            for n in (0,1):
                source=f'costumes/LFLF_0016_AKOS_0094_frame_{n}.png';clean=batch/'cleaned'/source;clean.parent.mkdir(parents=True,exist_ok=True)
                Image.new('RGBA',(20,30),(40+n,100,150,255)).save(clean)
                manifest['records'].append(dict(source=source,size=[20,30],cleaned_sha256=digest(clean),canonical=source))
            (batch/'manifest.json').write_text(json.dumps(manifest))
            priority=batch/'6x-crisp'/source;priority.parent.mkdir(parents=True);priority.write_bytes(b'archived')
            prepare(output,batch);calls=[]
            def worker(base,api,budget,**kwargs):
                calls.append((base.name,kwargs.get('sources')))
                (base/'progress.json').write_text(json.dumps(dict(state='awaiting_review')))
            with patch('topaz_scenes.run',side_effect=worker):process(output,FakeAPI(),20)
            self.assertEqual(calls[0][0],'room-0009')
            self.assertEqual(calls[1],('room-0016',[source]))
            self.assertEqual(len(calls),3) # Room 10's only asset is a free alias, so no paid task.
            self.assertEqual(calls[-1],('room-0016',()))

    @patch('topaz_scenes.active_character',return_value=False)
    @patch('topaz_character_cutouts.time.sleep',return_value=None)
    def test_supervisor_never_exceeds_available_budget(self,sleep,active):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);batch=self.fixture(root);output=root/'scenes';prepare(output,batch);api=FakeAPI()
            with patch.object(api,'balance',return_value=2):process(output,api,999)
            progress=json.loads((output/'progress.json').read_text())
            self.assertEqual(progress['credit_cap'],2)
            self.assertLessEqual(progress['submitted_credits'],2)
            self.assertEqual(progress['state'],'credit_cap')
            self.assertEqual(len(api.paid),2)


if __name__=='__main__':unittest.main()
