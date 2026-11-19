"""Host-side transport shared by terminal SEC measurements. SPDX-License-Identifier: BSD-2-Clause-Patent"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from inspect_fastboot import FASTBOOT_SHA256, QUERIES, require_device, validate_replies
from run_sec_c_once import capture, check_readback, locked_input, require
from run_sec_visual_once import sha


def measure_once(root, ledger_path, image, tool, serial, preflight, report, output,
                 capture=capture, check_readback=check_readback):
    ledger = root / ledger_path
    require(not ledger.exists(), 'Temporary boot attempt already consumed')
    before = check_readback(root, preflight, serial, datetime.now(timezone.utc))
    report['preflightSha256'] = before
    require_device(capture(tool, serial, output, report, 'devices', ['devices', '-l'], 10), serial)
    replies = {key: capture(tool, serial, output, report, key, args, 10) for key, args in QUERIES}
    report['bootloader'] = validate_replies(replies)
    require(check_readback(root, preflight, serial, datetime.now(timezone.utc)) == before,
            'Android evidence changed before transfer')
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump({'status': 'CONSUMED-BEFORE-SEND', 'reservedUtc': datetime.now(timezone.utc).isoformat(),
                   'imageSha256': report['imageSha256'], 'reviewSha256': report['reviewSha256'],
                   'logDirectory': output.name}, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    report['attemptConsumed'] = True
    report['temporaryBootCommandIssued'] = True
    response = capture(tool, serial, output, report, 'temporary-boot', ['boot', str(image)], 20)
    require(re.search(r"(?m)^Sending 'boot.img'.*\bOKAY\b", response)
            and re.search(r'(?m)^Booting\s+OKAY\b', response), 'Incomplete Fastboot acknowledgement')
    report['result'] = 'COMMAND-ACCEPTED-EXECUTION-UNKNOWN'


def attended_main(root, review_path, ledger_path, reviewed_inputs, label, measure):
    parser = argparse.ArgumentParser(description=f"Verify or temporarily boot the reviewed {label} image")
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--operator-present', action='store_true')
    parser.add_argument('--preflight', type=Path)
    parser.add_argument('--fastboot', type=Path)
    parser.add_argument('--expected-serial')
    args = parser.parse_args()
    review_bytes = (root / review_path).read_bytes()
    review = json.loads(review_bytes)
    image, prior_serial = reviewed_inputs(root, review)
    if not args.execute:
        print(json.dumps({'result': 'PASS-OFFLINE-ONLY', 'deviceContacted': False,
                          'imageSha256': review['image']['sha256'], 'ledgerAlreadyPresent': (root / ledger_path).exists()}))
        return
    require(args.operator_present and args.preflight and args.fastboot and args.expected_serial == prior_serial,
            'An attended session, matching local serial, explicit Fastboot and fresh Android preflight are required')
    require(not (root / ledger_path).exists(), 'Temporary boot attempt already consumed')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip()
            and subprocess.check_output(['git', 'show', 'HEAD:' + review_path], cwd=root) == review_bytes,
            'Live execution requires an intact committed checkout and review')
    tool = args.fastboot.resolve(strict=True)
    out = root / 'local' / (label + '-once-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))
    out.mkdir()
    report = {'result': 'IN-PROGRESS', 'commands': [], 'attemptConsumed': False,
              'reviewSha256': sha(review_bytes), 'imageSha256': review['image']['sha256'],
              'fdSha256': review['fd']['sha256'], 'temporaryBootCommandIssued': False,
              'physical' + ''.join(part.title() for part in label.split('-')) + 'Execution': 'UNKNOWN', 'partitionWriteCommandIssued': False}
    try:
        with locked_input(image, report['imageSha256']), locked_input(tool, FASTBOOT_SHA256):
            measure(root, image, tool, prior_serial, args.preflight, report, out)
    except Exception as error:
        report.update(result='FAIL', error=str(error))
        raise
    finally:
        (out / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(report['result'], out)
