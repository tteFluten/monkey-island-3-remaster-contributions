import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw
from topaz_cannon_removebg import install, validate, remove_matte_residue


class CannonRemoveBGTests(unittest.TestCase):
    def test_install_copies_provider_bytes_and_preserves_previous_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); output = root / 'new'; batch = root / 'batch'; local = root / 'local'
            records = []; jobs = {}
            for n in range(14):
                source = f'costumes/LFLF_0009_AKOS_0026_frame_{n}.png'
                p = output / '4x' / source; p.parent.mkdir(parents=True, exist_ok=True)
                Image.new('RGBA', (12, 8), (71, 82, 93, 137)).save(p)
                records.append(dict(source=source, size=[12, 8], raw='/cached/example-key.png'))
                jobs[source] = dict(state='accepted', validation=dict(passed=True, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
                old = batch / '4x' / source; old.parent.mkdir(parents=True, exist_ok=True);old.write_bytes(b'old edge version')
            (output / 'manifest.json').write_text(json.dumps(dict(records=records, source_batch=str(batch))))
            (output / 'jobs.json').write_text(json.dumps(jobs))
            other = local / 'hd/topaz-cannon/costumes/other-character.png';other.parent.mkdir(parents=True);other.write_bytes(b'keep')
            install(output, local)
            for r in records:
                source=r['source'];provider=(output/'4x'/source).read_bytes()
                self.assertEqual((batch/'4x'/source).read_bytes(),provider)
                self.assertEqual((output/'previous/asset-tool'/source).read_bytes(),b'old edge version')
                for pack in ('topaz-cannon', 'topaz-crisp'):
                    self.assertEqual((local/'hd'/pack/source.replace('_frame_','_aframe_')).read_bytes(),provider)
            self.assertEqual(other.read_bytes(),b'keep')
            # A corrupt reviewed result cannot partially replace the pack.
            snapshot={p.name:p.read_bytes() for p in other.parent.iterdir()}
            (output/'4x'/records[-1]['source']).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):install(output,local)
            self.assertEqual(snapshot,{p.name:p.read_bytes() for p in other.parent.iterdir()})

    def test_recompose_preserves_reviewed_matting_and_refuses_tampering(self):
        from topaz_batch import job_key, recompose
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp); source='costumes/cannon.png'
            original=p/'cleaned'/source;original.parent.mkdir(parents=True)
            Image.new('RGBA',(2,3),'red').save(original)
            record=dict(source=source,canonical=source,size=[2,3],cleaned_sha256=hashlib.sha256(original.read_bytes()).hexdigest())
            (p/'manifest.json').write_text(json.dumps(dict(records=[record])))
            raw=p/'raw'/(job_key(record,4)+'.png');raw.parent.mkdir();Image.new('RGB',(8,12),'green').save(raw)
            matting=p/'reviewed.png';Image.new('RGBA',(8,12),(20,30,200,137)).save(matting)
            (p/'protected-cutouts.json').write_text(json.dumps({f'4:{source}':dict(file=str(matting),sha256=hashlib.sha256(matting.read_bytes()).hexdigest(),upscale_job_key=job_key(record,4))}))
            recompose(p,4)
            self.assertEqual((p/'4x'/source).read_bytes(),matting.read_bytes())
            before=(p/'4x'/source).read_bytes();matting.write_bytes(b'tampered')
            with self.assertRaises(ValueError):recompose(p,4)
            self.assertEqual((p/'4x'/source).read_bytes(),before)

    def test_residue_cleanup_changes_alpha_only_without_original_input(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            image=Image.new('RGBA',(8,8),(125,126,124,254))
            ImageDraw.Draw(image).rectangle((2,2,5,5),fill=(70,100,130,254))
            image.save(p/'provider.png')
            report=remove_matte_residue(p/'provider.png',p/'cutout.png')
            result=np.array(Image.open(p/'cutout.png'))
            self.assertTrue(np.array_equal(result[:,:,:3],np.array(image)[:,:,:3]))
            self.assertEqual(result[0,0,3],0)
            self.assertEqual(result[3,3,3],254)
            self.assertTrue(report['rgb_unchanged'])

    def test_validation_reads_original_only_and_rejects_missing_subject(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            original=Image.new('RGBA',(32,24));ImageDraw.Draw(original).rectangle((4,4,27,19),fill=(200,0,0,255));original.save(p/'original.png')
            raw=Image.new('RGB',(32,24),(127,127,127));ImageDraw.Draw(raw).rectangle((4,4,27,19),fill=(0,190,220));raw.save(p/'raw.png')
            provider=raw.convert('RGBA');provider.putalpha(original.getchannel('A'));provider.save(p/'provider.png')
            before=(p/'provider.png').read_bytes()
            self.assertTrue(validate(p/'provider.png',p/'raw.png',p/'original.png')['passed'])
            self.assertEqual((p/'provider.png').read_bytes(),before)
            Image.new('RGBA',(32,24)).save(p/'provider.png')
            self.assertFalse(validate(p/'provider.png',p/'raw.png',p/'original.png')['passed'])

if __name__ == '__main__':unittest.main()
