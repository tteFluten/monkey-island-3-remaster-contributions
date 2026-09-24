"""Collect cels from COMI's looping AKOS chores without guessing frame ranges.

This deliberately supports only the opcodes used by the selected idle/walk
chores. Unknown commands fail closed before a paid batch can be prepared.
Layout follows the pinned engine's AkosCostumeLoader and akos_increaseAnim.
"""
import struct

# Command lengths include the two-byte opcode. Jump targets are little-endian.
COMMAND_SIZES = {
    0xc001: 2, 0xc010: 5, 0xc015: 3, 0xc031: 5, 0xc040: 5,
    0xc042: 3, 0xc060: 2, 0xc061: 2, 0xc070: 7, 0xc071: 7,
    0xc072: 7, 0xc073: 7, 0xc074: 7, 0xc075: 7, 0xc082: 7,
    0xc083: 3, 0xc08a: 4,
}
CONDITIONAL_JUMPS = {0xc031, 0xc070, 0xc071, 0xc072, 0xc073, 0xc074, 0xc075}


def entrypoints(fields, frame):
    header = struct.unpack('<6H', fields['AKHD'][:12])
    directions = 8 if header[1] & 2 else 4
    result = set()
    for direction in range(directions):
        animation = frame * directions + direction
        if animation >= header[2]:
            continue
        offset = struct.unpack_from('<H', fields['AKCH'], animation * 2)[0]
        if not offset:
            continue
        mask = struct.unpack_from('<H', fields['AKCH'], offset)[0]
        position = offset + 2
        for limb in range(16):
            if mask & (0x8000 >> limb):
                kind = fields['AKCH'][position]
                position += 1
                if kind not in (1, 4, 5):
                    if kind != 6:
                        raise ValueError(f'Unsupported animation type {kind}; inspect the chore first')
                    start, _ = struct.unpack_from('<HH', fields['AKCH'], position)
                    position += 4
                    result.add(start)
    return result


def cels(fields, frame):
    data = fields['AKSQ']
    cel_count = struct.unpack('<6H', fields['AKHD'][:12])[3]
    queue = list(entrypoints(fields, frame))
    seen, result, operations = set(), set(), set()

    def token(position):
        if not 0 <= position < len(data):
            raise ValueError('Animation jumps outside AKSQ')
        value = data[position]
        if value & 128:
            if position + 2 > len(data):
                raise ValueError('Truncated AKOS token')
            return int.from_bytes(data[position:position + 2], 'big'), 2
        return value, 1

    def add_cel(value):
        value &= 0xfff
        if value >= cel_count:
            raise ValueError('Animation refers to an invalid cel')
        result.add(value)

    while queue:
        position = queue.pop()
        if position in seen:
            continue
        seen.add(position)
        code, length = token(position)
        if code < 0xc000:
            add_cel(code)
            queue.append(position + length)
            continue
        operations.add(hex(code))
        if code == 0xc0ff:
            continue
        if code in (0xc020, 0xc025):  # DrawMany / RelativeOffsetDrawMany
            position += 4 if code == 0xc025 else 0
            count = data[position + 2]
            position += 3
            for _ in range(count):
                position += 4  # signed x/y offsets do not affect frame selection
                value, length = token(position)
                add_cel(value)
                position += length
            queue.append(position)
            continue
        if code == 0xc030 or code in CONDITIONAL_JUMPS:
            queue.append(struct.unpack_from('<H', data, position + 2)[0])
            if code == 0xc030:
                continue
        if code not in COMMAND_SIZES:
            raise ValueError(f'Unsupported opcode {code:#x} in chore {frame} at {position}')
        queue.append(position + COMMAND_SIZES[code])
    return sorted(result), sorted(operations)
