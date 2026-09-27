import base64
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zlib

spec = importlib.util.spec_from_file_location('painter', Path(__file__).parents[1] / 'server.py')
painter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(painter)


def png(width=8, height=8, color=(240, 170, 80, 180)):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    rows = (b'\0' + bytes(color) * width) * height
    return painter.PNG + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


def data_url(data):
    return 'data:image/png;base64,' + base64.b64encode(data).decode()


class WorkspaceTests(unittest.TestCase):
    def test_reference_and_thumbnail_keep_aspect_ratio(self):
        path=self.root/'assets/masters/topaz-4x/costumes/LFLF_0009_AKOS_0025_frame_0.png'
        path.parent.mkdir(parents=True);path.write_bytes(png(80,160))
        id_=self.work.register(path,'Barco')
        reference=self.root/'assets/references/topaz-cleaned/costumes'/path.name
        reference.parent.mkdir(parents=True);reference.write_bytes(png(20,40))
        self.assertEqual(self.work.reference(id_),reference)
        original=self.root/'extracted/costumes'/path.name
        original.parent.mkdir(parents=True);original.write_bytes(png(20,40))
        self.work.reference.cache_clear()
        self.assertEqual(self.work.reference(id_),reference)
        reference.unlink();self.work.reference.cache_clear()
        self.assertEqual(self.work.reference(id_),original)
        data=painter.thumbnail(str(path),path.stat().st_mtime_ns,False)
        w,h=painter.png_size(data)
        self.assertAlmostEqual(w/h,.5,places=2)

    def test_review_attaches_only_by_exact_master_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'assets/metadata').mkdir(parents=True)
            path='assets/masters/topaz-4x/costumes/LFLF_0009_AKOS_0025_frame_0.png'
            (root/'assets/manifest.json').write_text(json.dumps({'files':[{'path':path,'sha256':'abc'}]}))
            reviews={'costumes/LFLF_0009_AKOS_0025_frame_0.png':{'sha256':'abc','state':'rejected','validation_passed':False}}
            review_path=root/'assets/metadata/artwork-review.json'
            review_path.write_text(json.dumps(reviews))
            work=painter.Workshop(root)
            frame=next(iter(work.frames.values()))
            self.assertTrue(frame['review']['current'])
            self.assertEqual(frame['review']['state'],'rejected')
            reviews[next(iter(reviews))]['sha256']='old'
            review_path.write_text(json.dumps(reviews));work.reload()
            self.assertFalse(next(iter(work.frames.values()))['review']['current'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work = painter.Workshop(self.root)
        self.source = png()
        self.id = self.work.import_png(dict(name='guy_frame_0.png', png=data_url(self.source), batch='test'))['id']

    def tearDown(self):
        self.temp.cleanup()

    def test_save_preserves_source_alpha_dimensions_and_history(self):
        edited = png(color=(20, 120, 240, 30))
        result = self.work.save(dict(id=self.id, png=data_url(edited), revision=None, offset=[3, -2]))
        self.assertEqual(self.work.original(self.id).read_bytes(), self.source)
        self.assertEqual(self.work.draft(self.id).read_bytes(), edited)
        self.assertEqual(self.work.open(self.id)['offset'], [3, -2])
        self.work.save(dict(id=self.id, png=data_url(self.source), revision=result['revision']))
        versions = sorted((self.work.store / 'history' / self.id).glob('*.png'))
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].read_bytes(), self.source)
        self.assertEqual(versions[1].read_bytes(), edited)
        restarted = painter.Workshop(self.root)
        self.assertEqual(restarted.draft(self.id).read_bytes(), self.source)

    def test_restore_preserves_replaced_version_offset_and_conflicts(self):
        edited=png(color=(20,120,240,30))
        first=self.work.save(dict(id=self.id,png=data_url(edited),revision=None,offset=[3,-2]))
        second=self.work.save(dict(id=self.id,png=data_url(self.source),revision=first['revision']))
        folder=self.work.store/'history'/self.id
        version=sorted(folder.glob('*.png'))[-1].name
        with self.assertRaises(painter.Conflict):
            self.work.restore(dict(id=self.id,name=version,revision=first['revision']))
        restored=self.work.restore(dict(id=self.id,name=version,revision=second['revision']))
        self.assertEqual(restored['offset'],[3,-2])
        self.assertEqual(self.work.draft(self.id).read_bytes(),edited)
        self.assertEqual(len(list(folder.glob('*.png'))),3)
        self.assertEqual(sorted(folder.glob('*.png'))[-1].read_bytes(),self.source)
        with self.assertRaises(ValueError):
            self.work.restore(dict(id=self.id,name='../bad.png',revision=restored['revision']))

    def test_stale_revision_does_not_overwrite(self):
        self.work.save(dict(id=self.id, png=data_url(self.source), revision=None))
        with self.assertRaises(painter.Conflict):
            self.work.save(dict(id=self.id, png=data_url(png(color=(0, 0, 0, 255))), revision=None))
        self.assertEqual(self.work.draft(self.id).read_bytes(), self.source)

    def test_changed_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            self.work.save(dict(id=self.id, png=data_url(png(9, 8)), revision=None))
        self.assertFalse(self.work.draft(self.id).exists())

    def test_alignment_only_save_advances_revision(self):
        first = self.work.save(dict(id=self.id, png=data_url(self.source), revision=None, offset=[0, 0]))
        second = self.work.save(dict(id=self.id, png=data_url(self.source), revision=first['revision'], offset=[1, 0]))
        self.assertNotEqual(first['revision'], second['revision'])
        with self.assertRaises(painter.Conflict):
            self.work.save(dict(id=self.id, png=data_url(self.source), revision=first['revision'], offset=[2, 0]))

    def test_lfs_pointer_cannot_be_edited_as_png(self):
        self.work.original(self.id).write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abcd\n')
        with self.assertRaisesRegex(ValueError, 'Git LFS'):
            self.work.open(self.id)

    def test_paths_and_crc(self):
        with self.assertRaises(ValueError):
            self.work.register(self.root.parent / 'outside.png', 'test')
        with self.assertRaises(ValueError):
            self.work.frame('../../credentials')
        bad = bytearray(self.source); bad[30] ^= 1
        with self.assertRaises(ValueError):
            painter.png_size(bytes(bad))
        with self.assertRaises(painter.Conflict):
            self.work.import_png(dict(name='guy_frame_0.png', png=data_url(png(color=(1, 2, 3, 4))), batch='test'))

    def test_http_catalog_save_and_origin_boundary(self):
        server = painter.make_server(self.root, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(OSError):
                painter.make_server(self.root, server.server_port)
            with urllib.request.urlopen(url + '/api/health') as response:
                self.assertEqual(json.load(response)['app'], 'monkey-sprite-painter')
            with urllib.request.urlopen(url + '/api/catalog') as response:
                self.assertEqual(len(json.load(response)['frames']), 1)
            body = json.dumps(dict(id=self.id, png=data_url(self.source), revision=None)).encode()
            req = urllib.request.Request(url + '/api/save', body, {'Content-Type':'application/json', 'Origin':url})
            with urllib.request.urlopen(req) as response:
                self.assertTrue(json.load(response)['revision'])
            req = urllib.request.Request(url + '/api/save', body, {'Content-Type':'application/json', 'Origin':'https://external.example'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__':
    unittest.main()
