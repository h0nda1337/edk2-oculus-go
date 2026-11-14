"""One reviewed terminal SEC measurement; default is offline validation only.

This never clears or sends the full normal firmware. No flashing/reboot/slot
commands and no automatic retry. An execution attempt consumes a new FD-keyed
local ledger before sending, even if the host command fails or times out.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zlib

from android_boot import DTB_SHA, HEADER, PAGE, verify_container
from inspect_fastboot import FASTBOOT_SHA256, QUERIES, require_device, validate_replies
from verify_fd import verify


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(root, record, folders):
    path = (root / record['file']).resolve()
    if not any(path.is_relative_to(root / folder) for folder in folders):
        raise ValueError('Reviewed input escapes its permitted folder')
    data = path.read_bytes()
    if sha(data) != record['sha256']:
        raise ValueError(f'Reviewed file hash differs: {record["file"]}')
    return path, data


def validate_review(root, review):
    if review.get('decision') != 'APPROVED-FOR-ONE-TERMINAL-SEC-MEASUREMENT':
        raise ValueError('No explicit review for this bounded diagnostic')
    if review.get('scope') != 'terminal-edk2-sec-visual' or review.get('maxAttempts') != 1:
        raise ValueError('Wrong diagnostic scope or attempt count')
    fd_path, fd = checked_file(root, review['fd'], ('build',))
    image_path, image = checked_file(root, review['image'], ('local',))
    info = verify(fd)
    if int(info['secEntryAddress'], 16) != 0x80088000:
        raise ValueError('FD entry differs from the diagnostic PC guard')
    fields = HEADER.unpack_from(image)
    kernel = image[PAGE:PAGE + fields[1]]
    decoder = zlib.decompressobj(31)
    decoded = decoder.decompress(kernel, len(fd) + 1)
    dtb = decoder.unused_data
    if not decoder.eof or decoded != fd or sha(dtb) != DTB_SHA:
        raise ValueError('Image does not contain the reviewed FD and exact unit DTB')
    verify_container(image, fd, dtb)
    for label in ('model', 'data', 'sourceAudit'):
        _, data = checked_file(root, review[label], ('build',))
        report = json.loads(data)
        expected = {'model': 'PASS-EMULATOR-ONLY', 'data': 'PASS-STATIC-DATA-ONLY',
                    'sourceAudit': 'PASS'}[label]
        if report.get('result') != expected:
            raise ValueError(f'{label} did not pass its own limited scope')
        if label == 'model' and (report.get('fdSha256') != sha(fd)
                or len(report.get('cases', [])) != 12
                or any(case.get('result') != 'PASS' for case in report['cases'])):
            raise ValueError('Model report does not cover the exact diagnostic FD')
        if label == 'sourceAudit':
            lock = json.loads((root / 'sources.lock.json').read_bytes())
            if (report.get('rejected') or not report.get('upstreamTreeClean')
                    or not report.get('upstreamInputsTracked')
                    or report.get('edk2') != lock['edk2']):
                raise ValueError('Source audit has rejected or dirty inputs')
            if sum(source['origin'] == 'original-project' for source in report['files']) < 5:
                raise ValueError('Source audit lacks original platform inputs')
            for source in report['files']:
                if source['origin'] == 'original-project':
                    checked_file(root, source, ('OculusGoPkg',))
    for record in review['checkedSourceFiles']:
        checked_file(root, record, ('OculusGoPkg', 'scripts', 'tools', 'tests'))
    return image_path, info['sha256']


def validate_preflight(report, serial, folder_name, now):
    stamp = datetime.strptime(folder_name, 'readonly-preflight-%Y%m%d-%H%M%S').replace(tzinfo=timezone.utc)
    if not 0 <= (now - stamp).total_seconds() <= 3600:
        raise ValueError('Android integrity evidence must be less than one hour old')
    if (report.get('result'), report.get('serial'), report.get('product'),
            report.get('slot'), report.get('root'), report.get('bootCompleted')) != (
            'PASS-READONLY', serial, 'pacific', '_a', True, '1'):
        raise ValueError('Unexpected Android identity/integrity evidence')
    records = report.get('partitionReadbacks', [])
    if {row['name'] for row in records} != {'aboot_a', 'aboot_b', 'boot_a', 'boot_b'}:
        raise ValueError('Missing original-partition readbacks')
    if len(records) != 4 or not all(row.get('originalMatch') is True for row in records):
        raise ValueError('Original-partition readbacks did not all match')


def reserve_attempt(directory, fd_sha, record):
    if not re.fullmatch('[0-9a-f]{64}', fd_sha):
        raise ValueError('Invalid FD digest')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'sec-visual-{fd_sha}.json'
    # Atomic exclusive creation; never overwrite or reset an existing ledger.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--fastboot', type=Path)
    parser.add_argument('--expected-serial')
    parser.add_argument('--preflight', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--operator-present', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    review_bytes = args.review.read_bytes()
    image_path, fd_sha = validate_review(root, json.loads(review_bytes))
    if not args.execute:
        print(json.dumps({'result': 'PASS-OFFLINE-VALIDATION-ONLY', 'fdSha256': fd_sha,
                          'deviceContacted': False, 'attemptConsumed': False}, indent=2))
        return
    if not args.operator_present or not args.fastboot or not args.preflight:
        raise SystemExit('Execution needs a current operator, Fastboot path and fresh preflight')
    if not re.fullmatch('[A-Za-z0-9]+', args.expected_serial or ''):
        raise SystemExit('Execution needs an explicit verified serial')
    if sha(args.fastboot.read_bytes()) != FASTBOOT_SHA256:
        raise SystemExit('Unexpected Fastboot binary')
    preflight_path = args.preflight.resolve()
    if not preflight_path.is_relative_to(root / 'local'):
        raise SystemExit('Expected a locally retained preflight')
    preflight = json.loads(preflight_path.read_bytes())
    validate_preflight(preflight, args.expected_serial, preflight_path.parent.name,
                       datetime.now(timezone.utc))
    originals = {row['name']: row for row in json.loads(
        (root / 'docs/evidence/partitions.json').read_bytes())['partitions']}
    for row in preflight['partitionReadbacks']:
        if (row['size'], row['sha256']) != (originals[row['name']]['size'], originals[row['name']]['sha256']):
            raise SystemExit('Preflight does not match the preserved inventory')
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True)
    if dirty.strip():
        raise SystemExit('Commit/review the scoped changes before execution; do not discard other work')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    output = root / 'local' / f'sec-visual-once-{stamp}'
    output.mkdir(parents=True, exist_ok=False)
    report = {'result': 'IN-PROGRESS', 'serial': args.expected_serial,
              'reviewSha256': sha(review_bytes), 'fdSha256': fd_sha,
              'imageSha256': sha(image_path.read_bytes()), 'commands': [],
              'attemptConsumed': False, 'partitionWriteCommandIssued': False,
              'rebootCommandIssued': False, 'firmwareTransferCommandIssued': False,
              'physicalExecution': 'UNKNOWN'}

    def capture(label, arguments, timeout=10):
        command = [str(args.fastboot), '-s', args.expected_serial, *arguments]
        entry = {'label': label, 'arguments': arguments, 'timeoutSeconds': timeout}
        report['commands'].append(entry)
        print(label, flush=True)
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            entry['status'] = 'TIMEOUT'
            (output / f'{label}.stdout.txt').write_bytes(error.stdout or b'')
            (output / f'{label}.stderr.txt').write_bytes(error.stderr or b'')
            raise RuntimeError('Host command timed out; device may still be running; no retry') from error
        entry['exitCode'] = result.returncode
        (output / f'{label}.stdout.txt').write_bytes(result.stdout)
        (output / f'{label}.stderr.txt').write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f'{label} returned {result.returncode}; no automatic retry')
        return (result.stdout + b'\n' + result.stderr).decode('utf-8', errors='replace')

    try:
        require_device(capture('devices', ['devices', '-l']), args.expected_serial)
        report['bootloader'] = validate_replies({label: capture(label, list(arguments))
                                               for label, arguments in QUERIES})
        ledger = reserve_attempt(root / 'local/physical-attempts', fd_sha,
            {'status': 'CONSUMED-BEFORE-SEND', 'reviewSha256': sha(review_bytes),
             'imageSha256': report['imageSha256'], 'createdUtc': datetime.now(timezone.utc).isoformat(),
             'logDirectory': output.name})
        report['attemptConsumed'] = True
        report['ledger'] = ledger.name
        report['firmwareTransferCommandIssued'] = True
        capture('temporary-boot', ['boot', str(image_path)], timeout=20)
        report['result'] = 'COMMAND-ACCEPTED-EXECUTION-UNKNOWN'
    except Exception as error:
        report['result'] = 'FAIL-NO-RETRY'
        report['error'] = str(error)
    finally:
        (output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n',
                                           encoding='utf-8', newline='\n')
    print(report['result'], output, flush=True)
    if report['result'] != 'COMMAND-ACCEPTED-EXECUTION-UNKNOWN':
        raise SystemExit(report.get('error', 'Measurement did not complete'))


if __name__ == '__main__':
    main()
