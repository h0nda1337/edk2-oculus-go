"""Offline release gates for the guarded stack image. SPDX-License-Identifier: BSD-2-Clause-Patent"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from run_sec_stack_once import EXPECTED, validate_reports


class StackReview(unittest.TestCase):
    def setUp(self):
        self.fd = 'a'*64
        self.static = {'result':'PASS-STATIC-SEC-STACK', 'fdSha256':self.fd,
                       'elfSha256':'b'*64, 'reachableInstructions':290}
        self.model = dict(self.static, result='PASS-QEMU-SEC-STACK', stackRange=['0x8043f000','0x8047f000'],
                          bytesPerPattern=262144, vectors={'slotsVerified':16}, cases=[])
        for el in (1,2):
            outcomes = dict(EXPECTED)
            if el == 1:
                outcomes['mmu-el1'] = 'StackEntryRejected'
            for name, terminal in outcomes.items():
                self.model['cases'].append({'el':el, 'scenario':name, 'terminal':terminal, 'screenMatched':True,
                                            'fdOutsideFootprintMatched':True, 'unexpectedGuestRamWrites':0,
                                            'normalPoolAccesses':0, 'stackPointersAtCallEntries':[
                                            '0x8047efa0','0x8047eb80','0x8047e760','0x8047e340','0x8047df10']})

    def test_complete_model(self):
        validate_reports(self.model, self.static, self.fd)

    def test_missing_repeated_or_unexpected_outcome(self):
        rows = self.model['cases']
        for cases in (rows[:-1], rows + rows[:1], [dict(rows[0], terminal='StackFrameRejected'), *rows[1:]]):
            with self.assertRaises(ValueError):
                validate_reports(dict(self.model, cases=cases), self.static, self.fd)

    def test_footprint_frames_and_firmware_identity(self):
        for change in ({'unexpectedGuestRamWrites':1}, {'normalPoolAccesses':1},
                       {'screenMatched':False}, {'stackPointersAtCallEntries':[]}):
            model = deepcopy(self.model)
            model['cases'][0].update(change)
            with self.assertRaises(ValueError):
                validate_reports(model, self.static, self.fd)
        with self.assertRaises(ValueError):
            validate_reports(self.model, dict(self.static, elfSha256='c'*64), self.fd)
