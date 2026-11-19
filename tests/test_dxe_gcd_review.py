"""Host regression checks for the DXE_GCD observer evidence."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from run_dxe_gcd_once import validate_reports


class GcdReview(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((ROOT/'docs/evidence/dxe-gcd-qemu-20261119.json').read_bytes())
        self.static = {**self.model, 'result':'PASS-STATIC-DXE-GCD'}
        self.valid = next(r for r in self.model['cases'] if r['case'] == 'valid')

    def validate(self):
        validate_reports(self.model, self.static, self.model['fdSha256'])

    def test_complete_model(self):
        self.validate()

    def test_original_hob_pointer_is_rejected(self):
        self.valid['relocatedHobs'] = '0x80200000'
        with self.assertRaises(ValueError):
            self.validate()

    def test_image_size_must_match_pe(self):
        self.valid['loadedImageBytes'] += 1
        with self.assertRaises(ValueError):
            self.validate()

    def test_unreported_memory_is_rejected(self):
        self.valid['gcdRanges'][0][2] = 2
        with self.assertRaises(ValueError):
            self.validate()

    def test_guid_page_cannot_be_free(self):
        self.valid['originalHobPageType'] = 'EfiConventionalMemory'
        with self.assertRaises(ValueError):
            self.validate()

    def test_stack_requires_reserved_memory(self):
        stack = next(r for r in self.valid['gcdRanges'] if r[2] == 1)
        stack[2] = 0
        with self.assertRaises(ValueError):
            self.validate()

    def test_control_cannot_finish(self):
        row = next(r for r in self.model['cases'] if r['case'] == 'gcd-owner')
        row['terminal'] = 'TrialGcdComplete'
        with self.assertRaises(ValueError):
            self.validate()
