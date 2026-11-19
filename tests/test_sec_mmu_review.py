"""Offline release checks for SEC_MMU. SPDX-License-Identifier: BSD-2-Clause-Patent"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from run_sec_mmu_once import validate_reports


class MmuReview(unittest.TestCase):
    def setUp(self):
        self.digest = 'a' * 64
        self.static = dict(result='PASS-STATIC-SEC-MMU', fdSha256=self.digest, elfSha256='b'*64,
                           reachableInstructions=342, checkedActivationLevels=[1,2])
        self.model = dict(result='PASS-QEMU-SEC-MMU', fdSha256=self.digest, elfSha256='b'*64,
                          vectors={'slotsVerified':16}, cases=[])
        scenarios = {'sealed': ['valid','icache'], 'color':['color-corruption'],
                     'mono':['wrong-attribute','last-page-absent','mapped-guard','wrong-output',
                             'mono-corruption','instruction-fault'],
                     'untouched':['dcache','wrong-x0','relocated','dirty-tables','dirty-stack']}
        for el in (1,2):
            for pattern, cases in scenarios.items():
                for name in cases + (['mmu-el1'] if el == 1 and pattern == 'untouched' else []):
                    terminal = 'MmuComplete' if pattern == 'sealed' else 'MmuRejected'
                    self.model['cases'].append(dict(el=el, case=name, lastPattern=pattern,
                        terminal='MmuException' if name == 'instruction-fault' else terminal,
                        translatedSctlr='0x1001' if name == 'icache' else '0x1',
                        unexpectedGuestRamWrites=0, highPoolAccesses=0, fullScreenAndGuardsMatched=True))

    def test_complete(self):
        validate_reports(self.model,self.static,self.digest)

    def test_missing_or_duplicate_case(self):
        rows = self.model['cases']
        for cases in (rows[1:], rows+[rows[0]]):
            with self.assertRaises(ValueError):
                validate_reports(dict(self.model,cases=cases),self.static,self.digest)

    def test_translated_frame_cannot_pass_with_wrong_state(self):
        for change in ({'translatedSctlr':'0x0'},{'translatedSctlr':'0x5'},{'lastPattern':'mono'},
                       {'fullScreenAndGuardsMatched':False},{'highPoolAccesses':1},{'unexpectedGuestRamWrites':1}):
            model = deepcopy(self.model)
            model['cases'][0].update(change)
            with self.assertRaises(ValueError):
                validate_reports(model,self.static,self.digest)
        with self.assertRaises(ValueError):
            validate_reports(self.model,dict(self.static,elfSha256='c'*64),self.digest)
