import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import replicate_upscale as upscale

class UpscaleTests(unittest.TestCase):
    def test_anime_routes_to_pinned_esrgan_anime_variant(self):
        endpoint,payload=upscale.prediction_request({'enhance_model':upscale.ANIME_MODEL},'data:image/png;base64,test')
        self.assertEqual(endpoint,'/predictions')
        self.assertEqual(payload['version'],upscale.ANIME_VERSION)
        self.assertEqual(payload['input'],dict(img='data:image/png;base64,test',version='Anime - anime6B',scale=4,face_enhance=False,tile=0))
        self.assertNotIn('prompt',payload['input'])

    def test_transparent_rgb_extension_does_not_add_a_matte(self):
        original=Image.new('RGBA',(3,3),(255,0,255,0));original.putpixel((1,1),(20,30,40,255))
        result=upscale.prepare_input(original)
        self.assertEqual(set(result.getdata()),{(20,30,40)})
        self.assertEqual(original.getpixel((0,0)),(255,0,255,0))

    def test_provider_request_and_alpha_are_not_generative(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            original=Image.new('RGBA',(3,3),(20,30,40,0));original.putpixel((1,1),(20,30,40,255));original.save(folder/'original.png')
            upscale.prepare_input(original).save(folder/'input.png')
            output=io.BytesIO();Image.new('RGB',(12,12),(20,30,40)).save(output,format='PNG')
            root=folder
            class Queue:
                work=type('Work',(),{'root':root})()
                def folder(self,_): return folder
                def write(self,job): (folder/'job.json').write_text(json.dumps(job))
            job={'id':'test','width':12,'height':12}
            with patch.object(upscale,'request',return_value={'id':'prediction','status':'succeeded','output':'https://example.com/result.png'}) as send, patch.object(upscale.urllib.request,'urlopen',return_value=io.BytesIO(output.getvalue())):
                upscale.run(Queue(),job)
            inputs=send.call_args.args[2]['input']
            self.assertEqual(inputs['upscale_factor'],'4x');self.assertEqual(inputs['enhance_model'],'CGI');self.assertNotIn('prompt',inputs)
            result=Image.open(folder/'candidate.png')
            expected=original.getchannel('A').resize((12,12),Image.Resampling.BICUBIC)
            self.assertEqual(result.getchannel('A').tobytes(),expected.tobytes())
            self.assertTrue(any(0<a<255 for a in expected.getdata()))
            self.assertEqual(job['prediction_id'],'prediction')
