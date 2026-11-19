"""Validate the fixed SEC_C experiment offline or run it once on attended Windows.

The command never transitions the headset into Fastboot. Physical execution
requires the owner's current presence and the project's prior notification.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import zlib

from android_boot import DTB_SHA, HEADER, PAGE, verify_container
from collect_readonly_preflight import ADB_SHA256
from inspect_fastboot import FASTBOOT_SHA256, QUERIES, require_device, validate_replies
from run_sec_visual_once import checked_file, sha, validate_preflight
from verify_fd import verify


ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/sec-c-review-20261118.json'
LEDGER = 'local/physical-attempts/sec-c-20261118.json'
REQUIRED_SOURCES = {
    'OculusGoPkg/PrePi/Entry.S', 'OculusGoPkg/PrePi/SecMain.c', 'OculusGoPkg/OculusGoPkg.dsc',
    'scripts/build.sh', 'tests/entry_harness.S', 'tests/sec_c_qemu.py', 'tests/sec_c_prefix.py',
    'tools/run_sec_c_once.py', 'tools/run_sec_visual_once.py', 'tools/inspect_fastboot.py',
    'tools/android_boot.py', 'tools/verify_fd.py',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reviewed_image(root, review):
    require(review['decision'] == 'APPROVED-FOR-ONE-TERMINAL-SEC-C-MEASUREMENT'
            and review['scope'] == 'terminal-edk2-sec-c' and type(review['maxAttempts']) is int
            and review['maxAttempts'] == 1, 'No one-attempt approval for terminal SEC_C')
    fd_path, fd = checked_file(root, review['fd'], ('build',))
    image_path, image = checked_file(root, review['image'], ('local',))
    require(len(fd) == review['fd']['size'] and len(image) == review['image']['size'],
            'Unexpected firmware or container size')
    require(verify(fd)['secEntryAddress'] == '0x80088000' and fd[64:PAGE] == b'\xff' * (PAGE - 64),
            'Unexpected entry or occupied header padding')
    kernel_size = HEADER.unpack_from(image)[1]
    decoder = zlib.decompressobj(31)
    expanded = decoder.decompress(image[PAGE:PAGE + kernel_size], len(fd) + 1)
    require(decoder.eof and expanded == fd and sha(decoder.unused_data) == DTB_SHA,
            'Image FD or original EVT DTB mismatch')
    verify_container(image, fd, decoder.unused_data)
    for label, expected in (('model', 'PASS-QEMU-SEC-C'), ('prefixAudit', 'PASS-STATIC-SEC-C')):
        _, evidence = checked_file(root, review[label], ('build',))
        result = json.loads(evidence)
        require(result['result'] == expected and result['fdSha256'] == review['fd']['sha256'],
                f'{label} does not cover this SEC_C firmware')
        if label == 'model':
            require(all(row['fullSurfaceAndGuardsMatched'] is True
                        and row['incomingRegistersRestored'] is True for row in result['cases']),
                    'An SEC_C emulator case failed its memory or register checks')
            observed = {(row['el'], row['relocated'], row['dataCacheEnabled'], row['rejected'])
                        for row in result['cases']}
            expected_cases = {(el, reloc, cache, reloc or cache) for el in (1, 2)
                              for reloc, cache in ((False, False), (True, False), (False, True))}
            require(expected_cases <= observed, 'Missing SEC_C model coverage')
    audit_path, evidence = checked_file(root, review['sourceAudit'], ('build',))
    require(fd_path.parent.name.startswith('DEBUG-SEC_C-')
            and audit_path == fd_path.parent / 'SOURCES.json', 'Source audit is from a different build')
    audit = json.loads(evidence)
    lock = json.loads((root / 'sources.lock.json').read_bytes())
    require(audit['result'] == 'PASS' and audit['rejected'] == [] and audit['upstreamTreeClean'] is True
            and audit['upstreamInputsTracked'] is True and audit['edk2'] == lock['edk2'],
            'Source audit or upstream EDK2 identity mismatch')
    originals = [row for row in audit['files'] if row['origin'] == 'original-project']
    require({'OculusGoPkg/PrePi/Entry.S', 'OculusGoPkg/PrePi/SecMain.c'} <=
            {row['file'] for row in originals}, 'SEC sources missing from build audit')
    for row in originals:
        checked_file(root, row, ('OculusGoPkg',))
    sources = review['checkedSourceFiles']
    require(REQUIRED_SOURCES <= {row['file'] for row in sources}, 'Incomplete reviewed source set')
    for row in sources:
        checked_file(root, row, ('OculusGoPkg', 'scripts', 'tools', 'tests'))
    return image_path


def check_readback(root, path, serial, now):
    path = path.resolve(strict=True)
    require(path.name == 'REPORT.json' and path.parent.parent == root / 'local',
            'Expected a local Android preflight report')
    data = path.read_bytes()
    report = json.loads(data)
    validate_preflight(report, serial, path.parent.name, now)
    inventory = (root / 'docs/evidence/partitions.json').read_bytes()
    require(report['adbSha256'] == ADB_SHA256 and report['inventorySha256'] == sha(inventory),
            'Preflight tools or baseline differ')
    originals = {row['name']: row for row in json.loads(inventory)['partitions']}
    for row in report['partitionReadbacks']:
        original = originals[row['name']]
        require((row['size'], row['sha256']) == (original['size'], original['sha256']),
                'Live Android readback differs from the preserved original')
    return sha(data)


@contextmanager
def locked_input(path, digest):
    """Prevent replacement/writes while Fastboot reopens a verified Windows file."""
    if os.name != 'nt':
        raise RuntimeError('Live mode requires native Windows read-sharing locks')
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    open_file = kernel.CreateFileW
    open_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                          wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_file.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL.
    handle = open_file(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        require(sha(path.read_bytes()) == digest, 'Locked file differs from reviewed hash')
        yield
    finally:
        close(handle)


def capture(fastboot, serial, output, report, label, args, timeout):
    entry = {'label': label, 'timeoutSeconds': timeout}
    report['commands'].append(entry)
    command = [str(fastboot), '-s', serial, *args]
    print(label, flush=True)
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        entry['status'] = 'TIMEOUT'
        (output / f'{label}.stdout.txt').write_bytes(error.stdout or b'')
        (output / f'{label}.stderr.txt').write_bytes(error.stderr or b'')
        raise RuntimeError(f'{label} timed out; the visor may still be running') from error
    (output / f'{label}.stdout.txt').write_bytes(result.stdout)
    (output / f'{label}.stderr.txt').write_bytes(result.stderr)
    entry['exitCode'] = result.returncode
    require(result.returncode == 0, f'{label} failed with native status {result.returncode}')
    return (result.stdout + b'\n' + result.stderr).decode('utf-8', errors='replace')


def reserve_attempt(root, record):
    ledger = root / LEDGER
    ledger.parent.mkdir(exist_ok=True, parents=True)
    with ledger.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def measure(root, image, fastboot, serial, preflight, report, output):
    require(not (root / LEDGER).exists(), 'This SEC_C attempt has already been consumed')
    readback = check_readback(root, preflight, serial, datetime.now(timezone.utc))
    report['preflightSha256'] = readback
    require_device(capture(fastboot, serial, output, report, 'devices', ['devices', '-l'], 10), serial)
    replies = {key: capture(fastboot, serial, output, report, key, args, 10)
               for key, args in QUERIES}
    report['bootloader'] = validate_replies(replies)
    require(check_readback(root, preflight, serial, datetime.now(timezone.utc)) == readback,
            'Android evidence changed before send')
    reserve_attempt(root, {'status': 'CONSUMED-BEFORE-SEND', 'imageSha256': report['imageSha256'],
                           'reviewSha256': report['reviewSha256'], 'logDirectory': output.name,
                           'reservedUtc': datetime.now(timezone.utc).isoformat()})
    report['attemptConsumed'] = True
    report['temporaryBootCommandIssued'] = True
    capture(fastboot, serial, output, report, 'temporary-boot', ['boot', str(image)], 20)
    report['result'] = 'COMMAND-ACCEPTED-EXECUTION-UNKNOWN'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--operator-present', action='store_true')
    parser.add_argument('--fastboot', type=Path)
    parser.add_argument('--expected-serial')
    parser.add_argument('--preflight', type=Path)
    args = parser.parse_args()
    review_bytes = (ROOT / REVIEW).read_bytes()
    review = json.loads(review_bytes)
    image = reviewed_image(ROOT, review)
    if not args.execute:
        print(json.dumps({'result': 'PASS-OFFLINE-ONLY', 'imageSha256': review['image']['sha256'],
                          'deviceContacted': False, 'ledgerAlreadyPresent': (ROOT / LEDGER).exists()}))
        return
    require(args.operator_present and args.fastboot and args.preflight
            and re.fullmatch('[A-Za-z0-9]+', args.expected_serial or ''),
            'Live mode requires a present operator, explicit serial, pinned tool and fresh readback')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip(),
            'Working tree must be clean')
    require(subprocess.check_output(['git', 'show', 'HEAD:' + REVIEW], cwd=ROOT) == review_bytes,
            'Review must match the committed record')
    tool = args.fastboot.resolve(strict=True)
    out = ROOT / 'local' / ('sec-c-once-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    out.mkdir()
    report = {'result': 'IN-PROGRESS', 'reviewSha256': sha(review_bytes),
              'imageSha256': review['image']['sha256'], 'fdSha256': review['fd']['sha256'],
              'commands': [], 'attemptConsumed': False, 'temporaryBootCommandIssued': False,
              'physicalSecCExecution': 'UNKNOWN', 'partitionWriteCommandIssued': False}
    try:
        with locked_input(image, report['imageSha256']), locked_input(tool, FASTBOOT_SHA256):
            measure(ROOT, image, tool, args.expected_serial, args.preflight, report, out)
    except Exception as error:
        report['result'] = 'FAIL'
        report['error'] = str(error)
        raise
    finally:
        (out / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(report['result'], out)


if __name__ == '__main__':
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
