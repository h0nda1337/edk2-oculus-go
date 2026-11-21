"""Offline verification and single attended RAM boot of the text-console trial."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from pathlib import Path
import json
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_dxe_gop_once import POSITIVE, REQUIRED as GOP_INPUTS, SOURCES as GOP_SOURCES, validate_gop_cases
from run_sec_c_once import require
from run_sec_visual_once import checked_file, sha
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-text-review-20261120.json'
LEDGER = 'local/physical-attempts/dxe-text-20261120.json'
PREVIOUS = 'docs/evidence/dxe-gop-transfer-20261120.json'
DISPLAY = 'OculusGoPkg/Drivers/InheritedGopDxe/'
SOURCES = GOP_SOURCES | {DISPLAY+'TextConsole.h',DISPLAY+'TextConsole.c','OculusGoPkg/Include/third-party/edk2/ConsoleFont.h',
                         'OculusGoPkg/DxeCheckpoint/TextOutput.c'}
REQUIRED = GOP_INPUTS | SOURCES | {DISPLAY+'InheritedGopText.inf','OculusGoPkg/DxeCheckpoint/TextCheckpoint.inf',
    'tests/dxe_text_trace.py','tools/run_dxe_text_once.py','tests/test_dxe_text.py','tests/text_console_host.c','scripts/test-host.sh'}
EXPECTED_RASTER = '857bfdb8401e795369bce60028a9b123bcececae3fd3b61cdee7eeac5ab7a5dd'
OUTCOMES = {**{k:('TrialTextComplete','text-complete') for k in POSITIVE},
            'text-missing-interface':('TrialTextErrorVisible','text-error'),
            'text-blt-error':('TrialTextErrorVisible','text-error')}


def validate_reports(model,static,digest):
    validate_text_cases(model, static, digest, ['EDK2 GO', 'UEFI 42'], EXPECTED_RASTER)


def validate_text_cases(model, static, digest, lines, raster, *, profile='DXE-TEXT', later=None):
    later = later or {}
    outcomes = {**OUTCOMES, **later}
    validate_gop_cases(model,static,digest,profile,outcomes)
    require(set(model['textSymbols'])=={'TextOutputString','TextQuery','GoTextConsole'},'Missing text entry points')
    for row in model['cases']:
        case = row['case']
        if case in outcomes:
            lo,hi=(int(n,16) for n in row['gopText'])
            base=int(row['gopImageBase'],16)
            require(all(lo<=base+n<hi for n in model['textSymbols'].values()) and
                    base<=int(row['textInterfaceOffered'],16)<base+row['gopImageBytes'],
                    'Text interface and methods must belong to the display image')
        if case in POSITIVE or case in later:
            require(row['glyphUploads']==2*sum(map(len,lines)) and row['eyesMatch'] is True and row['consoleCrcVerified'] is True
                    and row['textLines']==lines and row['outputStringReturns']==[0,0]
                    and row['eyeRgbSha256']==raster and re.fullmatch('[a-f0-9]{64}',row['eyePngSha256'])
                    and int(row['displayHandle'],16)!=0,
                    'Text observation differs')
        else:
            require('eyeRgbSha256' not in row and 'glyphUploads' not in row,'Unexpected text after a fault')
            if case=='text-blt-error':
                require(row['glyphUploadsAttempted']==1,'First failed upload was not propagated')


def reviewed_inputs(root, review):
    verify_captures(root, review)
    return verify_terminal_inputs(root,review,scope='terminal-edk2-dxe-text',build_prefix='DEBUG-DXE_TEXT-',
                                  sec_sources=SOURCES,required=REQUIRED,previous_record=PREVIOUS,
                                  validate_reports=validate_reports)


def verify_captures(root, review, field='eyePngSha256'):
    model_path,model_data = checked_file(root,review['model'],('build',))
    capture_digests = {row['el']:row[field] for row in json.loads(model_data)['cases'] if row['case']=='valid'}
    captures = review['eyeCaptures']
    require(len(captures)==2,'Both EL captures are required')
    for el,record in enumerate(captures,1):
        path,data = checked_file(root,record,('build',))
        require(path == model_path.parent/f'eye-el{el}.png' and
                sha(data)==capture_digests[el] and len(data)==record['size'], 'Unexpected console capture')


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root,LEDGER,image,tool,serial,preflight,report,output)


if __name__=='__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'dxe-text', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
