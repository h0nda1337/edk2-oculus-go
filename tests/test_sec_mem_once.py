"""Offline tests for SEC_MEM evidence and its single attended transfer. SPDX-License-Identifier: BSD-2-Clause-Patent"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_sec_mem_once as runner


class SecMemEvidence(unittest.TestCase):
    def setUp(self):
        self.fd = 'a' * 64
        self.static = {'result': 'PASS-STATIC-SEC-MEM', 'fdSha256': self.fd, 'elfSha256': 'b' * 64,
                       'vectorSlots': 16}
        self.model = dict(self.static, result='PASS-QEMU-SEC-MEM', physicalVectorTable={'slotsVerified':16}, cases=[])
        for el in (1, 2):
            cases = ['valid-fdt', 'relocated', 'dcache', 'wrong-x0', 'bad-magic', 'short-ram', 'captured-fdt',
                     'reserved-pool', 'reserved-stack', 'undefined-instruction', 'bad-phit']
            if el == 1:
                cases.append('mmu-el1')
            for scenario in cases:
                ok = scenario in ('valid-fdt', 'captured-fdt')
                self.model['cases'].append({
                    'el': el, 'scenario': scenario, 'rejected': not ok, 'hobVerified': ok,
                    'highPoolUnchanged': True, 'fullSurfaceAndGuardsMatched': True,
                    'fdOutsideScratchUnchanged': True, 'fdtAndGuardsUnchanged': True, 'incomingRegistersRestored': True,
                    'unexpectedCpuRamWrites': 0, 'fdtSha256': runner.CAPTURED_FDT_SHA if scenario == 'captured-fdt' else '',
                    'highReadAddresses': ['0x94000000', '0x97ffffa0'] if ok else []})

    def test_accepts_complete_model_and_matching_binary(self):
        runner.validate_model(self.model, self.static, self.fd)

    def test_rejects_fd_elf_or_case_coverage_mismatch(self):
        for field in ('elfSha256', 'fdSha256'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                runner.validate_model(self.model, dict(self.static, **{field: 'c' * 64}), self.fd)
        for cases in (self.model['cases'][:-1], self.model['cases'] + self.model['cases'][:1]):
            with self.assertRaises(ValueError):
                runner.validate_model(dict(self.model, cases=cases), self.static, self.fd)

    def test_corrupted_canaries_skipped_hob_or_extra_read_fail(self):
        for index, changes in [(0, {'hobVerified': False}), (0, {'highPoolUnchanged': False}),
                               (0, {'highReadAddresses': ['0x94000000']}),
                               (1, {'fullSurfaceAndGuardsMatched': False}),
                               (1, {'fdOutsideScratchUnchanged': False}),
                               (1, {'highReadAddresses': ['0x94000000']})]:
            with self.subTest(index=index, changes=changes), self.assertRaises(ValueError):
                model = deepcopy(self.model)
                model['cases'][index].update(changes)
                runner.validate_model(model, self.static, self.fd)


class SecMemTransport(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.out = self.root / 'local/attempt'
        self.out.mkdir(parents=True)
        self.image = self.root / 'local/synthetic.img'
        self.tool = self.root / 'synthetic.exe'
        self.preflight = self.root / 'synthetic.json'
        self.commands = []
        self.flags = 'true'
        self.boot_reply = "Sending 'boot.img' (42 KB)  OKAY [0.01s]\nBooting  OKAY [0.01s]"
        self.barrier = None
        review = self.root / runner.REVIEW
        review.parent.mkdir(parents=True)
        review.write_text(json.dumps({'image': {'sha256': '0' * 64}}))

    def capture(self, tool, serial, output, report, label, args, timeout):
        self.assertEqual((tool, serial), (self.tool, 'GO123'))
        self.commands.append(tuple(args))
        if label == 'device-info' and self.barrier:
            self.barrier.wait(timeout=3)
        if label == 'temporary-boot':
            self.assertTrue((self.root / runner.LEDGER).is_file())
            self.assertEqual(args, ['boot', str(self.image)])
            self.assertIs(report['attemptConsumed'], True)
            if isinstance(self.boot_reply, Exception):
                raise self.boot_reply
            return self.boot_reply
        return {'devices': 'GO123 fastboot usb:1', 'product': 'product: pacific',
                'slot': 'current-slot: _a', 'secure': 'secure: yes',
                'device-info': ('Secure boot: ' + self.flags +
                                '\nDevice unlocked: true\nDevice critical unlocked: false')}[label]

    def measure(self):
        report = {'imageSha256': '0' * 64, 'reviewSha256': '1' * 64}
        runner.measure(self.root, self.image, self.tool, 'GO123', self.preflight, report, self.out)
        return report

    def test_default_offline_and_explicit_operator_identity(self):
        with patch.object(runner, 'ROOT', self.root), \
                patch.object(runner, 'reviewed_inputs', return_value=(self.image, 'GO123')), \
                patch.object(runner.subprocess, 'Popen') as native, \
                patch.object(sys, 'argv', ['runner']), redirect_stdout(io.StringIO()) as out:
            runner.main()
            self.assertIs(json.loads(out.getvalue())['deviceContacted'], False)
            args = ['--execute', '--fastboot', str(self.tool), '--preflight', str(self.preflight)]
            for tail in (['--expected-serial', 'GO123'], ['--operator-present', '--expected-serial', 'OTHER']):
                with patch.object(sys, 'argv', ['runner', *args, *tail]), self.assertRaises(ValueError):
                    runner.main()
            native.assert_not_called()
        self.assertFalse((self.root / runner.LEDGER).exists())

    def test_flags_and_changed_readback_stop_before_reservation(self):
        for flag, digests in [('false', ['a']), ('true', ['a', 'b'])]:
            self.flags = flag
            with patch.object(runner, 'capture', self.capture), \
                    patch.object(runner, 'check_readback', side_effect=digests), self.assertRaises(ValueError):
                self.measure()
            self.assertFalse((self.root / runner.LEDGER).exists())
            self.assertNotIn(('boot', str(self.image)), self.commands)

    def test_success_timeout_and_partial_ack_all_consume_the_attempt(self):
        for reply in (self.boot_reply, TimeoutError(), 'Booting  OKAY'):
            with self.subTest(reply=reply), TemporaryDirectory(dir=self.root) as tmp:
                # A new synthetic root is a separate fixture for each outcome.
                previous = self.root
                self.root = Path(tmp)
                self.boot_reply = reply
                self.commands.clear()
                try:
                    with patch.object(runner, 'capture', self.capture), \
                            patch.object(runner, 'check_readback', return_value='a'):
                        if isinstance(reply, TimeoutError):
                            with self.assertRaises(TimeoutError):
                                self.measure()
                        elif reply.startswith('Booting'):
                            with self.assertRaisesRegex(ValueError, 'acknowledgement'):
                                self.measure()
                        else:
                            self.assertEqual(self.measure()['result'], 'COMMAND-ACCEPTED-EXECUTION-UNKNOWN')
                        with self.assertRaisesRegex(ValueError, 'already consumed'):
                            self.measure()
                finally:
                    self.root = previous
                self.assertEqual(self.commands.count(('boot', str(self.image))), 1)

    def test_racing_sessions_send_only_once(self):
        self.barrier = threading.Barrier(2)
        with patch.object(runner, 'capture', self.capture), patch.object(runner, 'check_readback', return_value='a'), \
                ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.measure) for _ in range(2)]
            errors = [f.exception(timeout=5) for f in futures]
        self.assertEqual(errors.count(None), 1)
        self.assertTrue(any(isinstance(error, FileExistsError) for error in errors))
        self.assertEqual(self.commands.count(('boot', str(self.image))), 1)
        self.assertEqual(json.loads((self.root / runner.LEDGER).read_text())['status'], 'CONSUMED-BEFORE-SEND')


if __name__ == '__main__':
    unittest.main()
