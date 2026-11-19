"""Verify the reviewed SEC_MMU image or perform its one attended RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/sec-mmu-review-20261118.json'
LEDGER = 'local/physical-attempts/sec-mmu-20261118.json'
PREVIOUS = 'docs/evidence/sec-stack-transfer-20261118.json'
SEC_SOURCES = {f'OculusGoPkg/SecMmu/{s}' for s in ('Entry.S','Layout.h','Tables.c','Signal.c')}
REQUIRED = SEC_SOURCES | {
    'OculusGoPkg/SecMmu/SecMmu.inf','OculusGoPkg/OculusGoPkg.dsc','OculusGoPkg/OculusGoPkg.fdf',
    'scripts/build.sh','scripts/build-edk2.ps1','tools/verify_fd.py','tools/android_boot.py',
    'tools/audit_build_sources.py','tools/collect_readonly_preflight.py','tools/inspect_fastboot.py',
    'tools/run_sec_visual_once.py','tools/run_sec_c_once.py','tools/attended_terminal.py','tools/terminal_review.py',
    'tools/run_sec_mmu_once.py','tools/emulate_entry.py','tools/emulate_sec_handoff.py',
    'tools/verify_sec_visual_data.py','tests/sec_c_qemu.py','tests/entry_harness.S','tests/sec_visual_mmu_el1.S',
    'tests/sec_mem_static.py','tests/sec_mem_qemu.py','tests/sec_mmu_qemu.py','tests/sec_mmu_static.py',
}


def validate_reports(model, static, digest):
    require(model['result'] == 'PASS-QEMU-SEC-MMU' and static['result'] == 'PASS-STATIC-SEC-MMU'
            and model['fdSha256'] == static['fdSha256'] == digest
            and re.fullmatch('[0-9a-f]{64}', model['elfSha256']) and model['elfSha256'] == static['elfSha256'],
            'Model and static audit must cover the same delivered FD and ELF')
    require(static['checkedActivationLevels'] == [1,2] and static['reachableInstructions'] == 342
            and model['vectors']['slotsVerified'] == 16, 'Missing activation or vector coverage')
    groups = {
        'untouched': ('dcache','wrong-x0','relocated','dirty-tables','dirty-stack'),
        'mono': ('last-page-absent','wrong-output','wrong-attribute','mapped-guard','instruction-fault','mono-corruption'),
        'color': ('color-corruption',), 'sealed': ('valid','icache')}
    required = {(el,case): pattern for el in (1,2) for pattern, cases in groups.items() for case in cases}
    required[1,'mmu-el1'] = 'untouched'
    for row in model['cases']:
        case = row['case']
        pattern = required.pop((row['el'],case), None)
        end = 'MmuComplete' if pattern == 'sealed' else ('MmuException' if case == 'instruction-fault' else 'MmuRejected')
        require(pattern and row['lastPattern'] == pattern and row['terminal'] == end
                and row['fullScreenAndGuardsMatched'] is True and row['unexpectedGuestRamWrites'] == 0
                and row['highPoolAccesses'] == 0, 'Missing or unexpected MMU test outcome')
        if pattern != 'untouched':
            require(int(row['translatedSctlr'],16) & 0x1005 == (0x1001 if case == 'icache' else 1),
                    'The model did not observe the required translated SCTLR')
    require(not required,'Incomplete EL1/EL2 scenario coverage')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root, review, scope='terminal-edk2-sec-mmu',
                                  build_prefix='DEBUG-SEC_MMU-', sec_sources=SEC_SOURCES,
                                  required=REQUIRED, previous_record=PREVIOUS, validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'sec-mmu', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
