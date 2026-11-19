"""Regression checks for evidence distinguishing discovery, load and execution."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from run_dxe_dispatch_once import validate_reports


class DispatchReview(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((ROOT/'docs/evidence/dxe-dispatch-qemu-20261119.json').read_bytes())
        self.static = {**self.model,'result':'PASS-STATIC-DXE-DISPATCH'}

    def validate(self):
        validate_reports(self.model,self.static,self.model['fdSha256'])

    def test_reviewed_model(self):
        self.validate()

    def test_registered_protocol_must_answer(self):
        row = next(c for c in self.model['cases'] if c['case']=='valid')
        row['getDevicePathSize'] = 3
        with self.assertRaises(ValueError):
            self.validate()

    def test_unsatisfied_dependency_prevents_loading(self):
        row = next(c for c in self.model['cases'] if c['case']=='false-depex')
        row['loadStatus'] = 'EFI_SUCCESS'
        with self.assertRaises(ValueError):
            self.validate()

    def test_rejected_file_must_never_start(self):
        row = next(c for c in self.model['cases'] if c['case']=='wrong-file-guid')
        row['startStatus'] = 'EFI_SUCCESS'
        with self.assertRaises(ValueError):
            self.validate()

    def test_protocol_method_must_be_in_driver_text(self):
        self.model['driverSymbols']['GetDevicePathSize'] = 0
        with self.assertRaises(ValueError):
            self.validate()
