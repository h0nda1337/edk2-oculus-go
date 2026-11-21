"""Verify the standalone application trial or perform its single attended RAM boot."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from pathlib import Path
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_dxe_text_upright_once import POSITIVE, REQUIRED as TEXT_INPUTS, LINES, EYE_RGB, NATIVE_BGR
from run_dxe_text_once import SOURCES as TEXT_SOURCES, validate_text_cases, verify_captures
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-app-review-20261120.json'
LEDGER = 'local/physical-attempts/dxe-app-20261120.json'
PREVIOUS = 'docs/evidence/dxe-text-upright-transfer-20261120.json'
SOURCES = TEXT_SOURCES | {'OculusGoPkg/Applications/ConsoleProbe/ConsoleProbe.c',
                          'OculusGoPkg/DxeCheckpoint/AppLaunch.c', 'OculusGoPkg/DxeCheckpoint/AppLaunch.h'}
REQUIRED = TEXT_INPUTS | SOURCES | {'OculusGoPkg/Applications/ConsoleProbe/ConsoleProbe.inf',
                                    'OculusGoPkg/DxeCheckpoint/AppCheckpoint.inf','tools/run_dxe_app_once.py',
                                    'tests/dxe_app_trace.py','tests/test_dxe_app.py'}
SUCCESS_RASTER = '63c0e32c7402661c659e05744dafc5d5441a8f0a87b0f1e062c62d103138a2c4'
OUTCOMES = {**{case:('TrialAppComplete','app-complete') for case in POSITIVE},
            'app-missing-file':('TrialAppRejected','text-complete'),
            'app-output-error':('TrialAppRejected','text-complete')}


def validate_reports(model, static, digest):
    validate_text_cases(model,static,digest,LINES,EYE_RGB,profile='DXE-APP',later=OUTCOMES)
    require(model['appFileGuid'] == static['appFileGuid'] == 'a63728d5-057a-43bb-88f7-89aa3e5856e9' and
            model['appPeSha256'] == static['appPeSha256'] and re.fullmatch('[a-f0-9]{64}',model['appPeSha256']) and
            model['appPeBytes'] == static['appPeBytes'] > 0, 'Unexpected FV application')
    for row in model['cases']:
        case = row['case']
        if case not in OUTCOMES:
            require('appLoadStatus' not in row, 'Reached the application prematurely')
            continue
        require(row['nativeBgrSha256'] == NATIVE_BGR,'Initial console scanout differs')
        if case == 'app-missing-file':
            require(row['appLoadStatus'] == 'EFI_NOT_FOUND' and 'appHandle' not in row,'Missing file started')
            continue
        start,end = (int(v,16) for v in row['appText'])
        addr,size = int(row['appBase'],16),row['appBytes']
        lo,hi = (int(v,16) for v in row['freeWindow'])
        require(lo <= addr < start < end <= addr+size <= hi and start <= int(row['appOutputCaller'],16) < end and
                start <= int(row['appEntry'],16) < end and row['appFvPeSha256'] == static['appPeSha256'] and
                row['appLoadStatus'] == 'EFI_SUCCESS' and row['appRemovedFromDebugTable'] is True and
                row['appCodeRestoredToRwXn'] is True, 'Invalid application load, call or unload')
        require(row['appHandle'] not in (row['imageHandle'],row['driverHandle'],row['gopHandle']) and
                int(row['appEntry'],16) == addr+model['appSymbols']['_ModuleEntryPoint'] and
                start <= addr+model['appSymbols']['ConsoleProbeMain'] < end, 'Unexpected child handle or entry')
        for base_field,size_field in [('driverImageBase','driverImageBytes'), ('gopImageBase','gopImageBytes')]:
            other = int(row[base_field],16)
            require(addr+size <= other or other+row[size_field] <= addr,'Child image overlaps a resident driver')
        status = (1<<63)|2 if case=='app-output-error' else 0
        require(row['appOutputStatus'] == row['appExitStatus'] == row['appStartStatus'] == status,
                'Mismatched application status')
        if status:
            require('appEyeRgbSha256' not in row,'Unexpected success capture after application failure')
        else:
            require(row['appLine'] == '5 APP EFI 6' and row['appEyesMatch'] is True and
                    row['appEyeRgbSha256'] == SUCCESS_RASTER and re.fullmatch('[a-f0-9]{64}',row['appEyePngSha256']),
                    'Application output pixels differ')


def reviewed_inputs(root, review):
    verify_captures(root,review,'appEyePngSha256')
    return verify_terminal_inputs(root,review,scope='terminal-edk2-dxe-app',build_prefix='DEBUG-DXE_APP-',
                                  sec_sources=SOURCES,required=REQUIRED,previous_record=PREVIOUS,
                                  validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root,LEDGER,image,tool,serial,preflight,report,output)


if __name__ == '__main__':
    try:
        attended_main(ROOT,REVIEW,LEDGER,reviewed_inputs,'dxe-app',measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
