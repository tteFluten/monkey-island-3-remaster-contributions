import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stage_videos import stage, validate_video

ROOT = Path(__file__).resolve().parents[1]
VIDEO = dict(codec_type='video', width=2880, height=2160,
             r_frame_rate='12/1', avg_frame_rate='12/1', nb_frames='30')


class VideoStagingTests(unittest.TestCase):
    def fixture(self, root):
        source, local = root / 'supplied', root / 'playtest'
        source.mkdir()
        resource = local / 'game/RESOURCE'
        resource.mkdir(parents=True)
        header = bytearray(800)
        header[:4], header[8:12] = b'ANIM', b'AHDR'
        struct.pack_into('<H', header, 18, 30)
        struct.pack_into('<H', header, 790, 12)
        (resource / 'SINKSHP.SAN').write_bytes(header)
        (source / 'SINKSHIP.mp4').write_bytes(b'supplied replacement')
        return source, local

    @patch('stage_videos.subprocess.check_output', return_value=json.dumps({'streams': [VIDEO]}).encode())
    def test_alias_copy_receipt_repeat_and_backup(self, probe):
        with tempfile.TemporaryDirectory() as directory:
            source, local = self.fixture(Path(directory))
            original = (local / 'game/RESOURCE/SINKSHP.SAN').read_bytes()
            records = stage(source, local, 'ffprobe')
            target = local / 'hd/videos/SINKSHIP.mp4'
            self.assertEqual(target.read_bytes(), b'supplied replacement')
            self.assertEqual(records[0]['san'], 'SINKSHP.SAN')
            self.assertEqual(json.loads((local / 'video-staging.json').read_text())['records'], records)
            modified = target.stat().st_mtime_ns
            stage(source, local, 'ffprobe')
            self.assertEqual(target.stat().st_mtime_ns, modified)
            (source / 'SINKSHIP.mp4').write_bytes(b'updated movie')
            stage(source, local, 'ffprobe')
            backups = list((local / 'backups').glob('videos-*/SINKSHIP.mp4'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b'supplied replacement')
            self.assertEqual((local / 'game/RESOURCE/SINKSHP.SAN').read_bytes(), original)

    def test_wrong_names_rejected_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            source, local = self.fixture(Path(directory))
            (source / 'SINKSHIP.mp4').rename(source / 'wrong.mp4')
            with self.assertRaises(ValueError):
                stage(source, local, 'ffprobe')
            self.assertFalse((local / 'hd/videos').exists())

    def test_frame_rate_size_and_duration_validation(self):
        original = dict(frames=30, fps=12)
        for frames in (20, 30, 40):
            self.assertEqual(validate_video(dict(VIDEO, nb_frames=str(frames)), original), frames)
        for change in ({'nb_frames': '19'}, {'nb_frames': '0'}, {'r_frame_rate': '24/1'},
                       {'avg_frame_rate': '11/1'}, {'width': 1920}, {'height': 1080}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_video(dict(VIDEO, **change), original)


class VideoSubtitleTests(unittest.TestCase):
    def test_transparency_black_outlines_white_and_resolutions(self):
        if not shutil.which('c++'):
            self.skipTest('C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'test.cpp'
            binary = source.with_suffix('')
            source.write_text(r'''
#include "hd_video_support.h"
#include <cassert>
#include <vector>
int main() {
    // Match COMI SMUSH's signed palette rules, including color -1 and
    // the color-31 fill exception that takes precedence over the outline.
    assert(HdVideoSupport::textColor(225, 31) == 255);
    assert(HdVideoSupport::textColor(225, 15) == 0);
    assert(HdVideoSupport::textColor(241, 15) == 255);
    assert(HdVideoSupport::textColor(255, -1) == 255);
    assert(HdVideoSupport::textColor(224, 32) == 255);
    assert(HdVideoSupport::textColor(1, 31) == 1);
    unsigned char dark[] = {0, 0, 255, 15};
    unsigned char light[] = {255, 0, 255, 15};
    unsigned char palette[768] = {};
    palette[765] = palette[766] = palette[767] = 255;
    palette[45] = 255;
    for (int scale : {1, 4, 6}) {
        std::vector<unsigned int> frame(4 * scale * scale, 0xff123456);
        HdVideoSupport::subtitles(frame.data(), 4 * scale, scale, dark, light, 4, 1, palette);
        for (int y = 0; y < scale; ++y) for (int x = 0; x < 4 * scale; ++x) {
            unsigned int expected[] = {0xff123456, 0xff000000, 0xffffffff, 0xff0000ff};
            assert(frame[y * 4 * scale + x] == expected[x / scale]);
        }
    }
}
''')
            subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                            '-I', str(ROOT / 'tools/engine'), str(source), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, timeout=10, capture_output=True)


if __name__ == '__main__':
    unittest.main()
