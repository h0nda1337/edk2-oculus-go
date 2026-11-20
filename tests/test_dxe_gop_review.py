"""Require second-image dispatch, actual BGR pixels and controlled error exits."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from run_dxe_gop_once import validate_reports


class GopReview(unittest.TestCase):
    def setUp(self):
        self.model=json.loads((ROOT/'docs/evidence/dxe-gop-qemu-20261119.json').read_bytes())
        self.static={**self.model,'result':'PASS-STATIC-DXE-GOP'}

    def row(self,case):
        return next(c for c in self.model['cases'] if c['case']==case)

    def validate(self):
        validate_reports(self.model,self.static,self.model['fdSha256'])

    def test_reviewed_result(self):
        self.validate()

    def test_swapped_red_and_blue(self):
        self.row('valid')['rawBgrRow'][0]='0000ff'
        with self.assertRaises(ValueError):
            self.validate()

    def test_separate_driver(self):
        row=self.row('valid')
        row['gopHandle']=row['driverHandle']
        with self.assertRaises(ValueError):
            self.validate()

    def test_early_gop(self):
        self.row('gop-depex')['gopImageBase']='0x80200000'
        with self.assertRaises(ValueError):
            self.validate()

    def test_partial_drawing(self):
        self.row('valid')['bltCalls']=23
        with self.assertRaises(ValueError):
            self.validate()
