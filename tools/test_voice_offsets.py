from pathlib import Path
import json
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from audit_comi_audio import audit
from recover_comi_voice_offsets import scan, infer_matches, prepare, equivalent_texts
from recover_comi_voice_splice import select_verified


def payload(length):
    return b'COMP' + struct.pack('>III', 1, 0, length) + struct.pack('>IIII', 32, length, 0, 0) + b'\0' * length


class OffsetTests(unittest.TestCase):
    def setUp(self):
        self.entries = [dict(index=i, name=f'LINE{i}.IMX', offset=offset, size=size, status='invalid')
                        for i, (offset, size) in enumerate([(12, 36), (48, 40), (88, 44)])]
        self.candidates = {e['offset'] + 200: dict(offset=e['offset'] + 200, size=e['size']) for e in self.entries}

    def test_repeated_displacement_requires_adjacent_sizes_and_order(self):
        matches, shifts, runs = infer_matches(self.entries, self.candidates)
        self.assertEqual(len(matches), 3)
        self.assertEqual(shifts, {200: 3})
        self.assertEqual(runs[0]['count'], 3)

    def test_isolated_length_matches_are_rejected(self):
        candidates = {e['offset']+delta: dict(offset=e['offset']+delta, size=e['size'])
                      for e, delta in zip(self.entries, [100, 200, 300])}
        self.assertFalse(infer_matches(self.entries, candidates)[0])

    def test_ambiguous_duplicate_runs_are_rejected(self):
        candidates = dict(self.candidates)
        candidates.update({e['offset']+400: dict(offset=e['offset']+400,size=e['size']) for e in self.entries})
        self.assertFalse(infer_matches(self.entries, candidates)[0])

    def test_nonadjacent_directory_entries_are_rejected(self):
        self.entries[-1]['index'] = 8
        self.assertFalse(infer_matches(self.entries, self.candidates)[0])

    def test_scanner_rejects_truncation_and_noncontiguous_blocks(self):
        self.assertEqual(scan(payload(4))[0]['size'], 36)
        self.assertFalse(scan(payload(4)[:-1]))
        bad = bytearray(payload(4))
        struct.pack_into('>I', bad, 16, 16)
        self.assertFalse(scan(bad))

    def test_equivalent_line_requires_same_character_and_spoken_words(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / '.playtest/game'
            game.mkdir(parents=True)
            (game / 'COMI.LA1').write_bytes(b'/SGSY519/What!?\0/SSSY315/What?!\0/SSGT315/What?!\0')
            (game / 'COMI.LA2').write_bytes(b'')
            self.assertEqual(equivalent_texts(root, 'SGSY519.IMX', 'SSSY315.IMX')['SGSY519.IMX'], 'What!?')
            with self.assertRaises(ValueError):
                equivalent_texts(root, 'SGSY519.IMX', 'SSGT315.IMX')
            (game / 'COMI.LA2').write_bytes(b'/SSSY315/Where?\0')
            with self.assertRaises(ValueError):
                equivalent_texts(root, 'SGSY519.IMX', 'SSSY315.IMX')

    def test_preparation_preserves_source_and_rejects_failed_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'target'
            resource = target / '.playtest/game/RESOURCE'
            resource.mkdir(parents=True)
            data = bytearray(b'LB83' + struct.pack('>II', 132, 3) + b'x' * 120)
            for entry in self.entries:
                name, ext = entry['name'].split('.')
                data.extend(name.encode().ljust(8,b'\0') + ext.encode().ljust(4,b'\0') +
                            struct.pack('>II',entry['offset'],entry['size']))
            data.extend(b'\0' * (212-len(data)))
            for length in [4, 8, 12]:
                data.extend(payload(length))
            source = root / 'original.BUN'
            source.write_bytes(data)
            (resource / 'VOXDISK1.BUN').write_bytes(data)
            (resource / 'VOXDISK2.BUN').write_bytes(b'donor fixture')
            def decode(command, **kwargs):
                if 'LINE1' in command[1]:
                    return subprocess.CompletedProcess(command, 2, b'', b'bad compressed payload')
                Path(command[2]).write_bytes(b'iMUS\0\0\0\0MAP FRMT\0DATA\0')
                return subprocess.CompletedProcess(command, 0, b'', b'')
            with patch('recover_comi_voice_offsets.build_decoder', return_value=Path('fixture')), \
                 patch('recover_comi_voice_offsets.subprocess.run', side_effect=decode):
                prepare(target, source, root / 'work', quarantine=['LINE1.IMX'])
            manifest = json.loads((root / 'work/repair.json').read_text())
            self.assertEqual(len(manifest['repairs']), 2)
            self.assertEqual(manifest['remaining_invalid'], 1)
            self.assertEqual(manifest['rejected'][0]['name'], 'LINE1.IMX')
            self.assertEqual(manifest['quarantined'][0]['name'], 'LINE1.IMX')
            self.assertEqual(source.read_bytes(), data)
            self.assertEqual((resource / 'VOXDISK1.BUN').read_bytes(), data)
            self.assertEqual(audit(root / 'work/VOXDISK1.BUN')['counts'], {'valid_structure': 2, 'invalid': 1})


class SpliceTests(unittest.TestCase):
    def candidate(self, checksum='same', before=2048, after=0, ok=True):
        return dict(payload_sha256=checksum, equal_before=before, equal_after=after, decode_ok=ok)

    def test_identical_reconstructions_with_overlapping_source_sector_are_accepted(self):
        candidates = [self.candidate(before=0, after=4096), self.candidate(before=2048, after=2048)]
        self.assertEqual(select_verified(candidates)['payload_sha256'], 'same')

    def test_ambiguous_but_decodable_reconstructions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            select_verified([self.candidate('a'), self.candidate('b')])

    def test_decode_success_without_source_overlap_is_insufficient(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            select_verified([self.candidate(before=0, after=0)])

    def test_undecodable_candidates_are_rejected(self):
        with self.assertRaises(ValueError):
            select_verified([self.candidate(ok=False)])


if __name__ == '__main__':
    unittest.main()
