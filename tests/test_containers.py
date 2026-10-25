"""Offline format/corruption tests; all fixtures are synthetic.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import gzip
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import android_boot
import verify_fd


def fixture_fd():
    data = bytearray(b'\xff' * verify_fd.SIZE)
    struct.pack_into('<II6QII', data, 0, 0x14000400, 0xD503201F,
                     0x80000, len(data), 0, 0, 0, 0, 0x644D5241, 0)
    start = verify_fd.FV_OFFSET
    data[start:start + 72] = bytes(72)
    struct.pack_into('<I', data, start, 0x14000400)  # synthetic entry +0x1000
    struct.pack_into('<Q', data, start + 32, len(data) - start)
    data[start + 40:start + 44] = b'_FVH'
    struct.pack_into('<H', data, start + 48, 72)
    checksum = -sum(struct.unpack_from('<36H', data, start)) & 0xFFFF
    struct.pack_into('<H', data, start + 50, checksum)
    return data


class Formats(unittest.TestCase):
    def test_integrated_branches(self):
        result = verify_fd.verify(fixture_fd())
        self.assertEqual(result['secEntryAddress'], '0x80082000')
        self.assertFalse(result['firmwareCopyStage'])
        self.assertEqual(result['physicalExecution'], 'UNKNOWN')

    def test_truncation(self):
        with self.assertRaises(ValueError):
            verify_fd.verify(fixture_fd()[:-1])

    def test_header_corruption(self):
        data = fixture_fd()
        data[56] ^= 1
        with self.assertRaises(ValueError):
            verify_fd.verify(data)

    def test_volume_checksum(self):
        data = fixture_fd()
        data[verify_fd.FV_OFFSET + 44] ^= 1
        with self.assertRaises(ValueError):
            verify_fd.verify(data)

    def test_out_of_image_branch(self):
        with self.assertRaises(ValueError):
            verify_fd.branch_destination(struct.pack('<I', 0x14001000), 0)

    def test_requires_exact_dtb(self):
        with self.assertRaisesRegex(ValueError, 'exact local'):
            android_boot.make_container(fixture_fd(), bytes(40))

    def test_container_roundtrip_and_id(self):
        fd = bytes(fixture_fd())
        dtb = struct.pack('>II', 0xD00DFEED, 40) + bytes(32)
        with patch.object(android_boot, 'DTB_SHA', hashlib.sha256(dtb).hexdigest()):
            image = android_boot.make_container(fd, dtb)
            self.assertEqual(image, android_boot.make_container(fd, dtb))
        fields = android_boot.HEADER.unpack_from(image)
        self.assertEqual(fields[0], b'ANDROID!')
        self.assertEqual(fields[3:7], (0, 0, 0, 0))
        self.assertEqual(fields[8:11], (4096, 0, 0))
        kernel = image[4096:4096 + fields[1]]
        self.assertEqual(kernel[-40:], dtb)
        self.assertEqual(gzip.decompress(kernel[:-40]), fd)
        self.assertEqual(image[4096 + fields[1]:], bytes((-fields[1]) % 4096))
        self.assertEqual(len(image) % 4096, 0)
        h = hashlib.sha1(kernel + struct.pack('<I', len(kernel)) + bytes(8))
        self.assertEqual(fields[13], h.digest() + bytes(12))
        self.assertEqual(android_boot.verify_container(image, fd, dtb)['roundtrip'], 'PASS')
        corrupt = bytearray(image)
        corrupt[-1] = 1
        with self.assertRaisesRegex(ValueError, 'padding'):
            android_boot.verify_container(corrupt, fd, dtb)

    def test_stock_hash_gate(self):
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            android_boot.check_stock(bytes(1632))


if __name__ == '__main__':
    unittest.main()
