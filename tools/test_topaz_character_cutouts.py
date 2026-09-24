import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from topaz_character_cutouts import digest, run, review, install, audit, character_validation


class FakeAPI:
    def __init__(self): self.paid = []; self.images = {}; self.ambiguous = False
    def balance(self): return 100
    def estimate(self, size): return dict(credits=1)
    def submit(self, image, size): return self.call('/image/v1/enhance-gen/async', {}, image)
    def call(self, route, fields=None, image=None):
        if route == '/image/v1/estimate': return dict(credits=1)
        if '/status/' in route: return dict(status='Completed')
        if route.endswith('/async'):
            self.paid.append(route)
            if self.ambiguous: raise RuntimeError('Connection lost after submission')
            pid = str(len(self.paid))
            with Image.open(image) as im:
                if 'enhance-gen' in route: im = im.resize((im.width*4, im.height*4))
                self.images[pid] = im.convert('RGBA').copy()
            return dict(process_id=pid)
        raise AssertionError(route)
    def download(self, pid, destination): self.images[pid].save(destination)


class CharacterCutoutTests(unittest.TestCase):
    def test_audit_catches_truncation_and_recovers_only_enhanced_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=root/'output';batch=root/'batch';source='costumes/LFLF_0001_AKOS_0002_frame_599.png'
            original=Image.new('RGBA',(32,48));ImageDraw.Draw(original).rectangle((10,3,23,44),fill=(255,0,0,255))
            raw=Image.new('RGB',original.size,(127,127,127));ImageDraw.Draw(raw).rectangle((10,3,23,44),fill=(10,80,130))
            provider=raw.convert('RGBA');alpha=Image.new('L',raw.size);ImageDraw.Draw(alpha).rectangle((10,3,23,31),fill=255);provider.putalpha(alpha)
            for folder,image in [(batch/'cleaned',original),(output/'raw',raw),(output/'provider',provider),(output/'4x',provider)]:
                target=folder/source;target.parent.mkdir(parents=True,exist_ok=True);image.save(target)
            report=character_validation(output/'provider'/source,output/'raw'/source,batch/'cleaned'/source)
            self.assertFalse(report['passed'])
            (output/'manifest.json').write_text(json.dumps(dict(source_batch=str(batch),records=[dict(source=source,raw=str(output/'raw'/source))])))
            (output/'jobs.json').write_text(json.dumps({source:dict(state='rejected',validation=report)}))
            before=(output/'provider'/source).read_bytes();audit(output,repair=True)
            revised=json.loads((output/'audits.json').read_text())[source]
            self.assertTrue(revised['validation']['passed']);self.assertTrue(revised['repaired'])
            image=Image.open(output/'4x'/source)
            self.assertEqual(image.getpixel((15,40)),(10,80,130,255))
            self.assertEqual(image.getpixel((0,0))[3],0)
            self.assertEqual((output/'provider'/source).read_bytes(),before)

    def fixture(self, root, cached=(), count=2):
        output = root/'new'; batch=root/'batch'; records=[]; originals=[]
        for n in range(count):
            source=f'costumes/LFLF_0009_AKOS_0025_frame_{n}.png'
            clean=batch/'cleaned'/source; clean.parent.mkdir(parents=True,exist_ok=True)
            Image.new('RGBA',(4,4),(50,100,130,255)).save(clean)
            raw=output/'raw'/source
            if n in cached:
                raw.parent.mkdir(parents=True,exist_ok=True); Image.new('RGB',(16,16),(50,100,130)).save(raw)
            records.append(dict(source=source,original_size=[4,4],size=[16,16],raw=str(raw),
                cleaned_sha256=digest(clean),cached={'scale':6} if n in cached else None,
                raw_sha256=digest(raw) if raw.exists() else None))
            originals.append(dict(source=source,cleaned_sha256=digest(clean)))
        output.mkdir(parents=True,exist_ok=True)
        (output/'manifest.json').write_text(json.dumps(dict(records=records,source_batch=str(batch))))
        (batch/'manifest.json').write_text(json.dumps(dict(records=originals)))
        return output,batch,records

    @staticmethod
    def accepted(path,*args): return dict(passed=True,sha256=digest(path),silhouette_iou=.99)

    @patch('topaz_character_cutouts.time.sleep',return_value=None)
    def test_sixteen_slots_share_budget_and_resume_without_duplicate_payments(self, sleep):
        with tempfile.TemporaryDirectory() as temp:
            output, batch, records = self.fixture(Path(temp), count=18)
            api = FakeAPI(); original = api.call; peaks = []
            def observed(route, fields=None, image=None):
                if '/status/' in route:
                    jobs = json.loads((output/'jobs.json').read_text())
                    peaks.append(sum(j.get('state') == 'submitted' for j in jobs.values()))
                return original(route, fields, image)
            with patch.object(api, 'call', side_effect=observed), patch('topaz_character_cutouts.validate', self.accepted):
                run(output, api, 33, concurrency=16, require_pilots=False)
                self.assertEqual(max(peaks), 16)
                self.assertEqual(len(api.paid), 32)  # Last credit cannot fund a pair.
                jobs = json.loads((output/'jobs.json').read_text())
                self.assertEqual(sum(j.get('state') == 'validated' for j in jobs.values()), 16)
                run(output, api, 4, concurrency=16, require_pilots=False)
                self.assertEqual(len(api.paid), 36)
                run(output, api, 0, concurrency=16, require_pilots=False)
                self.assertEqual(len(api.paid), 36)

    def test_invalid_concurrency_never_touches_queue(self):
        for concurrency in (0, 17, 1.5, True):
            with self.subTest(concurrency=concurrency), self.assertRaises(ValueError):
                run(Path('unused'), FakeAPI(), 10, concurrency=concurrency)

    @patch('topaz_character_cutouts.time.sleep',return_value=None)
    def test_credit_cap_reserves_upscale_and_matting_together(self, sleep):
        with tempfile.TemporaryDirectory() as temp:
            output,batch,records=self.fixture(Path(temp)); api=FakeAPI()
            with patch('topaz_character_cutouts.validate',self.accepted):
                run(output,api,3,concurrency=4,require_pilots=False)
            jobs=json.loads((output/'jobs.json').read_text())
            self.assertEqual(len(api.paid),2)
            self.assertEqual(jobs[records[0]['source']]['state'],'validated')
            self.assertNotIn('process_id',jobs.get(records[1]['source'],{}))
            self.assertEqual(json.loads((output/'progress.json').read_text())['state'],'credit_cap')
            # Resume retains both paid results; only the second pair is billed.
            with patch('topaz_character_cutouts.validate',self.accepted): run(output,api,2,require_pilots=False)
            self.assertEqual(len(api.paid),4)

    @patch('topaz_character_cutouts.time.sleep',return_value=None)
    def test_cached_upscale_is_not_paid_again_and_review_is_required(self,sleep):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output,batch,records=self.fixture(root,cached=(0,1));api=FakeAPI()
            with patch('topaz_character_cutouts.validate',self.accepted): run(output,api,2,require_pilots=False)
            self.assertEqual(api.paid,['/image/v1/matting/async']*2)
            with self.assertRaises(ValueError): install(output,root/'local')
            source=records[0]['source']; review(output,[source]); install(output,root/'local')
            installed=root/'local/hd/topaz-cannon'/source.replace('_frame_','_aframe_')
            self.assertEqual(installed.read_bytes(),(output/'provider'/source).read_bytes())
            (output/'4x'/source).write_bytes(b'changed')
            with self.assertRaises(ValueError):install(output,root/'local')
            self.assertEqual(installed.read_bytes(),(output/'provider'/source).read_bytes())

    @patch('topaz_character_cutouts.time.sleep',return_value=None)
    def test_slow_provider_is_deferred_and_resumed_without_repayment(self,sleep):
        with tempfile.TemporaryDirectory() as temp:
            output,batch,records=self.fixture(Path(temp),cached=(0,));api=FakeAPI();original=api.call
            def slow(route,fields=None,image=None):
                if '/status/' in route:return dict(status='Processing')
                return original(route,fields,image)
            with patch.object(api,'call',side_effect=slow):
                run(output,api,1,sources=[records[0]['source']],require_pilots=False,poll_timeout=0)
            self.assertEqual(len(api.paid),1)
            self.assertEqual(json.loads((output/'progress.json').read_text())['state'],'awaiting_provider')
            saved=json.loads((output/'jobs.json').read_text())[records[0]['source']]['process_id']
            run(output,api,0,sources=[records[0]['source']],require_pilots=False)
            self.assertEqual(len(api.paid),1)
            self.assertEqual(json.loads((output/'jobs.json').read_text())[records[0]['source']]['process_id'],saved)

    def test_ambiguous_paid_request_is_never_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            output,batch,records=self.fixture(Path(temp));api=FakeAPI();api.ambiguous=True
            with self.assertRaises(RuntimeError): run(output,api,2,sources=[records[0]['source']],require_pilots=False)
            run(output,api,2,sources=[records[0]['source']],require_pilots=False)
            self.assertEqual(len(api.paid),1)
            self.assertEqual(json.loads((output/'jobs.json').read_text())[records[0]['source']]['state'],'unknown')


if __name__=='__main__': unittest.main()
