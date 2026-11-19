"""Regression checks for the DXE_MEM attended evidence gate. Host-only."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from run_dxe_mem_once import validate_reports


class MemoryReview(unittest.TestCase):
    def setUp(self):
        self.model=json.loads((ROOT/'docs/evidence/dxe-mem-qemu-20261119.json').read_bytes())
        self.static={**self.model,'result':'PASS-STATIC-DXE-MEM'}
        self.digest=self.model['fdSha256']

    def check(self):
        validate_reports(self.model,self.static,self.digest)

    def test_complete_model(self):
        self.check()

    def test_one_exception_level_is_insufficient(self):
        self.model['cases']=[row for row in self.model['cases'] if row['el']==1]
        with self.assertRaises(ValueError):
            self.check()

    def test_success_requires_distinct_map_keys(self):
        valid=next(row for row in self.model['cases'] if row['case']=='valid')
        valid['mapKeys']=[5,5]
        with self.assertRaises(ValueError):
            self.check()

    def test_overlapping_page_and_pool_fail(self):
        valid=next(row for row in self.model['cases'] if row['case']=='valid')
        valid['pool']=valid['pages']
        with self.assertRaises(ValueError):
            self.check()

    def test_corrupt_map_cannot_claim_success(self):
        row=next(row for row in self.model['cases'] if row['case']=='map-type')
        row['terminal']='TrialMemoryComplete'
        with self.assertRaises(ValueError):
            self.check()

    def test_mixed_core_hashes_fail(self):
        self.static['peSha256']='0'*64
        with self.assertRaises(ValueError):
            self.check()
