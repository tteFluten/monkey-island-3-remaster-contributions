import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

import audit_comi_audio as audit
import comi_audio as music
import restore_comi_voices as voices


def wav(path, rate=22050):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as f:
        f.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        f.writeframes(b'\1\0\2\0' * 200)


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target, self.cache = self.root / 'target', self.root / 'cache'
        self.header = self.target / '.playtest/engine/source/engines/scumm/imuse_digi/dimuse_extmusic_table.h'
        self.header.parent.mkdir(parents=True)
        self.header.write_text('{"1100-H~1.IMX", "06 Bloodnose the Pirate"},\n{"1101-W~1.IMX", "06 Bloodnose the Pirate"},')
        self.name = '06 Bloodnose the Pirate'
        wav(self.cache / 'wav' / (self.name + '.wav'))
        cues, table_hash = music.mapping(self.target)
        music.atomic_json(self.cache / 'manifest.json', dict(cues=cues, engine_table_sha256=table_hash,
            tracks={self.name: dict(wav_sha256=music.digest(self.cache / 'wav' / (self.name + '.wav')))}))

    def test_mapping_deduplicates_tracks_not_cues(self):
        cues, _ = music.mapping(self.target)
        self.assertEqual(len(cues), 2)
        self.assertEqual(len(set(cues.values())), 1)
        self.header.write_text('{"a", "../escape"}')
        with self.assertRaises(ValueError):
            music.mapping(self.target)

    def test_corrupt_download_and_incomplete_file(self):
        source = self.root / 'source'
        source.write_bytes(b'correct audio')
        dest = self.root / 'download'
        dest.write_bytes(b'bad')
        dest.with_suffix('.part').write_bytes(b'incomplete')
        expected = hashlib.md5(source.read_bytes()).hexdigest()
        music.download(source.as_uri(), dest, source.stat().st_size, expected)
        self.assertEqual(dest.read_bytes(), source.read_bytes())
        with patch('urllib.request.urlopen', side_effect=AssertionError('should reuse')):
            music.download(source.as_uri(), dest, source.stat().st_size, expected)
        with patch('time.sleep'), self.assertRaises(ValueError):
            music.download(source.as_uri(), dest, 1, expected)
        self.assertEqual(dest.read_bytes(), source.read_bytes())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires ffmpeg')
    def test_real_conversion_preserves_rate_and_validates_truncation(self):
        source = self.cache / 'wav' / (self.name + '.wav')
        dest = self.root / 'converted.wav'
        self.assertEqual(music.convert(source, dest)['sample_rate'], 22050)
        dest.write_bytes(dest.read_bytes()[:-10])
        with self.assertRaises(ValueError):
            music.wav_info(dest)

    @patch('comi_audio.ensure_stopped')
    def test_install_rerun_and_rollback_preserve_existing_files(self, stopped):
        active = self.target / '.playtest/hd/audio'
        wav(active / 'custom.wav')
        before = music.tree_hashes(active)
        music.install(self.target, self.cache)
        journal = (self.target / '.playtest/audio-install.json').read_bytes()
        music.install(self.target, self.cache)
        self.assertEqual(journal, (self.target / '.playtest/audio-install.json').read_bytes())
        music.rollback(self.target)
        self.assertEqual(music.tree_hashes(active), before)

    @patch('comi_audio.ensure_stopped')
    def test_new_install_rollback_and_changed_file_guard(self, stopped):
        music.install(self.target, self.cache)
        active = self.target / '.playtest/hd/audio'
        (active / 'user-file').write_text('preserve me')
        with self.assertRaises(ValueError):
            music.rollback(self.target)
        (active / 'user-file').unlink()
        music.rollback(self.target)
        self.assertFalse(active.exists())

    @patch('comi_audio.ensure_stopped')
    def test_interrupted_directory_swap_recovers_original(self, stopped):
        active = self.target / '.playtest/hd/audio'
        wav(active / 'custom.wav')
        original = music.tree_hashes(active)
        real_rename = Path.rename
        def interrupt(path, dest):
            if path.name == 'stage':
                raise OSError('simulated interruption')
            return real_rename(path, dest)
        with patch.object(Path, 'rename', interrupt), self.assertRaises(OSError):
            music.install(self.target, self.cache)
        music.recover(self.target / '.playtest')
        self.assertEqual(music.tree_hashes(active), original)
        music.install(self.target, self.cache)
        music.rollback(self.target)
        self.assertEqual(music.tree_hashes(active), original)

    def test_running_engine_blocks_install(self):
        with patch('subprocess.check_output', return_value=str(self.target / '.playtest/engine/build/scummvm')):
            with self.assertRaises(RuntimeError):
                music.ensure_stopped(self.target)

    @patch('comi_audio.ensure_stopped')
    def test_interrupted_rollback_recovers_original(self, stopped):
        active = self.target / '.playtest/hd/audio'
        wav(active / 'custom.wav')
        original = music.tree_hashes(active)
        music.install(self.target, self.cache)
        real_rename = Path.rename
        def interrupt(path, dest):
            if path.name == 'audio' and 'audio-backups' in str(path):
                raise OSError('interrupted rollback')
            return real_rename(path, dest)
        with patch.object(Path, 'rename', interrupt), self.assertRaises(OSError):
            music.rollback(self.target)
        music.recover(self.target / '.playtest')
        self.assertEqual(music.tree_hashes(active), original)


def bundle(path, payload, name='LINE', ext='IMX'):
    directory = 12 + len(payload)
    path.write_bytes(b'LB83' + struct.pack('>II', directory, 1) + payload +
        name.encode().ljust(8, b'\0') + ext.encode().ljust(4, b'\0') + struct.pack('>II', 12, len(payload)))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'test.bun'
        self.valid = b'COMP' + struct.pack('>III', 1, 0, 4) + struct.pack('>IIII', 32, 4, 0, 0) + b'\0'*4

    def test_valid_compression_table(self):
        bundle(self.file, self.valid)
        data = audit.audit(self.file)
        self.assertEqual(data['counts'], {'valid_structure': 1})
        self.assertEqual(data['entries'][0]['name'], 'LINE.IMX')

    def test_metadata_not_audio_damage(self):
        bundle(self.file, b'not audio', name='PRELOAD', ext='')
        self.assertEqual(audit.audit(self.file)['counts'], {'metadata': 1})

    def test_bad_header_count_block_and_codec(self):
        for offset, value in [(0, 0x12345678), (4, 1000), (16, 1000), (24, 99)]:
            with self.subTest(offset=offset):
                payload = bytearray(self.valid)
                struct.pack_into('>I', payload, offset, value)
                bundle(self.file, payload)
                self.assertEqual(audit.audit(self.file)['counts'], {'invalid': 1})

    def test_truncated_header_directory_and_entry(self):
        self.file.write_bytes(b'LB83')
        self.assertTrue(audit.audit(self.file)['errors'])
        bundle(self.file, self.valid)
        self.file.write_bytes(self.file.read_bytes()[:-1])
        self.assertTrue(audit.audit(self.file)['errors'])
        bundle(self.file, self.valid)
        data = bytearray(self.file.read_bytes())
        struct.pack_into('>I', data, len(data)-4, 0xfffffff)
        self.file.write_bytes(data)
        self.assertEqual(audit.audit(self.file)['counts'], {'invalid': 1})


def multi_bundle(path, entries):
    payloads = b''.join(payload for _, payload in entries)
    rows, offset = [], 12
    for name, payload in entries:
        rows.append(name.encode().ljust(8, b'\0') + b'IMX\0' + struct.pack('>II', offset, len(payload)))
        offset += len(payload)
    path.write_bytes(b'LB83' + struct.pack('>II', 12+len(payloads), len(entries)) + payloads + b''.join(rows))


class VoiceRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / 'target'
        self.resource = self.target / '.playtest/game/RESOURCE'
        self.resource.mkdir(parents=True)
        self.work = Path(self.temp.name) / 'work'
        self.source = self.resource / 'VOXDISK1.BUN'
        self.donor = self.resource / 'VOXDISK2.BUN'
        self.valid = b'COMP' + struct.pack('>III', 1, 0, 4) + struct.pack('>IIII', 32, 4, 0, 0) + b'\0'*4
        multi_bundle(self.source, [('SHARED', self.valid), ('BROKEN', b'broken header....'), ('UNFIXED', b'bad data......')])
        multi_bundle(self.donor, [('SHARED', self.valid), ('BROKEN', self.valid)])
        self.original = self.source.read_bytes()

    def prepared(self):
        def decode(args, **kwargs):
            Path(args[-1]).write_bytes(b'iMUS\0\0\0\0MAP FRMT\0DATA\0')
        with patch('restore_comi_voices.build_decoder', return_value=Path('fixture-decoder')), \
             patch('restore_comi_voices.subprocess.run', side_effect=decode):
            voices.prepare(self.target, self.work)

    @patch('restore_comi_voices.ensure_stopped')
    def test_repair_appends_only_matching_entries_and_rollback_is_exact(self, stopped):
        self.prepared()
        prepared = audit.audit(self.work / 'VOXDISK1.BUN')
        self.assertEqual(prepared['counts'], {'valid_structure': 2, 'invalid': 1})
        self.assertGreater(prepared['entries'][1]['offset'], len(self.original)-1)
        self.assertEqual(self.source.read_bytes(), self.original)
        voices.apply(self.target, self.work)
        voices.apply(self.target, self.work)
        self.assertEqual((self.work / 'VOXDISK1.original.BUN').read_bytes(), self.original)
        voices.apply(self.target, self.work, undo=True)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_mismatched_donor_is_rejected(self):
        changed = self.valid[:-1] + b'\1'
        multi_bundle(self.donor, [('SHARED', changed), ('BROKEN', self.valid)])
        with self.assertRaisesRegex(ValueError, 'disagree'):
            voices.prepare(self.target, self.work)
        self.assertEqual(self.source.read_bytes(), self.original)

    @patch('restore_comi_voices.ensure_stopped')
    def test_changes_since_preparation_block_install(self, stopped):
        self.prepared()
        self.source.write_bytes(self.original + b'changed')
        with self.assertRaises(ValueError):
            voices.apply(self.target, self.work)


if __name__ == '__main__':
    unittest.main()
