"""Offline specification and identity guards, no device access.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from verify_sec_visual_data import (BAND_BYTES, FB_BASE, SURFACE_BYTES,
                                    band_ranges, expected_band, verify_data)


class SecVisualData(unittest.TestCase):
    def test_pattern_and_footprint(self):
        band = expected_band()
        self.assertEqual(len(band), BAND_BYTES)
        row = band[:4320]
        self.assertEqual(row[:1080], bytes([255]) * 1080)
        self.assertEqual(row[1080:2160], bytes(1080))
        self.assertEqual(row[2160:3240], b'\x00\xff\x00' * 360)
        self.assertEqual(row[3240:], b'\xff\x00\xff' * 360)
        self.assertEqual(band, row * 32)
        ranges = band_ranges()
        self.assertEqual(sum(end - start for start, end in ranges), 276480)
        self.assertLess(ranges[0][1], ranges[1][0])
        for start, end in ranges:
            self.assertGreaterEqual(start, FB_BASE)
            self.assertLessEqual(end, FB_BASE + SURFACE_BYTES)

    def test_wrong_capture_rejected(self):
        with self.assertRaises(ValueError):
            verify_data(bytes(1048576), b'not the preserved DT')


if __name__ == '__main__':
    unittest.main()
