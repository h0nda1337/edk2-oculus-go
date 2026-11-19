"""Original structural verifier for the integrated direct-entry firmware.

SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

BASE = 0x80080000
SIZE = 0x400000
FV_OFFSET = 0x1000


def branch_destination(blob, offset):
    word = struct.unpack_from('<I', blob, offset)[0]
    if word & 0xFC000000 != 0x14000000:
        raise ValueError(f'Expected A64 B at {offset:#x}, got {word:#x}')
    relative = word & 0x03FFFFFF
    if relative & 0x02000000:
        relative -= 0x04000000
    target = offset + relative * 4
    if not 0 <= target < len(blob):
        raise ValueError('Branch target outside firmware')
    return target


def verify(data):
    if len(data) != SIZE:
        raise ValueError('Expected a complete 4 MiB FD')
    values = struct.unpack_from('<II6QII', data)
    if values != (0x14000400, 0xD503201F, 0x80000, SIZE,
                  0, 0, 0, 0, 0x644D5241, 0):
        raise ValueError('Integrated ARM64 header mismatch')
    if branch_destination(data, 0) != FV_OFFSET:
        raise ValueError('Header does not enter the in-place FV')
    if data[FV_OFFSET + 40:FV_OFFSET + 44] != b'_FVH':
        raise ValueError('Firmware volume signature missing')
    fv_length = struct.unpack_from('<Q', data, FV_OFFSET + 32)[0]
    header_length = struct.unpack_from('<H', data, FV_OFFSET + 48)[0]
    fv_end = FV_OFFSET + fv_length
    if fv_end == 0x80000:
        guard = 0x3be000
        if (data[fv_end:guard] != b'GODXEFD1' + b'\xff' * (guard-fv_end-8) or
                data[guard:] != b'GOSTACK1' + b'\xff' * (SIZE-guard-8)):
            raise ValueError('SEC_DXE writable workspace or guard signature differs')
    elif fv_end == 0x3be000:
        if data[fv_end:] != b'GOSTACK1' + b'\xff' * (SIZE - fv_end - 8):
            raise ValueError('SEC_STACK guard signature or reserved FD tail differs')
    elif fv_end != SIZE:
        raise ValueError('Firmware volume length mismatch')
    if header_length < 56 or header_length % 2 or header_length > fv_length:
        raise ValueError('Invalid FV header size')
    if sum(struct.unpack_from(f'<{header_length // 2}H', data, FV_OFFSET)) & 0xFFFF:
        raise ValueError('Firmware volume header checksum mismatch')
    entry = branch_destination(data, FV_OFFSET)
    if not FV_OFFSET + header_length <= entry < fv_end:
        raise ValueError('SEC entry not within FV contents')
    return {
        'result': 'PASS-STRUCTURAL-ONLY',
        'sha256': hashlib.sha256(data).hexdigest(),
        'size': len(data),
        'loadAddress': hex(BASE),
        'volumeAddress': hex(BASE + FV_OFFSET),
        'secEntryAddress': hex(BASE + entry),
        'entryBranches': [hex(BASE), hex(BASE + FV_OFFSET), hex(BASE + entry)],
        'bootShim': False,
        'firmwareCopyStage': False,
        'physicalExecution': 'UNKNOWN',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fd', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = verify(args.fd.read_bytes())
    encoded = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.write_text(encoded, encoding='utf-8')
    print(encoded, end='')


if __name__ == '__main__':
    main()
