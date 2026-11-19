"""Verify the DXE_DEBUG candidate and evidence, with a separate attended RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import struct
import subprocess
import zlib

from attended_terminal import attended_main, measure_once
from run_dxe_tables_once import REQUIRED as TABLE_INPUTS, SOURCES as TABLE_SOURCES, TABLE_CASES, validate_table_cases
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-debug-review-20261119.json'
LEDGER = 'local/physical-attempts/dxe-debug-20261119.json'
PREVIOUS = 'docs/evidence/dxe-tables-transfer-20261119.json'
SOURCES = TABLE_SOURCES | {'OculusGoPkg/Include/Trial/DebugPage.h','OculusGoPkg/DxeCheckpoint/DebugImage.c'}
REQUIRED = TABLE_INPUTS | SOURCES | {'OculusGoPkg/DxeCheckpoint/DebugCheckpoint.inf','tests/dxe_debug_trace.py',
                                     'tests/test_dxe_debug_review.py','tools/run_dxe_debug_once.py'}
POSITIVE = ('valid','icache','table-order')
EARLY = ('locator-dirty','locator-readback')
BEFORE_PUBLICATION = (*EARLY, 'oversize', 'locator-efi-type')
LATE = ('locator-crc','debug-record','debug-guid')
OUTCOMES = {**{k:('TrialDebugComplete','debug-image') for k in POSITIVE},
            **{k:('TrialDebugRejected','tables') for k in BEFORE_PUBLICATION},
            **{k:('TrialDebugRejected','debug-locator') for k in LATE}}


def validate_reports(model, static, digest):
    validate_table_cases(model, static, digest, 'DXE-DEBUG', {**TABLE_CASES, **OUTCOMES})
    page = 0x80400000
    require(model['debugPage'] == static['debugPage'] == hex(page), 'Unexpected locator address')
    for r in model['cases']:
        case = r['case']
        if case not in OUTCOMES:
            require('debugPageTouched' not in r, 'Page touched before debugger stage')
            continue
        require(r['debugPageTouched'] is True, 'Unobserved debugger page')
        if case in EARLY:
            require('allocation' not in r and 'debugLocator' not in r, 'Page accepted before qualification')
            continue
        require(r['qualifiedBytes'] == 4096, 'Incomplete page qualification')
        if case == 'oversize':
            require(r['oversizeRequest'] == {'pages':1025,'status':'EFI_OUT_OF_RESOURCES'}
                    and 'allocation' not in r, 'Wrong oversized allocation result')
            continue
        require(r['allocation'] == {'pages':1,'base':hex(page),'type':'EfiBootServicesData'} and
                r['gcdAndEfiOwnershipVerified'] is True, 'Invalid page allocation')
        if case == 'locator-efi-type':
            require('debugImage' not in r, 'Publication accepted a free page')
            continue
        loc, image = r['debugLocator'], r['debugImage']
        st = int(r['systemTable'],16)
        checksum = zlib.crc32(struct.pack('<8sQ8x', b'IBI SYST', st))
        require(loc == {'address':hex(page),'systemTable':hex(st),'crc32':f'{checksum:08x}'}, 'Invalid debugger locator')
        lo,hi = (int(x,16) for x in r['freeWindow'])
        base = int(r['coreBase'],16)
        require(image['guid'] == '49152e77-1ada-4764-b7a2-7afefed95e8b' and
                image['entries'] == 1 and image['updateStatus'] == 2 and image['imageBase'] == r['coreBase'] and
                image['loadedImage'] == r['loadedImageProtocol'] and image['handle'] == r['imageHandle'] and
                base <= int(image['header'],16) <= base+static['peImageBytes']-16 and
                lo <= int(image['table'],16) <= hi-4096 and lo <= int(image['record'],16) <= hi-24,
                'Invalid upstream debug record')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root, review, scope='terminal-edk2-dxe-debug-image',
                                  build_prefix='DEBUG-DXE_DEBUG-', sec_sources=SOURCES, required=REQUIRED,
                                  previous_record=PREVIOUS, validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'dxe-debug', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
