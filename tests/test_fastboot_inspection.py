"""Offline parser checks; no subprocess or device access.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from inspect_fastboot import QUERIES, require_device, validate_replies, value


class FastbootInspection(unittest.TestCase):
    def test_unique_serial_required(self):
        require_device('TEST123 fastboot usb:1-2', 'TEST123')
        for listing in ('', 'OTHER fastboot', 'TEST123 device',
                        'TEST123 fastboot\nTEST123 fastboot'):
            with self.assertRaises(ValueError):
                require_device(listing, 'TEST123')

    def test_unambiguous_fields(self):
        self.assertEqual(value('(bootloader) product: pacific\r\n', 'product'), 'pacific')
        for text in ('', 'product: pacific\nproduct: other', 'xproduct: pacific'):
            with self.assertRaises(ValueError):
                value(text, 'product')

    def test_reviewed_state_required(self):
        replies = {'product': 'product: pacific\n', 'slot': 'current-slot: _a\n',
                   'secure': 'secure: yes\n',
                   'device-info': '(bootloader) Device unlocked: true\n'
                                  '(bootloader) Device critical unlocked: false\n'}
        self.assertEqual(validate_replies(replies)['slot'], '_a')
        for key, changed in (('slot', 'current-slot: _b'), ('secure', 'secure: no'),
                             ('product', 'product: other'),
                             ('device-info', 'Device unlocked: false\n'
                                             'Device critical unlocked: false\n')):
            with self.assertRaises(ValueError):
                validate_replies({**replies, key: changed})

    def test_fixed_read_only_queries(self):
        self.assertEqual(tuple(args for _, args in QUERIES), (
            ('getvar', 'product'), ('getvar', 'current-slot'),
            ('getvar', 'secure'), ('oem', 'device-info')))


if __name__ == '__main__':
    unittest.main()
