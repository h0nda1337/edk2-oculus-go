"""The IORT output ID can differ from the PCI requester ID. Host-only fixtures."""
import struct
import unittest

from ufs_iort_qemu import pci_route


def table_for(maps):
    table = bytearray(48)
    table[:4] = b"IORT"
    struct.pack_into("<II", table, 36, 2, len(table))
    smmu_offset = len(table)
    smmu = bytearray(68)
    struct.pack_into("<BHBIII", smmu, 0, 4, len(smmu), 4, 1, 0, 0)
    table.extend(smmu)
    root = bytearray(36)
    struct.pack_into("<BHBIII", root, 0, 2, 36 + len(maps)*20, 3, 2, len(maps), 36)
    for first, span, out in maps:
        root.extend(struct.pack("<5I", first, span, out, smmu_offset, 0))
    table.extend(root)
    struct.pack_into("<I", table, 4, len(table))
    table[9] = -sum(table) & 255
    return table


class DecoderTest(unittest.TestCase):
    def test_last_id_and_nonidentity_output(self):
        table = table_for([(0x10, 8, 0x50)])
        self.assertEqual(pci_route(table, 0, 0x18)["sid"], 0x58)
        with self.assertRaisesRegex(ValueError, "unique mapping"):
            pci_route(table, 0, 0x19)

    def test_other_segment(self):
        with self.assertRaisesRegex(ValueError, "unique mapping"):
            pci_route(table_for([(0x18, 0, 0x21)]), 1, 0x18)

    def test_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "unique mapping"):
            pci_route(table_for([(0x10, 8, 0x50), (0x18, 0, 0x63)]), 0, 0x18)

    def test_checksum(self):
        table = table_for([(0, 255, 0)])
        table[9] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            pci_route(table, 0, 0x18)


if __name__ == "__main__":
    unittest.main()
