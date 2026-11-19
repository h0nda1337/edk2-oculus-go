"""Verify the private SEC_STACK artifacts or run their one attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json
from pathlib import Path
import re
import subprocess
import zlib

from android_boot import DTB_SHA, HEADER, PAGE, verify_container
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file, sha
from verify_fd import verify

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/sec-stack-review-20261118.json'
LEDGER = 'local/physical-attempts/sec-stack-20261118.json'
PREVIOUS = 'docs/evidence/sec-mem-transfer-20261118.json'
SEC_SOURCES = {f'OculusGoPkg/SecMem/{name}' for name in ('Hob.c', 'Stack.c', 'StackEntry.S')}
REQUIRED = SEC_SOURCES | {
    'OculusGoPkg/SecMem/SecStack.inf', 'OculusGoPkg/OculusGoPkg.dsc', 'OculusGoPkg/OculusGoPkg.fdf',
    'scripts/build.sh', 'scripts/build-edk2.ps1', 'tools/verify_fd.py', 'tools/android_boot.py',
    'tools/audit_build_sources.py', 'tools/collect_readonly_preflight.py', 'tools/inspect_fastboot.py',
    'tools/run_sec_visual_once.py', 'tools/run_sec_c_once.py', 'tools/attended_terminal.py',
    'tools/run_sec_stack_once.py', 'tools/emulate_entry.py', 'tools/emulate_sec_handoff.py',
    'tools/verify_sec_visual_data.py', 'tests/sec_c_qemu.py', 'tests/entry_harness.S',
    'tests/sec_visual_mmu_el1.S', 'tests/sec_mem_static.py', 'tests/sec_mem_qemu.py',
    'tests/sec_stack_qemu.py', 'tests/sec_stack_static.py',
}
EXPECTED = {'valid':'StackComplete', 'relocated':'StackEntryRejected', 'dcache':'StackEntryRejected',
            'wrong-x0':'StackEntryRejected', 'dirty-stack':'StackMemoryRejected', 'lower-guard':'StackGuardRejected',
            'forward-fault':'StackMemoryRejected', 'reverse-fault':'StackMemoryRejected',
            'live-frame':'StackFrameRejected', 'bad-phit':'StackFrameRejected', 'late-guard':'StackGuardRejected',
            'exception':'StackException'}


def validate_reports(model, static, digest):
    require(model['result'] == 'PASS-QEMU-SEC-STACK' and static['result'] == 'PASS-STATIC-SEC-STACK'
            and model['fdSha256'] == static['fdSha256'] == digest
            and re.fullmatch('[a-f0-9]{64}', model['elfSha256'])
            and model['elfSha256'] == static['elfSha256'], 'Different firmware under review')
    require(model['stackRange'] == ['0x8043f000','0x8047f000'] and model['bytesPerPattern'] == 262144
            and model['vectors']['slotsVerified'] == 16 and static['reachableInstructions'] == 290,
            'Wrong stack extent or instruction coverage')
    required = {(el,case): end for el in (1,2) for case,end in EXPECTED.items()}
    required[1,'mmu-el1'] = 'StackEntryRejected'
    for row in model['cases']:
        outcome = required.pop((row['el'],row['scenario']), None)
        require(outcome and row['terminal'] == outcome and row['screenMatched'] is True
                and row['fdOutsideFootprintMatched'] is True and row['unexpectedGuestRamWrites'] == 0
                and row['normalPoolAccesses'] == 0, 'Missing or unexpected model result')
        if row['scenario'] == 'valid':
            require(row['stackPointersAtCallEntries'] == ['0x8047efa0','0x8047eb80','0x8047e760',
                    '0x8047e340','0x8047df10'], 'Unexpected C/PI stack usage')
    require(not required, 'Incomplete QEMU coverage')


def reviewed_inputs(root, review):
    require(review['scope'] == 'terminal-edk2-sec-stack' and review['decision'] == 'ONE-ATTENDED-TEMPORARY-BOOT'
            and type(review['maxAttempts']) is int and review['maxAttempts'] == 1, 'Wrong review')
    fd_path, fd = checked_file(root, review['fd'], ('build',))
    image_path, image = checked_file(root, review['image'], ('local',))
    require(fd_path.parent.name.startswith('DEBUG-SEC_STACK-') and len(fd) == review['fd']['size']
            and len(image) == review['image']['size'] and fd[0x3be000:0x3be008] == b'GOSTACK1'
            and fd[64:PAGE] == b'\xff'*(PAGE-64), 'Unexpected diagnostic layout')
    info = verify(fd)
    require(info['secEntryAddress'] == review['entryAddress'], 'Different SEC entry')
    compressed = image[PAGE:PAGE + HEADER.unpack_from(image)[1]]
    decoder = zlib.decompressobj(31)
    require(decoder.decompress(compressed, len(fd)+1) == fd and decoder.eof and sha(decoder.unused_data) == DTB_SHA,
            'Unexpected FD or Pacific EVT tree')
    verify_container(image, fd, decoder.unused_data)
    reports = {}
    for key, filename in [('model','QEMU.json'), ('staticAudit','STATIC.json'), ('sourceAudit','SOURCES.json')]:
        path, raw = checked_file(root, review[key], ('build',))
        require(path == fd_path.parent/filename, f'{key} belongs to a different build')
        reports[key] = json.loads(raw)
    validate_reports(reports['model'], reports['staticAudit'], info['sha256'])
    audit = reports['sourceAudit']
    require(audit['result'] == 'PASS' and audit['rejected'] == [] and audit['upstreamTreeClean'] is True
            and audit['upstreamInputsTracked'] is True and
            audit['edk2'] == json.loads((root/'sources.lock.json').read_bytes())['edk2'], 'Source audit failed')
    originals = [r for r in audit['files'] if r['origin'] == 'original-project']
    require({r['file'] for r in originals} == SEC_SOURCES, 'Unexpected platform code in SEC')
    require({r['file'] for r in review['checkedSourceFiles']} == REQUIRED, 'Reviewed inputs incomplete')
    for row in [*originals, *review['checkedSourceFiles']]:
        checked_file(root, row, ('OculusGoPkg','scripts','tests','tools'))
    _, raw = checked_file(root, review['priorReadback'], ('local',))
    previous = json.loads((root/PREVIOUS).read_bytes())
    require(sha(raw) == previous['recovery']['reportSha256'], 'Prior device evidence differs')
    serial = json.loads(raw)['serial']
    require(re.fullmatch('[A-Za-z0-9]+', serial), 'Unexpected prior device identity')
    return image_path, serial


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'sec-stack', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
