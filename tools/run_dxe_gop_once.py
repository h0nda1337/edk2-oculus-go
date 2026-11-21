"""Check the two-driver GOP trial offline or perform its single attended RAM boot."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from pathlib import Path
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_dxe_dispatch_once import POSITIVE, REQUIRED as DISPATCH_INPUTS, SOURCES as DISPATCH_SOURCES, validate_dispatch_cases
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-gop-review-20261119.json'
LEDGER = 'local/physical-attempts/dxe-gop-20261119.json'
PREVIOUS = 'docs/evidence/dxe-dispatch-transfer-20261119.json'
SOURCES = DISPATCH_SOURCES | {'OculusGoPkg/DxeCheckpoint/GopBlt.c', 'OculusGoPkg/Include/Display/Framebuffer.h',
                              'OculusGoPkg/Drivers/InheritedGopDxe/InheritedGopDxe.c'}
REQUIRED = DISPATCH_INPUTS | SOURCES | {'OculusGoPkg/Drivers/InheritedGopDxe/InheritedGopDisplay.inf',
    'OculusGoPkg/DxeCheckpoint/GopCheckpoint.inf','tools/run_dxe_gop_once.py','tests/dxe_gop_trace.py',
    'tests/test_dxe_gop_review.py'}
OUTCOMES = {**{k:('TrialGopComplete','gop-blt') for k in POSITIVE},
            'gop-depex':('TrialDispatchRejected','protocol'), 'gop-file-guid':('TrialDispatchRejected','protocol'),
            'gop-readback':('TrialGopErrorVisible','gop-error'), 'gop-fill-status':('TrialGopErrorVisible','gop-error')}


def validate_reports(model, static, digest):
    validate_gop_cases(model,static,digest,'DXE-GOP',{})


def validate_gop_cases(model,static,digest,profile,later):
    outcomes = {**OUTCOMES, **later}
    validate_dispatch_cases(model,static,digest,profile,outcomes)
    require(model['gopGuid']==static['gopGuid']=='8cd15dc8-f091-4917-b779-342c1e0aa2de' and
            model['gopPeSha256']==static['gopPeSha256'] and re.fullmatch('[0-9a-f]{64}',static['gopPeSha256']),
            'Unexpected second FV image')
    for row in model['cases']:
        case = row['case']
        if 'dependencySatisfied' in row:
            require(row['gopWaitedForUtilities'] is True, 'GOP should initially wait')
        if case not in outcomes:
            require('gopImageBase' not in row, 'GOP loaded before the first driver passed')
            continue
        require(row['gopDependencySatisfied'] is (case!='gop-depex'), 'Wrong second DEPEX result')
        if case=='gop-depex':
            require('gopImageBase' not in row, 'GOP was loaded with an unfulfilled dependency')
            continue
        address = int(row['gopImageBase'],16)
        end = address+row['gopImageBytes']
        first = int(row['driverImageBase'],16)
        lo,hi = (int(x,16) for x in row['freeWindow'])
        require(lo<=address<end<=hi and address%4096==0 and end%4096==0 and
                (end<=first or address>=first+row['driverImageBytes']) and
                row['gopHandle'] not in (row['imageHandle'],row['driverHandle']), 'Bad second allocation')
        if case=='gop-file-guid':
            require('gopText' not in row and 'gopStarted' not in row,'Wrong image was started')
            continue
        start,limit = (int(x,16) for x in row['gopText'])
        require(address<start<limit<=end and all(start<=address+offset<limit for offset in model['gopSymbols'].values())
                and row['gopStarted'] is True and address<=int(row['gopInterface'],16)<end, 'Invalid live GOP')
        count = {'gop-readback':4, 'gop-fill-status':23}.get(case,24)
        require(row['bltCalls']==count,'Wrong number of observed GOP calls')
        if case in POSITIVE or case in later:
            require(row['rawBgrRow']==['ff0000','0000ff','00ffff','0000ff','ff0000'],'Unexpected physical BGR bytes')
        else:
            require('rawBgrRow' not in row,'Success pattern after rejection')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root,review,scope='terminal-edk2-dxe-gop',build_prefix='DEBUG-DXE_GOP-',
                                 sec_sources=SOURCES,required=REQUIRED,previous_record=PREVIOUS,
                                 validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root,LEDGER,image,tool,serial,preflight,report,output)


if __name__=='__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'dxe-gop', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
