import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from live_updates import ChangeFeed
from test_server import painter,png,data_url


class FeedTests(unittest.TestCase):
    def test_replay_and_restart_resync(self):
        feed=ChangeFeed(capacity=2);cursor=feed.read()['cursor']
        feed.publish('a');feed.publish('b','approval')
        for _ in range(2):
            update=feed.read(cursor,0)
            self.assertEqual(update['ids'],['a','b'])
        feed.publish('c')
        self.assertTrue(feed.read(cursor,0)['reset'])
        self.assertTrue(ChangeFeed().read(update['cursor'],0)['reset'])

    def test_wait_is_woken_by_write_without_poll_delay(self):
        feed=ChangeFeed();cursor=feed.read()['cursor'];result=[]
        worker=threading.Thread(target=lambda:result.append(feed.read(cursor,5)))
        worker.start();feed.publish('sprite','job');worker.join(1)
        self.assertFalse(worker.is_alive());self.assertEqual(result[0]['ids'],['sprite'])


class LiveServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.server=painter.make_server(Path(self.temp.name),0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.id=self.server.workshop.import_png(dict(name='sprite.png',png=data_url(png()),batch='test'))['id']
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def api(self,path,body=None):
        request=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=3) as response:return json.load(response)
    def test_state_and_cached_thumbnail_follow_selected_version(self):
        before=self.api('/api/live-state?ids='+self.id);frame=before['frames'][0]
        with urllib.request.urlopen(self.base+f'/api/thumbnail?id={self.id}&v={frame["thumbnail_version"]}') as response:
            self.assertIn('immutable',response.headers['Cache-Control']);previous=response.read()
        job=self.api('/api/variants/import',dict(id=self.id,png=data_url(png(color=(10,20,230,255))),name='blue.png'))
        self.assertEqual(self.api('/api/live-state?ids='+self.id)['frames'][0]['revision'],None)
        result=self.api('/api/variants/select',dict(job_id=job['id'],revision=None))
        self.api('/api/imagelab/approve',dict(id=self.id,revision=result['revision']))
        current=self.api('/api/live-state?ids='+self.id)
        self.assertEqual(current['frames'][0]['revision'],result['revision'])
        self.assertNotEqual(current['frames'][0]['thumbnail_version'],frame['thumbnail_version'])
        self.assertEqual(current['jobs'][0]['status'],'applied')
        self.assertIsNotNone(current['approvals'][self.id])
        with urllib.request.urlopen(self.base+f'/api/thumbnail?id={self.id}&v={frame["thumbnail_version"]}') as response:
            self.assertEqual(response.headers['Cache-Control'],'no-store');self.assertNotEqual(response.read(),previous)
        self.api('/api/imagelab/revoke',dict(id=self.id))
        self.assertIsNone(self.api('/api/live-state?ids='+self.id)['approvals'][self.id])
    def test_event_stream_reports_job_completion_and_save_to_another_client(self):
        with urllib.request.urlopen(self.base+'/api/events',timeout=3) as response:
            def event():
                while True:
                    line=response.readline().decode()
                    if line.startswith('data: '):return json.loads(line[6:])
            self.assertTrue(event()['reset'])
            job=self.api('/api/variants/import',dict(id=self.id,png=data_url(png()),name='copy.png'))
            update=event();self.assertEqual(update['ids'],[self.id]);self.assertIn('job',update['kinds'])
            self.api('/api/variants/select',dict(job_id=job['id'],revision=None))
            self.assertEqual(event()['ids'],[self.id])
    def test_partial_snapshot_does_not_include_other_assets(self):
        other=self.server.workshop.import_png(dict(name='other.png',png=data_url(png()),batch='test'))['id']
        self.api('/api/variants/import',dict(id=other,png=data_url(png()),name='other.png'))
        result=self.api('/api/live-state?ids='+self.id)
        self.assertEqual(result['ids'],[self.id]);self.assertEqual(result['jobs'],[])

    def test_catalog_cursor_avoids_reloading_unchanged_frames_without_missing_a_save(self):
        catalog=self.api('/api/catalog');cursor=catalog['cursor']
        unchanged=self.api('/api/live-state?since='+cursor)
        self.assertEqual(unchanged['frames'],[]);self.assertTrue(unchanged['full'])
        self.assertIn(self.id,unchanged['ids'])
        self.api('/api/save',dict(id=self.id,revision=None,png=data_url(png(color=(17,12,88,255)))))
        changed=self.api('/api/live-state?since='+cursor)
        self.assertEqual([frame['id'] for frame in changed['frames']],[self.id])
        self.assertTrue(changed['frames'][0]['revision'])
        restarted=self.api('/api/live-state?since=previous-server:22')
        self.assertEqual(len(restarted['frames']),1)
