import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
from import_discs import copy_checked, import_discs, validate_game


class DiscTests(unittest.TestCase):
    def test_duplicate_conflict_preserves_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'source', Path(folder) / 'target'
            source.write_bytes(b'original'); target.write_bytes(b'original')
            copy_checked(source, target)
            source.write_bytes(b'different')
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                copy_checked(source, target)
            self.assertEqual(target.read_bytes(), b'original')

    def test_incomplete_game_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'COMI.LA2'):
                validate_game(Path(folder))

    def test_conflicting_disc_detaches_and_keeps_existing_import(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            discs = [base / 'one.iso', base / 'two.iso']
            for disc in discs:
                disc.write_bytes(b'iso')
            destination = base / 'game'
            destination.mkdir(); (destination / 'old').write_bytes(b'keep')
            calls = []
            def run(args, **kwargs):
                calls.append(args)
                if args[1] == 'attach':
                    mount = Path(args[args.index('-mountpoint') + 1])
                    (mount / 'COMI.LA0').write_bytes(args[-1].encode())
                return subprocess.CompletedProcess(args, 0)
            with patch('import_discs.subprocess.run', side_effect=run):
                with self.assertRaisesRegex(ValueError, 'Conflicting'):
                    import_discs(discs, destination)
            self.assertEqual(sum(c[1] == 'detach' for c in calls), 2)
            self.assertEqual((destination / 'old').read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
