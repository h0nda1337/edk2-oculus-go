"""Regression checks for early DXE constructor and table evidence."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from run_dxe_tables_once import DXE, HOB, validate_reports


class TablesReview(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((ROOT/'docs/evidence/dxe-tables-qemu-20261119.json').read_bytes())
        self.static = {**self.model, 'result':'PASS-STATIC-DXE-TABLES'}
        self.valid = next(r for r in self.model['cases'] if r['case'] == 'valid')

    def validate(self):
        validate_reports(self.model, self.static, self.model['fdSha256'])

    def test_complete_model(self):
        self.validate()

    def test_each_constructor_must_return_success(self):
        statuses = self.valid['constructorStatuses']
        statuses[next(iter(statuses))] = 1
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_constructor(self):
        self.valid['constructorStatuses'].pop('UefiLibConstructor')
        with self.assertRaises(ValueError):
            self.validate()

    def test_original_hobs_cannot_substitute_for_migrated_list(self):
        self.valid['installedByGuid'][HOB] = '0x80200000'
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_dxe_guid(self):
        self.valid['installedByGuid'].pop(DXE)
        with self.assertRaises(ValueError):
            self.validate()

    def test_query_must_go_through_published_services(self):
        self.valid['queryThroughPublishedServices'] = False
        with self.assertRaises(ValueError):
            self.validate()

    def test_reordered_control_required_at_both_exception_levels(self):
        self.model['cases'].remove(next(r for r in self.model['cases'] if r['case'] == 'table-order'))
        with self.assertRaises(ValueError):
            self.validate()
