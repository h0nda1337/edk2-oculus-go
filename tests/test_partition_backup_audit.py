import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_partition_backups import audit, file_format


def inventory(data, name='boot_a'):
    return json.dumps({'partitions': [{'name': name, 'size': len(data),
                                      'sha256': hashlib.sha256(data).hexdigest()}]}).encode()


class PartitionBackupAudit(unittest.TestCase):
    def test_checked_matching_backup_is_not_signature_verification(self):
        data = b'ANDROID!' + bytes(4096)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'boot_a.img').write_bytes(data)
            result = audit(folder, inventory(data))
        self.assertEqual(result['result'], 'PASS')
        self.assertEqual(result['partitions'][0]['format_hint'], 'android-boot-magic')
        self.assertFalse(result['signature_verification_performed'])
        self.assertNotIn(temporary, json.dumps(result))

    def test_missing_size_and_same_length_corruption(self):
        data = b'ANDROID!' + bytes(8)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path = folder / 'boot_a.img'
            for replacement, status in ((None, 'MISSING'), (data[:-1], 'SIZE-MISMATCH'),
                                        (data[:-1] + b'x', 'HASH-MISMATCH')):
                if replacement is not None:
                    path.write_bytes(replacement)
                result = audit(folder, inventory(data))
                self.assertEqual(result['result'], 'FAIL')
                self.assertEqual(result['partitions'][0]['status'], status)
                self.assertNotIn('format_hint', result['partitions'][0])

    def test_invalid_and_duplicate_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaises(ValueError):
                audit(folder, inventory(b'x', '../boot_a'))
            document = json.loads(inventory(b'x'))
            document['partitions'] *= 2
            with self.assertRaises(ValueError):
                audit(folder, json.dumps(document).encode())

    def test_format_hints_are_coarse(self):
        self.assertEqual(file_format(b'\x7fELF\x01\x01'), 'elf32-magic')
        self.assertEqual(file_format(b'\x7fELF\x02\x01'), 'elf64-magic')
        self.assertEqual(file_format(bytes(1080) + b'\x53\xef'), 'ext-superblock-magic-at-standard-offset')
        self.assertEqual(file_format(b'\x7fELF'), 'unclassified')


if __name__ == '__main__':
    unittest.main()
