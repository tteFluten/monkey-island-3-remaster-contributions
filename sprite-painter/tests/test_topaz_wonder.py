import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
import topaz_wonder as topaz

class WonderTests(unittest.TestCase):
    def test_output_download_retries_without_submitting(self):
        import io,urllib.error
        with patch.object(topaz.urllib.request,'urlopen',side_effect=[urllib.error.URLError('offline'),io.BytesIO(b'png')]) as get,patch.object(topaz.time,'sleep'),patch.object(topaz,'request') as paid:
            self.assertEqual(topaz.read_output('https://example.test/result','Bria'),b'png')
            self.assertEqual(get.call_count,2);paid.assert_not_called()

    def test_cached_bria_never_submits_again(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);Image.new('RGBA',(8,8),(20,20,20,255)).save(folder/'bria.png')
            queue=SimpleNamespace(folder=lambda _:folder)
            with patch('replicate_upscale.request') as paid:
                result=topaz.bria_cutout(queue,{'id':'test'},folder/'wonder.png',Image.new('RGB',(8,8)))
                self.assertEqual(result.size,(8,8));paid.assert_not_called()

    def test_alpha_only_preserves_paint_and_never_calls_topaz(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);queue=SimpleNamespace(folder=lambda _:folder)
            source=Image.new('RGBA',(8,8),(20,40,90,255));source.save(folder/'alpha-source.png')
            topaz.prepare_input(source).save(folder/'input.png')
            with patch.object(topaz,'bria_cutout',return_value=Image.new('RGBA',(8,8),(200,0,0,128))),patch.object(topaz,'request') as paid:
                topaz.refine_alpha(queue,{'id':'test'})
                paid.assert_not_called()
            with Image.open(folder/'candidate.png') as result:
                self.assertEqual(result.getpixel((0,0)),(20,40,90,128))
                self.assertEqual(result.size,source.size)

    def test_larger_bria_mask_is_resampled_without_resizing_wonder(self):
        import io
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); queue=SimpleNamespace(folder=lambda _:folder)
            output=io.BytesIO(); Image.new('RGBA',(300,1900),(9,8,7,128)).save(output,format='PNG')
            job={'id':'test'}
            result=topaz.compose_bria(queue,job,output.getvalue(),Image.new('RGB',(60,380),(127,127,127)))
            self.assertEqual(result.size,(60,380))
            self.assertEqual(result.getchannel('A').getextrema(),(128,128))
            self.assertTrue(job['alpha_resized'])
            wrong=io.BytesIO(); Image.new('RGBA',(300,300)).save(wrong,format='PNG')
            with self.assertRaises(ValueError):topaz.compose_bria(queue,job,wrong.getvalue(),Image.new('RGB',(60,380)))

    def test_bria_uses_wonder_and_unmixes_gray_edge(self):
        import io
        import replicate_upscale
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            raw=folder/'wonder.png'; enhanced=Image.new('RGB',(2,1),(80,90,100)); enhanced.putpixel((1,0),(127,127,127)); enhanced.save(raw)
            output=io.BytesIO(); mask=Image.new('RGBA',(2,1),(1,2,3,255)); mask.putpixel((1,0),(1,2,3,0));mask.save(output,format='PNG')
            queue=SimpleNamespace(work=SimpleNamespace(root=folder),folder=lambda _:folder,write=lambda _:None)
            job={'id':'test'}
            with patch.object(replicate_upscale,'request',return_value={'id':'bria-id','status':'succeeded','output':'https://example.com/image.png'}) as send, patch.object(topaz.urllib.request,'urlopen',return_value=io.BytesIO(output.getvalue())):
                result=topaz.bria_cutout(queue,job,raw,enhanced)
            self.assertEqual(result.getpixel((0,0)),(80,90,100,255))
            self.assertEqual(result.getpixel((1,0)),(0,0,0,0))
            self.assertEqual(send.call_args.args[1],'/models/bria/remove-background/predictions')
            self.assertEqual(job['bria_prediction_id'],'bria-id')

    def test_two_stages_keep_provider_alpha_and_original_input(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            original=Image.new('RGBA',(3,3),(90,20,10,0))
            original.putpixel((1,1),(90,20,10,255)); original.save(folder/'original.png')
            topaz.prepare_input(original).save(folder/'input.png')
            self.assertEqual(Image.open(folder/'input.png').getpixel((0,0)),(127,127,127))
            queue=SimpleNamespace(work=SimpleNamespace(root=folder),folder=lambda _:folder,write=lambda _:None)
            job=dict(id='test',width=12,height=12)
            routes=[]
            def request(root,route,fields=None,image=None):
                routes.append(route)
                if 'estimate' in route: return {'credits':1}
                if 'balance' in route: return {'available_credits':800}
                if '/status/' in route: return {'status':'Completed'}
                return {'process_id':'matting' if 'matting' in route else 'wonder'}
            def download(root,pid,dest):
                Image.new('RGBA' if pid=='matting' else 'RGB',(12,12),(90,20,10,123) if pid=='matting' else (90,20,10)).save(dest)
            with patch.object(topaz,'request',side_effect=request),patch.object(topaz,'download',side_effect=download):
                topaz.run(queue,job)
            with Image.open(folder/'candidate.png') as result:
                self.assertEqual(result.getchannel('A').getextrema(),(123,123))
            self.assertEqual(job['estimated_credits'],2)
            self.assertIn('/image/v1/matting/async',routes)
            self.assertEqual(job['topaz_stages']['wonder']['settings']['model'],'Wonder 3.5')

    def test_unknown_submission_never_retries(self):
        queue=SimpleNamespace(work=SimpleNamespace(root=Path('.')),write=lambda _:None)
        job={'topaz_stages':{'wonder':{'state':'submitting'}}}
        with patch.object(topaz,'request') as request:
            with self.assertRaises(ValueError): topaz.stage(queue,job,'wonder','route',{},Path('input'),Path('output'))
            request.assert_not_called()

    def test_cost_limit_prevents_paid_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); Image.new('RGBA',(3,3)).save(folder/'original.png')
            queue=SimpleNamespace(work=SimpleNamespace(root=folder),folder=lambda _:folder,write=lambda _:None)
            with patch.object(topaz,'request',return_value={'credits':3}),patch.object(topaz,'stage') as stage:
                with self.assertRaises(ValueError): topaz.run(queue,dict(id='test',width=12,height=12))
                stage.assert_not_called()
