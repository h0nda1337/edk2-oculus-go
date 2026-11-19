"""Regression checks for the debugger locator and core-image evidence."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from run_dxe_debug_once import validate_reports


class DebugImageReview(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((ROOT/'docs/evidence/dxe-debug-qemu-20261119.json').read_bytes())
        self.static = {**self.model, 'result':'PASS-STATIC-DXE-DEBUG'}
        self.valid = next(r for r in self.model['cases'] if r['case'] == 'valid')

    def validate(self):
        validate_reports(self.model, self.static, self.model['fdSha256'])

    def test_complete(self):
        self.validate()

    def test_shared_free_or_overallocated_memory(self):
        for key, value in [('pages',1025),('type','EfiConventionalMemory'),('base','0x80401000')]:
            with self.subTest(key=key):
                old = self.valid['allocation'][key]
                self.valid['allocation'][key] = value
                with self.assertRaises(ValueError):
                    self.validate()
                self.valid['allocation'][key] = old

    def test_locator_checksum_covers_full_structure(self):
        self.valid['debugLocator']['crc32'] = '00000000'
        with self.assertRaises(ValueError):
            self.validate()

    def test_image_record_must_match_registered_handle(self):
        self.valid['debugImage']['handle'] = '0x0'
        with self.assertRaises(ValueError):
            self.validate()

    def test_update_must_have_finished(self):
        self.valid['debugImage']['updateStatus'] |= 1
        with self.assertRaises(ValueError):
            self.validate()

    def test_oversize_control_must_reproduce_resource_shortage(self):
        next(r for r in self.model['cases'] if r['case']=='oversize')['oversizeRequest']['status'] = 'EFI_SUCCESS'
        with self.assertRaises(ValueError):
            self.validate()
