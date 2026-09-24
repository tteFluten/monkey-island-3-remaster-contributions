import copy
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from audit_comi_audio import audit
from comi_audio import digest
from recover_comi_voice_donor import prepare, select_replacements
from restore_comi_voices import apply
from test_comi_audio import multi_bundle


class DonorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'target'
        resource = self.target / '.playtest/game/RESOURCE'
        resource.mkdir(parents=True)
        self.current = resource / 'VOXDISK1.BUN'
        (resource / 'VOXDISK2.BUN').write_bytes(b'unchanged disc two')
        self.donor = self.root / 'donor.bun'
        valid = b'COMP' + struct.pack('>III', 1, 0, 4) + struct.pack('>IIII', 32, 4, 0, 0) + b'\0'*4
        anchors = [(f'ANCH{i:03}', valid) for i in range(100)]
        multi_bundle(self.current, anchors + [('MISSING', b'bad sound data'), ('ALTT', valid[:-1]+b'\1')])
        multi_bundle(self.donor, anchors + [('MISSING', valid), ('ALTT', valid)])
        self.original = self.current.read_bytes()
        self.previous = self.root / 'previous.json'
        self.previous.write_text(json.dumps(dict(prepared_sha256=digest(self.current),
            target_workspace=str(self.target), total_restored_entries=3)))
        self.provenance = self.root / 'provenance.json'
        self.provenance.write_text(json.dumps(dict(downloaded_bundle_sha256=digest(self.donor))))
        self.work = self.root / 'work'

    def selection(self):
        return audit(self.current), audit(self.donor)

    def test_matching_donor_recovers_missing_and_explicit_original_take(self):
        repairs, anchors = select_replacements(*self.selection(), ['ALTT.IMX'])
        self.assertEqual(len(anchors), 100)
        self.assertEqual([a['name'] for a, b in repairs], ['MISSING.IMX', 'ALTT.IMX'])

    def test_any_unexpected_healthy_difference_rejects_donor(self):
        with self.assertRaisesRegex(ValueError, 'Healthy recording differs'):
            select_replacements(*self.selection())

    def test_wrong_directory_and_damaged_donor_rejected(self):
        current, donor = self.selection()
        for field, value in [('name', 'OTHER.IMX'), ('status', 'invalid')]:
            modified = copy.deepcopy(donor)
            modified['entries'][0][field] = value
            with self.assertRaises(ValueError):
                select_replacements(current, modified, ['ALTT.IMX'])

    def test_insufficient_matching_anchors_rejected(self):
        current, donor = self.selection()
        current['entries'] = current['entries'][1:]
        donor['entries'] = donor['entries'][1:]
        with self.assertRaisesRegex(ValueError, 'Insufficient'):
            select_replacements(current, donor, ['ALTT.IMX'])

    def do_prepare(self, fail=False):
        def decode(command, **kwargs):
            Path(command[2]).write_bytes(b'iMUS\0\0\0\0MAP FRMT\0DATA\0')
            return subprocess.CompletedProcess(command, 0, b'', b'sanitizer failure' if fail else b'')
        with patch('recover_comi_voice_donor.build_decoder', return_value=Path('fixture')), \
             patch('recover_comi_voice_donor.subprocess.run', side_effect=decode):
            prepare(self.target, self.donor, self.previous, self.provenance, self.work, ['ALTT.IMX'])

    @patch('restore_comi_voices.ensure_stopped')
    def test_prepare_install_rerun_and_exact_rollback(self, stopped):
        self.do_prepare()
        self.assertEqual(self.current.read_bytes(), self.original)
        manifest = json.loads((self.work / 'repair.json').read_text())
        self.assertEqual(manifest['newly_restored_entries'], 1)
        self.assertEqual(manifest['total_restored_entries'], 4)
        apply(self.target, self.work)
        self.assertEqual([e['sha256'] for e in audit(self.current)['entries']],
                         [e['sha256'] for e in audit(self.donor)['entries']])
        apply(self.target, self.work)
        apply(self.target, self.work, undo=True)
        self.assertEqual(self.current.read_bytes(), self.original)

    def test_native_sanitizer_failure_never_prepares_installable_bundle(self):
        with self.assertRaisesRegex(ValueError, 'Native decoder rejected'):
            self.do_prepare(fail=True)
        self.assertFalse((self.work / 'repair.json').exists())
        self.assertEqual(self.current.read_bytes(), self.original)

    def test_download_checksum_mismatch_rejected(self):
        self.provenance.write_text(json.dumps(dict(downloaded_bundle_sha256='wrong')))
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.do_prepare()
        self.assertFalse(self.work.exists())


if __name__ == '__main__':
    unittest.main()
