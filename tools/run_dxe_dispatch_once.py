"""Validate the DXE_DISPATCH evidence or run the single attended RAM boot."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from pathlib import Path
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_dxe_debug_once import POSITIVE, REQUIRED as DEBUG_INPUTS, SOURCES as DEBUG_SOURCES, validate_debug_cases
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-dispatch-review-20261119.json'
LEDGER = 'local/physical-attempts/dxe-dispatch-20261119.json'
PREVIOUS = 'docs/evidence/dxe-debug-transfer-20261119.json'
SOURCES = DEBUG_SOURCES | {'OculusGoPkg/Include/Trial/DispatchLayout.h','OculusGoPkg/DxeCheckpoint/Dispatch.c'}
REQUIRED = DEBUG_INPUTS | SOURCES | {'OculusGoPkg/DxeCheckpoint/DispatchCheckpoint.inf',
    'tests/dxe_dispatch_trace.py','tools/run_dxe_dispatch_once.py','tests/test_dxe_dispatch_review.py'}
LATE = {**{k:('TrialDispatchComplete','protocol') for k in POSITIVE},
        'false-depex':('TrialDispatchRejected','dispatch'),
        'missing-load-path':('TrialDispatchRejected','dispatch'),
        'wrong-file-guid':('TrialDispatchRejected','dispatch'),
        'bad-protocol-result':('TrialDispatchRejected','start-driver')}


def validate_reports(model, static, digest):
    validate_dispatch_cases(model, static, digest, 'DXE-DISPATCH', {})


def validate_dispatch_cases(model, static, digest, profile, later):
    outcomes = {**LATE, **later}
    validate_debug_cases(model, static, digest, profile, outcomes)
    require(model['driverGuid'] == static['driverGuid'] == '9b680fce-ad6b-4f3a-b60b-f59899003443' and
            model['driverPeSha256'] == static['driverPeSha256'] and
            re.fullmatch('[0-9a-f]{64}',static['driverPeSha256']), 'Unexpected embedded FV driver')
    for row in model['cases']:
        case = row['case']
        if case not in outcomes:
            require('driverFile' not in row, 'Dispatch before prerequisite')
            continue
        require(row['eventsInitialized'] is True and row['driverFile'] == static['driverGuid'] and
                int(row['fvHandle'],16) != 0, 'Missing firmware volume discovery')
        require(row['dependencySatisfied'] is (case != 'false-depex'), 'Incorrect dependency result')
        if case == 'false-depex':
            require('loadStatus' not in row, 'Load after FALSE DEPEX')
            continue
        if case == 'missing-load-path':
            require(row['loadStatus'] == 'EFI_INVALID_PARAMETER' and 'driverImageBase' not in row,
                    'Image load accepted a missing device path')
            continue
        lo,hi = [int(x,16) for x in row['freeWindow']]
        address = int(row['driverImageBase'],16)
        end = address + row['driverImageBytes']
        require(row['loadStatus'] == 'EFI_SUCCESS' and address % 4096 == 0 and lo <= address < end <= hi and
                row['driverHandle'] != row['imageHandle'], 'Invalid driver image')
        if case == 'wrong-file-guid':
            require('driverText' not in row and 'startStatus' not in row, 'Wrong file was made executable')
            continue
        start,limit = [int(x,16) for x in row['driverText']]
        require(address < start < limit <= end and start % 4096 == limit % 4096 == 0 and
                row['startStatus'] == 'EFI_SUCCESS' and row['getDevicePathSize'] == 4 and
                start <= address+model['driverSymbols']['DevicePathEntryPoint'] < limit and
                start <= address+model['driverSymbols']['GetDevicePathSize'] < limit and
                row['protocolGuid'] == '0379be4e-d706-437d-b037-edb82fb772a4' and
                address <= int(row['protocolInterface'],16) < end, 'Missing driver execution or useful protocol')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root, review, scope='terminal-edk2-dxe-dispatch',
                                 build_prefix='DEBUG-DXE_DISPATCH-', sec_sources=SOURCES, required=REQUIRED,
                                 previous_record=PREVIOUS, validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'dxe-dispatch', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
