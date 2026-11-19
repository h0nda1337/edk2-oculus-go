"""Offline SEC_C transport and attempt-accounting tests. Synthetic files only."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_sec_c_once as runner


class SecCOnce(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.output = self.root / 'local/trial'
        self.output.mkdir(parents=True)
        self.report = {'temporaryBootCommandIssued': False, 'attemptConsumed': False,
                       'commands': [], 'imageSha256': 'a' * 64, 'reviewSha256': 'b' * 64}
        self.ledger = self.root / runner.LEDGER
        self.image = self.root / 'local/synthetic.img'
        self.tool = self.root / 'never-invoked.exe'
        self.preflight = self.root / 'unused'

    def measure(self):
        runner.measure(self.root, self.image, self.tool, 'TEST123', self.preflight,
                       self.report, self.output)

    def test_default_offline_does_not_start_any_subprocess_or_reserve(self):
        config = self.root / runner.REVIEW
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'image': {'sha256': 'a' * 64}}))
        with patch.object(runner, 'ROOT', self.root), patch.object(sys, 'argv', ['runner']), \
                patch.object(runner, 'reviewed_image', return_value=self.image), \
                patch.object(runner.subprocess, 'Popen') as launch, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            runner.main()
        launch.assert_not_called()
        self.assertIs(json.loads(out.getvalue())['deviceContacted'], False)
        self.assertFalse(self.ledger.exists())

    def test_consumed_single_phase_ledger_fails_before_device_queries(self):
        runner.reserve_attempt(self.root, {'case': 'previous'})
        with self.assertRaises(FileExistsError):
            runner.reserve_attempt(self.root, {'case': 'next'})
        self.assertEqual(json.loads(self.ledger.read_text()), {'case': 'previous'})
        with patch.object(runner, 'capture') as native, self.assertRaises(ValueError):
            self.measure()
        native.assert_not_called()

    def simulated_capture(self, valid_state, command_log, fail_boot=False):
        def fake(tool, serial, output, report, label, args, timeout):
            command_log.append(tuple(args))
            replies = {'devices': 'TEST123 fastboot usb:1', 'product': 'product: pacific',
                       'slot': 'current-slot: _a', 'secure': 'secure: yes', 'device-info':
                       'Secure boot: ' + ('true' if valid_state else 'false') +
                       '\nDevice unlocked: true\nDevice critical unlocked: false'}
            if label == 'temporary-boot':
                self.assertTrue(self.ledger.is_file())
                self.assertTrue(report['attemptConsumed'])
                self.assertEqual(args, ['boot', str(self.image)])
                if fail_boot:
                    raise subprocess.TimeoutExpired('synthetic', timeout)
                return 'OKAY'
            return replies[label]
        return fake

    def test_live_flags_reject_before_reservation_with_no_transfer(self):
        commands = []
        with patch.object(runner, 'check_readback', return_value='a' * 64), \
                patch.object(runner, 'capture', self.simulated_capture(False, commands)), \
                self.assertRaises(ValueError):
            self.measure()
        self.assertFalse(self.ledger.exists())
        self.assertFalse(self.report['temporaryBootCommandIssued'])
        self.assertEqual(commands, [('devices', '-l')] + [q for _, q in runner.QUERIES])

    def test_timeout_after_send_consumes_the_only_attempt(self):
        commands = []
        with patch.object(runner, 'check_readback', return_value='a' * 64), \
                patch.object(runner, 'capture', self.simulated_capture(True, commands, fail_boot=True)):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.measure()
            with self.assertRaisesRegex(ValueError, 'already been consumed'):
                self.measure()
        self.assertTrue(self.report['temporaryBootCommandIssued'])
        self.assertEqual(sum(cmd[0] == 'boot' for cmd in commands), 1)

    def test_expired_or_wrong_original_readback(self):
        stamp = datetime(2026, 11, 19, 1, tzinfo=timezone.utc)
        names = ('aboot_a', 'aboot_b', 'boot_a', 'boot_b')
        inventory = self.root / 'docs/evidence/partitions.json'
        inventory.parent.mkdir(parents=True)
        rows = [{'name': name, 'sha256': 'a' * 64, 'size': 8} for name in names]
        inventory.write_text(json.dumps({'partitions': rows}))
        path = self.root / 'local/readonly-preflight-20261119-010000/REPORT.json'
        path.parent.mkdir()
        report = {'adbSha256': runner.ADB_SHA256, 'inventorySha256': runner.sha(inventory.read_bytes()),
                  'result': 'PASS-READONLY', 'slot': '_a', 'root': True, 'product': 'pacific',
                  'serial': 'TEST123', 'bootCompleted': '1',
                  'partitionReadbacks': [dict(row, originalMatch=True) for row in rows]}
        path.write_text(json.dumps(report))
        self.assertEqual(runner.check_readback(self.root, path, 'TEST123', stamp),
                         runner.sha(path.read_bytes()))
        with self.assertRaises(ValueError):
            runner.check_readback(self.root, path, 'TEST123', stamp + timedelta(hours=2))
        report['partitionReadbacks'][0]['sha256'] = 'b' * 64
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            runner.check_readback(self.root, path, 'TEST123', stamp)

    @unittest.skipUnless(os.name == 'nt', 'native Windows read-sharing test')
    def test_locked_path_allows_second_reader_and_blocks_write_and_replace(self):
        self.image.write_bytes(b'original')
        replacement = self.image.with_suffix('.other')
        replacement.write_bytes(b'new')
        with runner.locked_input(self.image, runner.sha(b'original')):
            self.assertEqual(self.image.read_bytes(), b'original')
            with self.assertRaises(PermissionError):
                self.image.write_bytes(b'edit')
            with self.assertRaises(PermissionError):
                replacement.replace(self.image)
        replacement.replace(self.image)
        with self.assertRaises(ValueError), runner.locked_input(self.image, runner.sha(b'original')):
            self.fail('replaced image was accepted')


if __name__ == '__main__':
    unittest.main()
