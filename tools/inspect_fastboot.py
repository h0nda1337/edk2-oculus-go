"""Original, bounded Fastboot inspection. Never sends a payload or reboots.

Use only after the required physical-headset notification/turn boundary.
All captures remain local because bootloader replies contain identifiers.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

FASTBOOT_SHA256 = 'b2d9cbff4ce9ae7eb448cfc831bafc867935f50f5be38f8f81057fd7eb3b8d86'
QUERIES = (
    ('product', ('getvar', 'product')),
    ('slot', ('getvar', 'current-slot')),
    ('secure', ('getvar', 'secure')),
    ('device-info', ('oem', 'device-info')),
)


def require_device(listing, serial):
    if not re.fullmatch(r'[A-Za-z0-9]+', serial):
        raise ValueError('An explicit alphanumeric serial is required')
    matches = [row for line in listing.splitlines()
               if (row := line.split()) and row[0] == serial]
    if len(matches) != 1 or len(matches[0]) < 2 or matches[0][1] != 'fastboot':
        raise ValueError('Expected serial is not uniquely present in Fastboot')


def value(text, key):
    prefix = r'^[ \t]*(?:\(bootloader\)[ \t]*)?' + re.escape(key) + ':'
    fields = [line for line in text.splitlines() if re.match(prefix, line)]
    if len(fields) != 1:
        raise ValueError(f'Missing or ambiguous bootloader field: {key}')
    field = fields[0].split(':', 1)[1].strip()
    if not re.fullmatch(r'\S+', field):
        raise ValueError(f'Invalid bootloader field: {key}')
    return field


def validate_replies(replies):
    product = value(replies['product'], 'product')
    slot = value(replies['slot'], 'current-slot')
    secure = value(replies['secure'], 'secure')
    secure_boot = value(replies['device-info'], 'Secure boot')
    unlocked = value(replies['device-info'], 'Device unlocked')
    critical = value(replies['device-info'], 'Device critical unlocked')
    if (product.casefold(), slot, secure, secure_boot, unlocked, critical) != (
            'pacific', '_a', 'yes', 'true', 'true', 'false'):
        raise ValueError('Bootloader state differs from the reviewed original state')
    return {'product': product, 'slot': slot, 'secure': secure, 'secureBoot': secure_boot,
            'unlocked': unlocked, 'criticalUnlocked': critical}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fastboot', type=Path, required=True)
    parser.add_argument('--expected-serial', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9]+', args.expected_serial):
        raise SystemExit('Invalid explicit serial')
    if hashlib.sha256(args.fastboot.read_bytes()).hexdigest() != FASTBOOT_SHA256:
        raise SystemExit('Fastboot binary differs from the reviewed tool')
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    output = root / 'local' / f'fastboot-inspect-{stamp}'
    output.mkdir(parents=True, exist_ok=False)
    report = {'result': 'IN-PROGRESS', 'serial': args.expected_serial,
              'fastbootSha256': FASTBOOT_SHA256, 'commands': [],
              'firmwareSent': False, 'rebootCommandIssued': False,
              'partitionWriteCommandIssued': False}

    def capture(label, arguments):
        entry = {'label': label, 'arguments': list(arguments), 'timeoutSeconds': 10}
        report['commands'].append(entry)
        print(label, flush=True)
        try:
            result = subprocess.run(
                [str(args.fastboot), '-s', args.expected_serial, *arguments],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        except subprocess.TimeoutExpired as error:
            entry['status'] = 'TIMEOUT'
            (output / f'{label}.stdout.txt').write_bytes(error.stdout or b'')
            (output / f'{label}.stderr.txt').write_bytes(error.stderr or b'')
            raise RuntimeError(f'{label} timed out; do not retry automatically') from error
        entry['exitCode'] = result.returncode
        (output / f'{label}.stdout.txt').write_bytes(result.stdout)
        (output / f'{label}.stderr.txt').write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f'{label} failed: {result.returncode}')
        return (result.stdout + b'\n' + result.stderr).decode('utf-8', errors='replace')

    try:
        require_device(capture('devices', ('devices', '-l')), args.expected_serial)
        replies = {label: capture(label, arguments) for label, arguments in QUERIES}
        report['state'] = validate_replies(replies)
        report['result'] = 'PASS-INSPECTION-ONLY'
    except Exception as error:
        report['result'] = 'FAIL'
        report['error'] = str(error)
    finally:
        (output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n',
                                           encoding='utf-8', newline='\n')
    print(report['result'], output, flush=True)
    if report['result'] != 'PASS-INSPECTION-ONLY':
        raise SystemExit(report.get('error', 'Inspection failed'))


if __name__ == '__main__':
    main()
