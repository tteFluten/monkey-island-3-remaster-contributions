import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from asset_edits import replace, resolve_url
from install_asset_drafts import install
from quiver_cannon import atomic
from topaz_character_cutouts import digest


def png(size=(16, 20), color=(10, 20, 30, 100)):
    output = io.BytesIO()
    Image.new('RGBA', size, color).save(output, 'PNG')
    return output.getvalue()


class AssetEditTests(unittest.TestCase):
    def fixture(self, root):
        out = root / 'output/topaz-scenes'
        batch = root / 'output/topaz-batch'
        source = 'costumes/LFLF_0001_AKOS_0002_frame_22.png'
        alias = 'costumes/LFLF_0009_AKOS_0002_frame_22.png'
        master = out / 'room-0001/4x' / source
        master.parent.mkdir(parents=True)
        master.write_bytes(png())
        atomic(out / 'room-0001/jobs.json', {source: dict(state='validated', validation=dict(passed=True, sha256=digest(master)))})
        atomic(batch / 'manifest.json', dict(records=[dict(source=s, size=[4, 5], cleaned_sha256='input') for s in (source, alias)]))
        atomic(out / 'plan.json', dict(source_batch=str(batch), scenes=[dict(id='room-0001', sources=[
            dict(source=source, size=[4, 5], operation='upscale-matting'),
            dict(source=alias, size=[4, 5], operation='alias', parent=source)])]))
        return out, source, alias, master, '/files/' + master.relative_to(root).as_posix()

    def test_edit_survives_install_and_updates_aliases_without_changing_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, source, alias, master, url = self.fixture(root)
            before = master.read_bytes()
            journal = (out / 'room-0001/jobs.json').read_bytes()
            data = png(color=(50, 40, 30, 0))
            result = replace(root, url, digest(master), data)
            self.assertTrue(result['installed'])
            self.assertEqual((Path(result['backup']) / 'previous.png').read_bytes(), before)
            self.assertEqual(master.read_bytes(), before)
            self.assertEqual((out / 'room-0001/jobs.json').read_bytes(), journal)
            for attempt in range(2):
                receipt = install(out, root / '.playtest')
                for name in (source, alias):
                    for pack in ('topaz-cannon', 'topaz-crisp'):
                        target = root / '.playtest/hd' / pack / name.replace('_frame_', '_aframe_')
                        self.assertEqual(target.read_bytes(), data)
                self.assertEqual(receipt['new_or_changed'], 0)
            with self.assertRaisesRegex(ValueError, 'changed since'):
                replace(root, url, digest(master), before)
            again = replace(root, result['url'], result['sha256'], before)
            self.assertTrue(again['installed'])

    def test_live_game_defers_runtime_and_invalid_canvas_cannot_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, source, alias, master, url = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'canvas'):
                replace(root, url, digest(master), png(size=(4, 5)))
            self.assertFalse((root / 'output/asset-edits/manifest.json').exists())
            atomic(root / '.playtest/process.json', dict(pid=os.getpid()))
            data = png(color=(1, 2, 3, 0))
            result = replace(root, url, digest(master), data)
            self.assertFalse(result['installed'])
            self.assertIn('pending', result['message'])
            self.assertFalse((root / '.playtest/hd').exists())
            (root / '.playtest/process.json').unlink()
            install(out, root / '.playtest')
            self.assertEqual((root / '.playtest/hd/topaz-cannon' / source.replace('_frame_', '_aframe_')).read_bytes(), data)

    def test_library_file_backup_revision_check_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'previews/test.png'
            target.parent.mkdir()
            target.write_bytes(png())
            old = target.read_bytes()
            sha = digest(target)
            replacement = png(color=(1, 1, 1, 0))
            result = replace(root, '/api/assets/file/previews/test.png', sha, replacement)
            self.assertEqual(target.read_bytes(), replacement)
            self.assertEqual((Path(result['backup']) / 'previous.png').read_bytes(), old)
            with self.assertRaisesRegex(ValueError, 'changed since'):
                replace(root, result['url'], sha, old)
            for url in ('https://example.com/files/previews/test.png', '/files/previews/../secrets.png',
                        '/files/previews/%2e%2e/secrets.png', '/files/.context/secrets.png',
                        '/files/output/topaz-batch/6x/costumes/LFLF_0001_AKOS_0002_frame_22.png'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    resolve_url(root, url)
            target.unlink()
            target.symlink_to('/tmp/outside.png')
            with self.assertRaisesRegex(ValueError, 'outside'):
                resolve_url(root, '/files/previews/test.png')


if __name__ == '__main__': unittest.main()
