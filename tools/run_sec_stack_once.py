"""Verify the private SEC_STACK artifacts or run their one attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

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
    return verify_terminal_inputs(root, review, scope='terminal-edk2-sec-stack',
                                  build_prefix='DEBUG-SEC_STACK-', sec_sources=SEC_SOURCES,
                                  required=REQUIRED, previous_record=PREVIOUS, validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'sec-stack', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
