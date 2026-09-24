import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from prepare_topaz import digest
from topaz_batch import database, job_key
from topaz_queue import run


class FakeAPI:
    def __init__(self):
        self.submissions = []
        self.available = 100
        self.processing = False
        self.fail_download = False
        self.fail_submit = False

    def balance(self):
        return self.available

    def estimate(self, size):
        return {'credits': 1}

    def submit(self, path, size):
        self.submissions.append(size)
        self.available -= 1
        if self.fail_submit:
            raise TimeoutError('unknown submission result')
        return {'process_id': str(len(self.submissions))}

    def call(self, route):
        return {'status': 'Processing' if self.processing else 'Completed'}

    def download(self, pid, destination):
        if self.fail_download:
            raise RuntimeError('storage unavailable')
        Image.new('RGB', (12, 18), 'red').save(destination)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.records = []
        for i, color in enumerate(['red', 'blue', 'green', 'yellow', 'black']):
            source = f'objects/{i}.png'
            path = self.root / 'cleaned' / source
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new('RGBA', (2, 3), color).save(path)
            self.records.append(dict(source=source, canonical=source, size=[2, 3], cleaned_sha256=digest(path)))
        (self.root / 'manifest.json').write_text(json.dumps(dict(records=self.records)))
        self.selection = [r['source'] for r in self.records]

    def tearDown(self):
        self.temp.cleanup()

    def test_concurrent_queue_obeys_total_cap_and_reuses_results(self):
        api = FakeAPI()
        result = run(self.root, api, self.selection, 3, poll_interval=0)
        self.assertEqual(result, dict(completed=3, credits=3, pending=2))
        self.assertEqual(len(api.submissions), 3)
        result = run(self.root, api, self.selection, 2, poll_interval=0)
        self.assertEqual(result, dict(completed=2, credits=2, pending=0))
        run(self.root, api, self.selection, 100, poll_interval=0)
        self.assertEqual(len(api.submissions), 5)

    def test_balance_limits_batch(self):
        api = FakeAPI()
        api.available = 1
        result = run(self.root, api, self.selection, 10, poll_interval=0)
        self.assertEqual(result['credits'], 1)

    def test_timeout_resumes_paid_jobs_with_zero_budget(self):
        api = FakeAPI()
        api.processing = True
        with self.assertRaises(TimeoutError):
            run(self.root, api, self.selection, 4, timeout=-1, poll_interval=0)
        api.processing = False
        result = run(self.root, api, self.selection, 0, poll_interval=0)
        self.assertEqual(result, dict(completed=4, credits=0, pending=1))
        self.assertEqual(len(api.submissions), 4)

    def test_unknown_submission_is_never_retried(self):
        api = FakeAPI()
        api.fail_submit = True
        with self.assertRaises(TimeoutError):
            run(self.root, api, self.selection, 5, poll_interval=0)
        api.fail_submit = False
        with self.assertRaisesRegex(RuntimeError, 'submitting'):
            run(self.root, api, self.selection, 5, poll_interval=0)
        self.assertEqual(len(api.submissions), 1)

    def test_download_failure_keeps_all_outstanding_ids(self):
        api = FakeAPI()
        api.fail_download = True
        with self.assertRaises(RuntimeError):
            run(self.root, api, self.selection, 4, poll_interval=0)
        api.fail_download = False
        run(self.root, api, self.selection, 0, poll_interval=0)
        self.assertEqual(len(api.submissions), 4)
        self.assertTrue(all((self.root / '6x' / s).exists() for s in self.selection[:4]))

    def test_changed_input_prevents_any_payment(self):
        (self.root / 'cleaned' / self.selection[0]).write_bytes(b'changed')
        api = FakeAPI()
        with self.assertRaises(ValueError):
            run(self.root, api, self.selection, 5, poll_interval=0)
        self.assertEqual(api.submissions, [])

    def test_scale_mismatch_prevents_payment(self):
        api = FakeAPI()
        api.scale = 4
        with self.assertRaisesRegex(ValueError, 'supports 6x'):
            run(self.root, api, self.selection, 5, poll_interval=0)
        self.assertEqual(api.submissions, [])


if __name__ == '__main__':
    unittest.main()
