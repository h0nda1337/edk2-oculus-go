"""Offline identity, partition-scope and complete-read checks. No ADB calls.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from collect_readonly_preflight import require_identity, require_partition, verify_payload


class ReadbackGuards(unittest.TestCase):
    def test_exact_identity(self):
        require_identity('List of devices attached\nTEST123 device product:vr_pacific',
                         'TEST123', 'TEST123', 'pacific')
        with self.assertRaises(ValueError):
            require_identity('OTHER device', 'TEST123', 'OTHER', 'pacific')
        with self.assertRaises(ValueError):
            require_identity('TEST123 unauthorized', 'TEST123', 'TEST123', 'pacific')
        with self.assertRaises(ValueError):
            require_identity('TEST123 device', 'TEST123', 'TEST123', 'other')

    def test_block_and_size_must_match_inventory(self):
        original = {'name': 'boot_a', 'blockDevice': '/dev/block/sde18', 'size': 512}
        require_partition(original, '/dev/block/sde18', '1')
        with self.assertRaises(ValueError):
            require_partition(original, '/dev/block/sde19', '1')
        with self.assertRaises(ValueError):
            require_partition(original, '/dev/block/sde18', '2')
        with self.assertRaises(ValueError):
            require_partition({**original, 'name': 'userdata'}, '/dev/block/sde18', '1')

    def test_full_length_and_hash_are_required(self):
        data = b'original'
        record = {'name': 'boot_a', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        self.assertTrue(verify_payload(data, record)['originalMatch'])
        with self.assertRaises(ValueError):
            verify_payload(data[:-1], record)
        with self.assertRaises(ValueError):
            verify_payload(b'changed!', record)


if __name__ == '__main__':
    unittest.main()
