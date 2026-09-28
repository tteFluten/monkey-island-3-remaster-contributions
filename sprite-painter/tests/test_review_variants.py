import io
import json
import time
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
import test_server as fixtures
from imagelab import ImageLab

painter,png,data_url=fixtures.painter,fixtures.png,fixtures.data_url

class ReviewVariantTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    tearDown=fixtures.WorkspaceTests.tearDown

    def lab(self):return ImageLab(self.work,painter.atomic,painter.sha,painter.png_size,painter.Conflict)

    def complete(self,lab):
        deadline=time.monotonic()+4
        while lab.active and time.monotonic()<deadline:time.sleep(.01)
        self.assertIsNone(lab.active)

    def test_import_is_an_exact_separate_version_available_as_generation_base(self):
        lab=self.lab();data=png(color=(17,31,45,96))
        job=lab.import_variant(dict(id=self.id,name='../my sprite.png',png=data_url(data)))
        self.assertEqual(job['status'],'ready')
        self.assertEqual(job['model'],'Importado · my sprite.png')
        self.assertEqual((lab.folder(job['id'])/'candidate.png').read_bytes(),data)
        self.assertFalse(self.work.draft(self.id).exists())
        self.assertEqual(self.work.original(self.id).read_bytes(),self.source)
        self.assertEqual(lab.variant_source(dict(id=self.id,job_id=job['id'])),data)
        self.assertIn('image',job)
        ref=self.root/'reference.png';ref.write_bytes(self.source)
        with patch.object(self.work,'reference',return_value=ref),patch.object(lab,'status',return_value=dict(ready=True,models=['mock'],defaultModel='mock')),patch.object(lab,'start_next'):
            generated=lab.create(dict(id=self.id,prompt='Use uploaded image',upscale_job_id=job['id'],alpha_mode='none'))
        with Image.open(lab.folder(generated['id'])/'input.png') as image:
            self.assertEqual(image.getpixel((0,0)),(17,31,45,96))

    def test_import_rejects_wrong_size_and_invalid_png_without_creating_jobs(self):
        lab=self.lab()
        for data in (png(9,8),b'not an image'):
            with self.assertRaises(ValueError):lab.import_variant(dict(id=self.id,name='test.png',png=data_url(data)))
        self.assertEqual(lab.list(),[])
        self.assertFalse(self.work.draft(self.id).exists())

    def test_bria_alpha_from_selected_import_keeps_rgb_size_and_does_not_call_topaz(self):
        lab=self.lab();data=png(color=(77,89,103,255))
        imported=lab.import_variant(dict(id=self.id,png=data_url(data)))
        with patch('replicate_upscale.token',return_value='mock'),patch('topaz_wonder.bria_cutout',return_value=Image.new('RGBA',(8,8),(255,0,0,128))),patch('topaz_wonder.request') as topaz:
            job=lab.extract_variant_alpha(dict(id=self.id,job_id=imported['id'],engine='bria'));self.complete(lab)
            topaz.assert_not_called()
        self.assertEqual(lab.read(job['id'])['status'],'ready')
        with Image.open(lab.folder(job['id'])/'candidate.png') as image:
            self.assertEqual(image.size,(8,8));self.assertEqual(image.getpixel((3,3)),(77,89,103,128))
        self.assertFalse(self.work.draft(self.id).exists())

    def test_imagelab_alpha_current_uses_only_mask_request_and_preserves_every_rgb(self):
        lab=self.lab();calls=[]
        paint=Image.new('RGBA',(8,8))
        for y in range(8):
            for x in range(8):paint.putpixel((x,y),(x*21,y*31,91,255))
        buffer=io.BytesIO();paint.save(buffer,format='PNG')
        saved=self.work.save(dict(id=self.id,revision=None,png=data_url(buffer.getvalue())))
        def worker(mode,folder=None):
            if mode=='probe':return dict(ready=True,models=['mock'],defaultModel='mock')
            calls.append(mode);self.assertEqual(mode,'alpha')
            mask=Image.new('L',(1024,1024));ImageDraw.Draw(mask).rectangle((200,200,800,800),fill=255)
            mask.save(folder/'alpha-image.bin',format='PNG');return dict(ready=True)
        with patch.object(lab,'worker',side_effect=worker):
            job=lab.extract_variant_alpha(dict(id=self.id,revision=saved['revision'],engine='imagelab'));self.complete(lab)
        self.assertEqual(calls,['alpha']);self.assertEqual(lab.read(job['id'])['status'],'ready')
        with Image.open(lab.folder(job['id'])/'candidate.png') as result:
            self.assertEqual(result.convert('RGB').tobytes(),paint.convert('RGB').tobytes())
            self.assertEqual(result.getchannel('A').getextrema(),(0,255))
        self.assertEqual(self.work.draft(self.id).read_bytes(),buffer.getvalue())

    def test_alpha_rejects_stale_or_cross_asset_sources_before_provider(self):
        lab=self.lab();other=self.work.import_png(dict(name='other.png',png=data_url(png()),batch='other'))['id']
        imported=lab.import_variant(dict(id=other,png=data_url(png())))
        with patch.object(lab,'worker') as worker,patch('replicate_upscale.token') as token:
            with self.assertRaises(painter.Conflict):lab.extract_variant_alpha(dict(id=self.id,revision='stale',engine='bria'))
            with self.assertRaises(ValueError):lab.extract_variant_alpha(dict(id=self.id,job_id=imported['id'],engine='imagelab'))
            worker.assert_not_called();token.assert_not_called()

    def test_identical_queued_alpha_is_not_submitted_twice(self):
        lab=self.lab()
        with patch('replicate_upscale.token',return_value='mock'),patch.object(lab,'start_next'):
            a=lab.extract_variant_alpha(dict(id=self.id,revision=None,engine='bria'))
            b=lab.extract_variant_alpha(dict(id=self.id,revision=None,engine='bria'))
        self.assertEqual(a['id'],b['id']);self.assertEqual(len(lab.list()),1)
