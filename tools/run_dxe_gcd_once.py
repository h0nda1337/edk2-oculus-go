"""Check the DXE_GCD package offline or perform one attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import subprocess

from attended_terminal import attended_main, measure_once
from run_dxe_mem_once import REQUIRED as MEMORY_INPUTS, SEC_SOURCES, validate_memory_cases
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-gcd-review-20261119.json'
LEDGER = 'local/physical-attempts/dxe-gcd-20261119.json'
PREVIOUS = 'docs/evidence/dxe-mem-transfer-20261119.json'
SOURCES = SEC_SOURCES | {'OculusGoPkg/DxeCheckpoint/ImageGcd.c', 'OculusGoPkg/Include/Trial/StackLayout.h'}
REQUIRED = MEMORY_INPUTS | SOURCES | {
    'OculusGoPkg/DxeCheckpoint/GcdCheckpoint.inf', 'tools/run_dxe_gcd_once.py',
    'tests/dxe_gcd_trace.py', 'tests/test_dxe_gcd_review.py'}
OUTCOMES = {
    'valid': ('TrialGcdComplete','gcd'), 'icache': ('TrialGcdComplete','gcd'),
    'image-metadata': ('TrialGcdRejected','memory'), 'hob-copy': ('TrialGcdRejected','image'),
    'hob-page-type': ('TrialGcdRejected','image'),
    'gcd-owner': ('TrialGcdRejected','relocated-hobs'), 'stack-type': ('TrialGcdRejected','relocated-hobs')}


def validate_reports(model, static, digest):
    validate_memory_cases(model, static, digest, 'DXE-GCD', OUTCOMES)
    for row in model['cases']:
        case = row['case']
        if case not in OUTCOMES:
            continue
        low, high = (int(x,16) for x in row['freeWindow'])
        base, size = int(row['coreBase'],16), static['peImageBytes']
        require(row['imageInitSuccess'] and low <= int(row['imageHandle'],16) < high
                and base <= int(row['loadedImageProtocol'],16) <= base+size-96
                and row['loadedImageBytes'] == size, 'Invalid loaded image observation')
        if case == 'image-metadata':
            continue
        n = row['hobBytesCompared']
        require(row['gcdInitSuccess'] and 56 <= n <= 4096 and
                low <= int(row['relocatedHobs'],16) <= high-n, 'Missing HOB migration')
        if case == 'hob-copy':
            continue
        require(row['originalHobPageType'] == 'EfiBootServicesData' and
                row['coreFileGuidPointsIntoOriginalHobs'] is True, 'Original GUID storage is unprotected')
        if case == 'hob-page-type':
            continue
        cursor, ram, stack = 0, 0, 0
        for start, end, kind in row['gcdRanges']:
            lo, hi = int(start,16), int(end,16)
            require(lo == cursor and lo < hi <= 1<<32, 'Broken GCD map coverage')
            if kind == 2:
                require(0x80200000 <= lo < hi <= 0x80380000, 'System memory escapes arena')
                ram += hi-lo
            elif kind == 1:
                require((lo,hi) == (0x8046f000,0x8047f000),'Unexpected reservation')
                stack += hi-lo
            else:
                require(kind == 0 and (hi <= 0x80200000 or lo >= 0x80380000),
                        'Unexpected GCD resource')
            cursor = hi
        require(cursor == 1<<32 and ram == row['systemMemoryBytes'] == 0x180000,
                'Wrong GCD address space or RAM size')
        require(stack == row['reservedStackBytes'] == 65536,'Missing stack reservation')
        if case not in ('gcd-owner','stack-type'):
            require(row['gcdMapFreed'] is True, 'Map buffer release missing')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root, review, scope='terminal-edk2-dxe-image-gcd',
                                  build_prefix='DEBUG-DXE_GCD-', sec_sources=SOURCES, required=REQUIRED,
                                  previous_record=PREVIOUS, validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'dxe-gcd', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
