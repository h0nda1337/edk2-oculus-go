"""Original, serial-scoped Android readback; never reboots or sends firmware.

Optional adb root restarts adbd only. Raw captures remain under local/ and
partition contents are hashed in host memory, not uploaded or saved as images.
Run only in a device session after the required owner-notification hold point.
PASS-READONLY does not authorize firmware execution or permanent writes.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ADB_SHA256 = '957e46b8615f7af5b7292a2ddabe98d2e61940c3fb2b0545756507f080613e71'
PARTITIONS = ('aboot_a', 'aboot_b', 'boot_a', 'boot_b')


def require_identity(listing, serial, reported_serial, product):
    if not re.fullmatch(r'[A-Za-z0-9]+', serial):
        raise ValueError('Expected serial must be explicit and alphanumeric')
    rows = [line.split() for line in listing.splitlines() if line.strip()]
    matches = [row for row in rows if row[0] == serial]
    if len(matches) != 1 or len(matches[0]) < 2 or matches[0][1] != 'device':
        raise ValueError('Expected headset is not uniquely authorized in ADB')
    if reported_serial.strip() != serial or product.strip() != 'pacific':
        raise ValueError('Headset identity/product mismatch')


def require_partition(record, resolved, sectors):
    if record['name'] not in PARTITIONS:
        raise ValueError('Partition is not in the four-item readback allowlist')
    if not re.fullmatch(r'/dev/block/sd[a-f][0-9]+', resolved):
        raise ValueError('Unexpected resolved block node')
    if resolved != record['blockDevice'] or int(sectors) * 512 != record['size']:
        raise ValueError('Current block mapping/size differs from original inventory')
    if not 0 < record['size'] <= 67108864:
        raise ValueError('Partition exceeds bounded readback size')


def verify_payload(data, record):
    if len(data) != record['size']:
        raise ValueError(f'Incomplete partition read: {len(data)} / {record["size"]}')
    actual = hashlib.sha256(data).hexdigest()
    if actual != record['sha256']:
        raise ValueError('Complete partition hash differs from original backup')
    return {'name': record['name'], 'size': len(data), 'sha256': actual, 'originalMatch': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--expected-serial', required=True)
    parser.add_argument('--request-root', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9]+', args.expected_serial):
        raise SystemExit('Invalid explicit serial')
    if hashlib.sha256(args.adb.read_bytes()).hexdigest() != ADB_SHA256:
        raise SystemExit('ADB binary differs from the previously verified tool')
    root = Path(__file__).resolve().parents[1]
    inventory_path = root / 'docs/evidence/partitions.json'
    inventory = json.loads(inventory_path.read_text())
    originals = {row['name']: row for row in inventory['partitions']}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    output = root / 'local' / f'readonly-preflight-{stamp}'
    output.mkdir(parents=True, exist_ok=False)
    report = {'result': 'IN-PROGRESS', 'serial': args.expected_serial,
        'adbSha256': ADB_SHA256,
        'inventorySha256': hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
        'commands': [], 'partitionReadbacks': [], 'rootRestartRequested': False,
        'headsetRebootCommandIssued': False, 'firmwareSent': False,
        'partitionWriteCommandIssued': False, 'physicalRecoveryRevalidated': False}

    def capture(label, arguments, timeout=15, partition=False):
        # All callers use literal command lists; there is no arbitrary shell mode.
        command = [str(args.adb), '-s', args.expected_serial, *arguments]
        print(label, flush=True)
        entry = {'label': label, 'arguments': arguments, 'timeoutSeconds': timeout}
        report['commands'].append(entry)
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            entry.update({'status': 'TIMEOUT', 'bytesReceived': len(error.stdout or b'')})
            raise RuntimeError(f'{label} timed out; no complete hash available') from error
        entry.update({'exitCode': result.returncode, 'bytesReceived': len(result.stdout)})
        (output / f'{label}.stderr.txt').write_bytes(result.stderr)
        if not partition:
            (output / f'{label}.txt').write_bytes(result.stdout)
        if result.returncode:
            raise RuntimeError(f'{label} failed: {result.returncode}')
        return result.stdout if partition else result.stdout.decode('utf-8', errors='replace').strip()

    try:
        listing = capture('01-devices', ['devices', '-l'])
        # Select exactly the known serial before any device-shell command.
        rows = [line.split() for line in listing.splitlines() if line.strip()]
        if not any(len(row) >= 2 and row[:2] == [args.expected_serial, 'device'] for row in rows):
            raise RuntimeError('Expected authorized ADB device is absent')
        serial = capture('02-serial', ['shell', 'getprop', 'ro.serialno'])
        product = capture('03-product', ['shell', 'getprop', 'ro.product.device'])
        require_identity(listing, args.expected_serial, serial, product)
        report['product'] = product
        identity = capture('04-id', ['shell', 'id'])
        if not identity.startswith('uid=0('):
            if not args.request_root:
                raise RuntimeError('ADB is not root; rerun with --request-root for authorized readback')
            report['rootRestartRequested'] = True
            capture('05-adb-root', ['root'])
            capture('06-wait-adb', ['wait-for-device'])
            identity = capture('07-root-id', ['shell', 'id'])
        if not identity.startswith('uid=0('):
            raise RuntimeError('Root was not obtained; partition reads aborted')
        report['root'] = True
        report['slot'] = capture('08-slot', ['shell', 'getprop', 'ro.boot.slot_suffix'])
        report['bootCompleted'] = capture('09-boot-completed', ['shell', 'getprop', 'sys.boot_completed'])
        if report['slot'] not in ('_a', '_b') or report['bootCompleted'] != '1':
            raise RuntimeError('Unexpected Android boot/slot state')
        battery = capture('10-battery', ['shell', 'dumpsys', 'battery'])
        report['batteryText'] = battery
        for label, path in (
            ('11-soc-machine', '/sys/devices/soc0/machine'),
            ('12-soc-id', '/sys/devices/soc0/soc_id'),
            ('13-soc-revision', '/sys/devices/soc0/revision'),
            ('14-cmdline', '/proc/cmdline'),
            ('15-iomem', '/proc/iomem')):
            capture(label, ['shell', 'cat', path])
        capture('16-uname', ['shell', 'uname', '-a'])
        capture('17-by-name', ['shell', 'ls', '-al', '/dev/block/bootdevice/by-name'])
        for name in PARTITIONS:
            record = originals[name]
            resolved = capture(f'{name}-node', ['shell', 'readlink', '-f',
                f'/dev/block/bootdevice/by-name/{name}'])
            if resolved != record['blockDevice'] or not re.fullmatch(r'/dev/block/sd[a-f][0-9]+', resolved):
                raise RuntimeError(f'{name}: unexpected by-name mapping')
            block = resolved.rsplit('/', 1)[-1]
            sectors = capture(f'{name}-sectors', ['shell', 'cat', f'/sys/class/block/{block}/size'])
            require_partition(record, resolved, sectors)
            payload = capture(f'{name}-readback', ['exec-out', 'cat', resolved],
                              timeout=60, partition=True)
            report['partitionReadbacks'].append(verify_payload(payload, record))
            del payload
        report['result'] = 'PASS-READONLY'
    except Exception as error:
        report['result'] = 'FAIL'
        report['error'] = str(error)
    finally:
        (output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n',
                                           encoding='utf-8', newline='\n')
    print(report['result'], output, flush=True)
    if report['result'] != 'PASS-READONLY':
        raise SystemExit(report.get('error', 'Preflight failed'))


if __name__ == '__main__':
    main()
