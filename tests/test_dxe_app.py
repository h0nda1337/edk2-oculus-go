"""Regressions for FV application identity, caller attribution and cleanup."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from run_dxe_app_once import validate_reports


class AppReview(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((ROOT/'docs/evidence/dxe-app-qemu-20261120.json').read_bytes())
        self.static = {**self.model, 'result':'PASS-STATIC-DXE-APP'}
        self.row = next(r for r in self.model['cases'] if r['case']=='valid')

    def validate(self):
        validate_reports(self.model,self.static,self.model['fdSha256'])

    def test_record(self):
        self.validate()

    def test_output_from_core(self):
        self.row['appOutputCaller'] = self.row['dxeMain']
        with self.assertRaises(ValueError):
            self.validate()

    def test_wrong_file(self):
        self.row['appFvPeSha256'] = 'f'*64
        with self.assertRaises(ValueError):
            self.validate()

    def test_stale_executable_pages(self):
        self.row['appCodeRestoredToRwXn'] = False
        with self.assertRaises(ValueError):
            self.validate()

    def test_error_discarded(self):
        row = next(r for r in self.model['cases'] if r['case']=='app-output-error')
        row['appStartStatus'] = 0
        with self.assertRaises(ValueError):
            self.validate()
