import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import asset_pack as pack


class AssetPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'pack'
        self.target = Path(self.temp.name) / 'target'
        (self.root / 'assets/runtime').mkdir(parents=True)
        self.target.mkdir()
        self.rows = []
        self.add('assets/runtime/art.png', b'new-art', '.playtest/hd/objects/art.png')

    def add(self, path, data, destination, **extra):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        self.rows.append(dict(path=path, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), destination=destination, **extra))
        (self.root / 'assets/manifest.json').write_text(json.dumps(dict(version=1, files=self.rows)))

    def target_file(self, relative, data):
        p = self.target / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_dry_run_install_repeat_and_rollback_preserve_unrelated_files(self):
        art = self.target_file(self.rows[0]['destination'], b'old-art')
        save = self.target_file('.playtest/saves/comi.s00', b'save')
        before = sorted(str(p) for p in self.target.rglob('*'))
        self.assertEqual(pack.install(self.root, self.target, True)['changed_files'], 1)
        self.assertEqual(before, sorted(str(p) for p in self.target.rglob('*')))
        receipt = pack.install(self.root, self.target)
        self.assertEqual(art.read_bytes(), b'new-art')
        self.assertEqual(pack.install(self.root, self.target)['changed_files'], 0)
        pack.rollback(self.target, receipt['transaction'])
        self.assertEqual(art.read_bytes(), b'old-art')
        self.assertEqual(save.read_bytes(), b'save')
        self.assertEqual(pack.rollback(self.target, receipt['transaction'])['status'], 'already-rolled-back')

    def test_missing_or_corrupt_file_prevents_all_changes(self):
        self.add('assets/runtime/second.png', b'second', '.playtest/hd/objects/second.png')
        for mode in ['corrupt', 'missing']:
            p = self.root / self.rows[1]['path']
            if mode == 'corrupt': p.write_bytes(b'broken')
            else: p.unlink()
            with self.assertRaises(ValueError): pack.install(self.root, self.target)
            self.assertFalse((self.target / '.playtest').exists())

    def test_voice_compatibility_checked_before_installation(self):
        voice = '.playtest/game/RESOURCE/VOXDISK1.BUN'
        self.add('assets/voices/VOXDISK1.BUN', b'repaired', voice,
                 compatible_input_sha256=[hashlib.sha256(b'original').hexdigest()])
        with self.assertRaisesRegex(ValueError, 'voice bundle'): pack.install(self.root, self.target)
        p = self.target_file(voice, b'wrong edition')
        with self.assertRaisesRegex(ValueError, 'voice bundle'): pack.install(self.root, self.target)
        self.assertFalse((self.target / self.rows[0]['destination']).exists())
        p.write_bytes(b'original')
        receipt = pack.install(self.root, self.target)
        self.assertEqual(p.read_bytes(), b'repaired')
        pack.rollback(self.target, receipt['transaction'])
        self.assertEqual(p.read_bytes(), b'original')

    def test_rollback_refuses_to_destroy_later_edits(self):
        receipt = pack.install(self.root, self.target)
        self.target_file(self.rows[0]['destination'], b'my edit')
        with self.assertRaisesRegex(ValueError, 'Locally edited'): pack.rollback(self.target, receipt['transaction'])

    def test_symlinks_and_traversal_are_rejected(self):
        outside = self.target.parent / 'outside'
        outside.mkdir()
        (self.target / '.playtest').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): pack.install(self.root, self.target, True)
        with self.assertRaises(ValueError): pack.within(self.root, '../outside')
        self.assertEqual(list(outside.iterdir()), [])

    def test_failure_rolls_back_already_installed_files(self):
        self.add('assets/runtime/second.png', b'second', '.playtest/hd/objects/second.png')
        art = self.target_file(self.rows[0]['destination'], b'old-art')
        replace = pack.os.replace
        def fail_second(src, dst):
            if str(src).endswith('.new') and str(dst).endswith('second.png'): raise OSError('simulated disk error')
            return replace(src, dst)
        with patch.object(pack.os, 'replace', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'disk error'): pack.install(self.root, self.target)
        self.assertEqual(art.read_bytes(), b'old-art')
        self.assertFalse((self.target / self.rows[1]['destination']).exists())

    def test_live_engine_blocks_installation(self):
        owner = self.target_file('.playtest/engine.lock/owner.json', json.dumps({'gamePid': pack.os.getpid()}).encode())
        with self.assertRaisesRegex(ValueError, 'Stop'): pack.install(self.root, self.target)
        self.assertTrue(owner.exists())

    def test_changed_master_requires_a_matching_runtime_export(self):
        self.add('assets/masters/topaz-4x/art.png', b'new-art', None, canonical=True)
        runtime, master = self.rows
        runtime.update(derived_from=master['path'], transform=dict(kind='copy', source_sha256=master['sha256']))
        manifest = self.root / 'assets/manifest.json'
        manifest.write_text(json.dumps(dict(version=1, files=self.rows)))
        pack.verify(self.root)
        (self.root / master['path']).write_bytes(b'changed-art')
        master.update(sha256=hashlib.sha256(b'changed-art').hexdigest(), bytes=len(b'changed-art'))
        manifest.write_text(json.dumps(dict(version=1, files=self.rows)))
        with self.assertRaisesRegex(ValueError, 'outdated master'): pack.install(self.root, self.target)
        self.assertFalse((self.target / '.playtest').exists())


if __name__ == '__main__': unittest.main()
