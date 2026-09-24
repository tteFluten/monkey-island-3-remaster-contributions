import struct
import unittest
from costume_sequences import cels


def fixture(sequence, kind=6):
    return {'AKHD': struct.pack('<6H', 1, 0, 4, 700, 1, 16),
            'AKCH': struct.pack('<4H', 8, 8, 8, 8) + struct.pack('<HBHH', 0x8000, kind, 0, 0),
            'AKSQ': sequence}


class SequenceTests(unittest.TestCase):
    def test_drawmany_keeps_cel_zero_extended_cels_and_stops_on_loop(self):
        data = b'\xc0\x20\x02' + struct.pack('<hh', -20, 30) + b'\0'
        data += struct.pack('<hh', 5, -10) + b'\x82\x57'  # cel 599
        data += b'\xc0\x30\0\0'
        self.assertEqual(cels(fixture(data), 0)[0], [0, 599])

    def test_conditional_jump_collects_both_paths(self):
        data = b'\xc0\x31\x08\0\0' + b'\x01\xc0\xff' + b'\x02\xc0\xff'
        self.assertEqual(cels(fixture(data), 0)[0], [1, 2])

    def test_unknown_commands_and_animation_types_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported opcode'):
            cels(fixture(b'\xc0\xfe'), 0)
        with self.assertRaisesRegex(ValueError, 'animation type'):
            cels(fixture(b'\xc0\xff', kind=2), 0)

    def test_invalid_cel_and_out_of_range_jump_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid cel'):
            cels(fixture(b'\x8f\xff\xc0\xff'), 0)
        with self.assertRaisesRegex(ValueError, 'outside AKSQ'):
            cels(fixture(b'\xc0\x30\xff\xff'), 0)


if __name__ == '__main__':
    unittest.main()
