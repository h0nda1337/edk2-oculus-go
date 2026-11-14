"""Offline one-attempt and freshness guards; never invokes a device tool.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from datetime import datetime, timezone
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import run_sec_visual_once as runner
from run_sec_visual_once import checked_file, reserve_attempt, validate_preflight, validate_review


class SecVisualOnce(unittest.TestCase):
    def test_attempt_ledger_is_exclusive_and_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='go-sec-ledger-') as temp:
            directory = Path(temp)
            path = reserve_attempt(directory, '1' * 64, {'status': 'CONSUMED'})
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                reserve_attempt(directory, '1' * 64, {'status': 'RETRY'})
            self.assertEqual(path.read_bytes(), original)

    def test_preflight_identity_and_freshness(self):
        now = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)
        report = {'result': 'PASS-READONLY', 'serial': 'TEST123', 'product': 'pacific',
                  'slot': '_a', 'root': True, 'bootCompleted': '1',
                  'partitionReadbacks': [{'name': name, 'originalMatch': True} for name
                      in ('aboot_a', 'aboot_b', 'boot_a', 'boot_b')]}
        validate_preflight(report, 'TEST123', 'readonly-preflight-20261025-173000', now)
        with self.assertRaises(ValueError):
            validate_preflight(report, 'TEST123', 'readonly-preflight-20261025-160000', now)
        with self.assertRaises(ValueError):
            validate_preflight(report, 'OTHER', 'readonly-preflight-20261025-173000', now)
        with self.assertRaises(ValueError):
            validate_preflight({**report, 'root': False}, 'TEST123',
                               'readonly-preflight-20261025-173000', now)

    def test_no_implicit_execution_clearance(self):
        with self.assertRaises(ValueError):
            validate_review(Path('.').resolve(), {'decision': 'PASS-OFFLINE'})

    def test_default_does_not_contact_device(self):
        with tempfile.TemporaryDirectory(prefix='go-sec-offline-') as temp:
            review = Path(temp) / 'review.json'
            review.write_text('{}', encoding='utf-8')
            with patch.object(sys, 'argv', ['runner', '--review', str(review)]), \
                    patch.object(runner, 'validate_review', return_value=(Path('unused'), '1' * 64)), \
                    patch.object(runner.subprocess, 'run') as native, \
                    patch.object(runner.subprocess, 'check_output') as query, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                runner.main()
                native.assert_not_called()
                query.assert_not_called()
                self.assertIn('PASS-OFFLINE-VALIDATION-ONLY', output.getvalue())

    def test_execute_requires_current_operator_before_device_calls(self):
        with tempfile.TemporaryDirectory(prefix='go-sec-no-operator-') as temp:
            review = Path(temp) / 'review.json'
            review.write_text('{}', encoding='utf-8')
            with patch.object(sys, 'argv', ['runner', '--review', str(review), '--execute']), \
                    patch.object(runner, 'validate_review', return_value=(Path('unused'), '1' * 64)), \
                    patch.object(runner.subprocess, 'run') as native:
                with self.assertRaises(SystemExit):
                    runner.main()
                native.assert_not_called()

    def test_reviewed_path_and_digest_are_required(self):
        with tempfile.TemporaryDirectory(prefix='go-sec-input-') as temp:
            root = Path(temp)
            path = root / 'local' / 'image'
            path.parent.mkdir()
            path.write_bytes(b'original')
            record = {'file': 'local/image', 'sha256': runner.sha(b'original')}
            self.assertEqual(checked_file(root, record, ('local',))[1], b'original')
            with self.assertRaises(ValueError):
                checked_file(root, record, ('build',))
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                checked_file(root, record, ('local',))


if __name__ == '__main__':
    unittest.main()
