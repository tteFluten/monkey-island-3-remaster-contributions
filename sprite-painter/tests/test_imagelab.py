import json
from pathlib import Path
import time
import threading
import unittest
from unittest.mock import patch
from PIL import Image
import test_server as fixtures
from imagelab import ImageLab


painter, png, data_url = fixtures.painter, fixtures.png, fixtures.data_url

class ImageLabTests(unittest.TestCase):
    def setUp(self):
        fixtures.WorkspaceTests.setUp(self)
        reference=self.root/'test-original.png';reference.write_bytes(self.source)
        self.reference_patch=patch.object(self.work,'reference',return_value=reference)
        self.reference_patch.start();self.addCleanup(self.reference_patch.stop)
    tearDown=fixtures.WorkspaceTests.tearDown
    def lab(self):
        return ImageLab(self.work, painter.atomic, painter.sha, painter.png_size, painter.Conflict)

    def test_upscale_ignores_bad_draft_and_cleanup_keeps_original_authority(self):
        import base64, io
        lab=self.lab()
        ref=self.root/'test-original.png';ref.write_bytes(png(2,2,(30,60,90,255)))
        self.work.save(dict(id=self.id,revision=None,png=data_url(png(color=(255,0,255,255)))))
        with patch('replicate_upscale.token',return_value='test'),patch.object(lab,'start_next'):
            job=lab.create_upscale({'id':self.id})
            duplicate=lab.create_upscale({'id':self.id})
        self.assertEqual(job['id'],duplicate['id'])
        folder=lab.folder(job['id'])
        self.assertEqual((folder/'original.png').read_bytes(),ref.read_bytes())
        self.assertEqual(Image.open(folder/'input.png').getpixel((0,0)),(30,60,90))
        Image.new('RGBA',(8,8),(31,61,91,255)).save(folder/'candidate.png')
        job.update(status='ready',quality={'passed':True});lab.write(job)
        with patch.object(lab,'worker',side_effect=self.fake_worker),patch.object(lab,'start_next'):
            cleanup=lab.create(dict(id=self.id,prompt='Clean edges',style_id='',upscale_job_id=job['id']))
            request=json.loads((lab.folder(cleanup['id'])/'request.json').read_text())
            subject=Image.open(io.BytesIO(base64.b64decode(request['images'][0]['base64'])))
            authority=Image.open(io.BytesIO(base64.b64decode(request['images'][-1]['base64'])))
            self.assertEqual(subject.getpixel((512,512)),(31,61,91,255))
            self.assertEqual(authority.getpixel((512,512)),(30,60,90,255))
            self.assertEqual(cleanup['upscale_job_id'],job['id'])
            ref.write_bytes(png(2,2,(90,60,30,255)))
            with self.assertRaisesRegex(ValueError,'no corresponde'):
                lab.create(dict(id=self.id,prompt='Clean edges',upscale_job_id=job['id']))

    def test_different_upscalers_queue_independently_and_selection_preserves_edits(self):
        lab=self.lab();ref=self.root/'test-original.png';ref.write_bytes(png(2,2))
        with patch('replicate_upscale.token',return_value='test'),patch.object(lab,'start_next'):
            a=lab.create_upscale(dict(id=self.id,enhance_model='CGI'))
            b=lab.create_upscale(dict(id=self.id,enhance_model='High Fidelity V2'))
            anime=lab.create_upscale(dict(id=self.id,enhance_model='Real-ESRGAN Anime 6B'))
            self.assertEqual(anime['model'],'Real-ESRGAN Anime 6B ×4 · Replicate')
            self.assertNotEqual(anime['id'],a['id'])
            self.assertNotEqual(a['id'],b['id'])
            self.assertEqual(b['enhance_model'],'High Fidelity V2')
            with self.assertRaises(ValueError):lab.create_upscale(dict(id=self.id,enhance_model='invalid'))
        candidate=png(color=(40,60,80,100));(lab.folder(a['id'])/'candidate.png').write_bytes(candidate)
        a.update(status='ready',quality={'passed':True});lab.write(a)
        manual=png(color=(90,100,120,60))
        edit=self.work.save(dict(id=self.id,revision=None,png=data_url(manual)))
        with self.assertRaises(painter.Conflict):lab.select_variant(dict(job_id=a['id'],revision=None))
        lab.select_variant(dict(job_id=a['id'],revision=edit['revision']))
        self.assertEqual(self.work.draft(self.id).read_bytes(),candidate)
        saved=list((self.work.store/'history'/self.id).glob('*.png'))
        self.assertIn(manual,[p.read_bytes() for p in saved])
        a.update(status='ready',quality={'passed':False,'issues':['color alterado']});lab.write(a)
        current=self.work.revision(self.id)
        lab.select_variant(dict(job_id=a['id'],revision=current))
        self.assertEqual(self.work.draft(self.id).read_bytes(),candidate)
        opened=self.work.open(self.id)
        self.assertEqual(opened['selected_variant']['job_id'],a['id'])
        self.assertEqual(opened['current_sha256'],lab.read(a['id'])['candidate_sha256'])
        self.work.save(dict(id=self.id,revision=opened['revision'],png=data_url(manual)))
        self.assertIsNone(self.work.open(self.id)['selected_variant'])
        latest=sorted((self.work.store/'history'/self.id).glob('*.png'))[-1].name
        self.work.restore(dict(id=self.id,name=latest,revision=self.work.revision(self.id)))
        self.assertEqual(self.work.open(self.id)['selected_variant']['job_id'],a['id'])

    def test_alpha_only_variant_uses_ai_matte_without_regenerating(self):
        from PIL import ImageDraw
        lab=self.lab()
        with patch.object(lab,'worker',side_effect=self.fake_worker):
            source=lab.create(dict(id=self.id,prompt='Remaster'));self.complete(lab)
        calls=[]
        def worker(mode,folder=None):
            calls.append(mode);self.assertEqual(mode,'alpha')
            mask=Image.new('L',(16,16));ImageDraw.Draw(mask).rectangle((3,3,12,12),fill=255)
            mask.save(folder/'alpha-image.bin',format='PNG');return dict(ready=True)
        with patch.object(lab,'worker',side_effect=worker):
            job=lab.alpha_variant(source['id']);self.complete(lab)
        self.assertEqual(calls,['alpha']);self.assertEqual(lab.read(job['id'])['status'],'ready')
        with Image.open(lab.folder(job['id'])/'candidate.png') as candidate:
            self.assertEqual(candidate.getchannel('A').getextrema(),(0,255))
        self.assertFalse(self.work.draft(self.id).exists())
        self.assertEqual(lab.read(source['id'])['mask_method'],'simplified-contour-v1')

    def test_prepared_canvas_round_trip_preserves_rectangular_placement(self):
        import base64
        asset=self.work.import_png(dict(name='wide_frame_0.png',png=data_url(png(28,12,(30,60,90,255))),batch='test'))['id']
        ref=self.root/'wide-original.png';ref.write_bytes(png(7,3,(30,60,90,255)))
        lab=self.lab()
        def echo(mode,folder=None):
            if mode=='probe': return self.fake_worker(mode)
            request=json.loads((folder/'request.json').read_text())
            self.assertEqual(request['aspect_ratio'],'1:1')
            (folder/'provider-image.bin').write_bytes(base64.b64decode(request['images'][0]['base64']))
            return dict(ready=True)
        with patch.object(self.work,'reference',return_value=ref),patch.object(lab,'worker',side_effect=echo):
            job=lab.create(dict(id=asset,prompt='Preserve shape',style_id=''));self.complete(lab)
        self.assertEqual(lab.read(job['id'])['status'],'ready')
        with Image.open(lab.folder(job['id'])/'candidate.png') as result:
            self.assertEqual(result.size,(28,12))
            self.assertEqual(result.getextrema(),((30,30),(60,60),(90,90),(255,255)))

    def test_wrong_provider_aspect_is_not_silently_adapted(self):
        lab=self.lab()
        def worker(mode,folder=None):
            if mode=='probe': return self.fake_worker(mode)
            (folder/'provider-image.bin').write_bytes(png(32,16));return dict(ready=True)
        with patch.object(lab,'worker',side_effect=worker):
            job=lab.create(dict(id=self.id,prompt='Remaster'));self.complete(lab)
        self.assertEqual(lab.read(job['id'])['status'],'failed')
        self.assertFalse((lab.folder(job['id'])/'candidate.png').exists())

    def test_approved_draft_is_snapshotted_and_used_until_revoked(self):
        other=self.work.import_png(dict(name='guy_frame_1.png',png=data_url(png()),batch='test'))['id']
        self.work.frame(other)['group']=self.work.frame(self.id)['group']
        good=png(color=(10,20,30,180))
        self.work.save(dict(id=other,revision=None,png=data_url(good),offset=[0,0]))
        lab=self.lab();record=lab.approve(dict(id=other,revision=self.work.revision(other)))
        self.work.save(dict(id=other,revision=self.work.revision(other),png=data_url(png(color=(1,1,1,255))),offset=[0,0]))
        self.assertEqual((lab.root/'references'/record['file']).read_bytes(),good)
        lab=self.lab()
        with patch.object(lab,'worker',side_effect=self.fake_worker):
            job=lab.create(dict(id=self.id,prompt='Remaster'));self.complete(lab)
            self.assertEqual(job['style_asset_id'],other)
            self.assertEqual((lab.folder(job['id'])/'style.png').read_bytes(),good)
            lab.revoke(other)
            job=lab.create(dict(id=self.id,prompt='Remaster'));self.complete(lab)
            self.assertIsNone(job['style_asset_id'])
        with self.assertRaises(painter.Conflict): lab.approve(dict(id=other,revision='stale'))

    def test_approve_variant_does_not_apply_it(self):
        lab=self.lab()
        with patch.object(lab,'worker',side_effect=self.fake_worker):
            job=lab.create(dict(id=self.id,prompt='Remaster'));self.complete(lab)
        approval=lab.approve(dict(job_id=job['id']))
        self.assertEqual(approval['job_id'],job['id'])
        self.assertFalse(self.work.draft(self.id).exists())

    def test_only_original_is_sent_and_mask_comes_from_original(self):
        lab=self.lab();bad=png(color=(0,0,0,255))
        self.work.save(dict(id=self.id,revision=None,png=data_url(bad),offset=[0,0]))
        with patch.object(lab,'worker',side_effect=self.fake_worker):
            job=lab.create(dict(id=self.id,prompt='Faithful remaster'));self.complete(lab)
        request=json.loads((lab.folder(job['id'])/'request.json').read_text())
        self.assertEqual(len(request['images']),2)
        self.assertEqual(request['images'][0]['label'],'subject')
        self.assertEqual((lab.folder(job['id'])/'input.png').read_bytes()[:8],painter.PNG)
        with Image.open(lab.folder(job['id'])/'input.png') as img:
            self.assertEqual(img.getpixel((0,0)),(240,170,80,180))
        with Image.open(lab.folder(job['id'])/'candidate.png') as img:
            self.assertEqual(img.getchannel('A').getextrema(),(180,180))
        with patch.object(self.work,'reference',return_value=None):
            with self.assertRaisesRegex(ValueError,'No hay original'): lab.create(dict(id=self.id,prompt='Repair'))

    def test_style_reference_requires_accepted_matching_master(self):
        other=self.work.import_png(dict(name='guy_frame_1.png',png=data_url(png(color=(10,20,30,180))),batch='test'))['id']
        frame=self.work.frame(other);frame['group']=self.work.frame(self.id)['group']
        frame['review']=dict(state='accepted',current=True,sha256=painter.sha(self.work.original(other).read_bytes()))
        lab=self.lab()
        with patch.object(lab,'worker',side_effect=self.fake_worker):
            job=lab.create(dict(id=self.id,prompt='Remaster'));self.complete(lab)
            self.assertEqual(job['style_asset_id'],other)
            request=json.loads((lab.folder(job['id'])/'request.json').read_text())
            self.assertEqual([i['label'] for i in request['images']],['subject','style ref','photo ref'])
            frame['review']['sha256']='stale'
            job=lab.create(dict(id=self.id,prompt='Remaster'));self.complete(lab)
            self.assertIsNone(job['style_asset_id'])

    def test_queue_fifo_cancellation_and_failure_continues(self):
        lab=self.lab();started=threading.Event();release=threading.Event();calls=[]
        def worker(mode,folder=None):
            if mode=='probe': return self.fake_worker(mode)
            calls.append(folder.name)
            if len(calls)==1:
                started.set();release.wait(3)
                raise ValueError('Provider unavailable')
            return self.fake_worker(mode,folder)
        with patch.object(lab,'worker',side_effect=worker):
            first=lab.create(dict(id=self.id,prompt='First'))
            self.assertTrue(started.wait(1))
            second=lab.create(dict(id=self.id,prompt='Second'))
            third=lab.create(dict(id=self.id,prompt='Third'))
            self.assertEqual(lab.read(second['id'])['status'],'queued')
            self.assertEqual(len(lab.list()),3)
            lab.cancel(third['id'])
            with self.assertRaises(ValueError): lab.cancel(first['id'])
            release.set();self.complete(lab)
        self.assertEqual(calls,[first['id'],second['id']])
        self.assertEqual(lab.read(first['id'])['status'],'failed')
        self.assertEqual(lab.read(second['id'])['status'],'ready')
        self.assertEqual(lab.read(third['id'])['status'],'cancelled')

    def test_restart_resumes_queued_without_repeating_running(self):
        lab=self.lab()
        with patch.object(lab,'worker',side_effect=self.fake_worker),patch.object(lab,'start_next'):
            first=lab.create(dict(id=self.id,prompt='Already sent'))
            second=lab.create(dict(id=self.id,prompt='Waiting'))
        first['status']='running';lab.write(first)
        recovered=self.lab();calls=[]
        def worker(mode,folder=None):
            if mode=='generate': calls.append(folder.name)
            return self.fake_worker(mode,folder)
        with patch.object(recovered,'worker',side_effect=worker):
            recovered.resume();self.complete(recovered)
        self.assertEqual(calls,[second['id']])
        self.assertEqual(recovered.read(first['id'])['status'],'interrupted')
        self.assertEqual(recovered.read(second['id'])['status'],'ready')

    def fake_worker(self, mode, folder=None):
        if mode=='probe': return dict(ready=True,models=['test-model'],defaultModel='test-model')
        (folder/'provider-image.bin').write_bytes(png(16,16,(240,170,80,255)))
        return dict(ready=True)

    def complete(self, lab):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            with lab.lock:
                if not lab.active: return
            time.sleep(.01)
        self.fail('La cola no terminó a tiempo')

    def test_generation_is_separate_until_explicit_apply_and_preserves_alpha(self):
        lab=self.lab()
        with patch.object(lab,'worker',side_effect=self.fake_worker):
            job=lab.create(dict(id=self.id,prompt='Repair outline',model='test-model'))
            self.complete(lab)
        self.assertEqual(lab.read(job['id'])['status'],'ready')
        self.assertFalse(self.work.draft(self.id).exists())
        with Image.open(lab.folder(job['id'])/'candidate.png') as image:
            self.assertEqual(image.size,(8,8))
            self.assertEqual(image.getchannel('A').getextrema(),(180,180))
        lab.apply(job['id'])
        self.assertTrue(self.work.draft(self.id).exists())
        self.assertEqual(self.work.original(self.id).read_bytes(),self.source)
        self.assertTrue(lab.apply(job['id'])['already_applied'])

    def test_wrong_palette_cannot_be_applied_or_used_as_reference(self):
        lab=self.lab()
        def worker(mode,folder=None):
            if mode=='probe': return self.fake_worker(mode)
            (folder/'provider-image.bin').write_bytes(png(16,16,(40,150,220,255)))
            return dict(ready=True)
        with patch.object(lab,'worker',side_effect=worker):
            job=lab.create(dict(id=self.id,prompt='Preserve palette'));self.complete(lab)
        self.assertFalse(lab.read(job['id'])['quality']['passed'])
        with self.assertRaisesRegex(ValueError,'fidelidad'):lab.apply(job['id'])
        with self.assertRaisesRegex(ValueError,'no respeta'):lab.approve(dict(job_id=job['id']))
        self.assertFalse(self.work.draft(self.id).exists())

    def test_stale_candidate_cannot_overwrite_manual_work(self):
        lab=self.lab()
        with patch.object(lab,'worker',side_effect=self.fake_worker):
            job=lab.create(dict(id=self.id,prompt='Repair outline',model='test-model'))
            self.complete(lab)
        manual=png(color=(1,2,3,180))
        self.work.save(dict(id=self.id,revision=None,png=data_url(manual),offset=[0,0]))
        with self.assertRaises(painter.Conflict): lab.apply(job['id'])
        self.assertEqual(self.work.draft(self.id).read_bytes(),manual)

    def test_worker_failure_and_invalid_job_id(self):
        lab=self.lab()
        def worker(mode, folder=None):
            if mode=='probe': return self.fake_worker(mode)
            raise ValueError('Provider unavailable')
        with patch.object(lab,'worker',side_effect=worker):
            job=lab.create(dict(id=self.id,prompt='Repair',model='test-model'))
            self.complete(lab)
        self.assertEqual(lab.read(job['id'])['status'],'failed')
        self.assertFalse(self.work.draft(self.id).exists())
        with self.assertRaises(ValueError): lab.folder('../../outside')
