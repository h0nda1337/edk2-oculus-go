"""Check the SEC_DXE package offline or perform one attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/sec-dxe-review-20261118.json'
LEDGER = 'local/physical-attempts/sec-dxe-20261118.json'
PREVIOUS = 'docs/evidence/sec-mmu-transfer-20261118.json'
SEC_SOURCES = {'OculusGoPkg/SecMmu/'+s for s in ('Entry.S','Layout.h','Tables.c','DxeHandoff.c')} | {
    'OculusGoPkg/DxeCheckpoint/Checkpoint.c','OculusGoPkg/Include/Trial/DxeLayout.h'}
REQUIRED = SEC_SOURCES | {
    'OculusGoPkg/SecMmu/SecDxe.inf','OculusGoPkg/DxeCheckpoint/DxeCheckpoint.inf',
    'OculusGoPkg/OculusGoPkg.dsc','OculusGoPkg/OculusGoPkg.fdf','OculusGoPkg/OculusGoPkg.dec',
    'scripts/build.sh','scripts/build-edk2.ps1','scripts/check-sec-dxe.sh','tools/verify_fd.py','tools/android_boot.py',
    'tools/audit_build_sources.py','tools/collect_readonly_preflight.py','tools/inspect_fastboot.py',
    'tools/run_sec_visual_once.py','tools/run_sec_c_once.py','tools/attended_terminal.py','tools/terminal_review.py',
    'tools/run_sec_dxe_once.py','tools/emulate_entry.py','tools/emulate_sec_handoff.py',
    'tools/verify_sec_visual_data.py','tests/sec_c_qemu.py','tests/entry_harness.S','tests/sec_mem_qemu.py',
    'tests/sec_mmu_qemu.py','tests/sec_dxe_qemu.py','tests/sec_dxe_static.py',
}


def validate_reports(model, static, digest):
    require(model['result']=='PASS-QEMU-SEC-DXE' and static['result']=='PASS-STATIC-SEC-DXE' and
            model['fdSha256']==static['fdSha256']==digest and model['vectors']['slotsVerified']==16,
            'Missing package or vector checks')
    for key in ('innerFvSha256','peSha256','secElfSha256','coreElfSha256'):
        require(re.fullmatch('[0-9a-f]{64}',static[key]) and static[key]==model[key],'Mismatched '+key)
    expected={(el,k) for el in (1,2) for k in
              ('valid','icache','dcache','wrong-x0','relocated','dirty-pool','dirty-guard','bad-fv','bad-module')}
    for row in model['cases']:
        key=row['el'],row['case']
        require(key in expected,'Unexpected model scenario')
        expected.remove(key)
        positive=key[1] in ('valid','icache')
        core=positive or key[1]=='bad-module'
        terminal='TrialDxeComplete' if positive else ('TrialDxeRejected' if core else 'MmuRejected')
        pattern='core' if positive else ('branch' if core else ('hobs' if key[1]=='bad-fv' else 'untouched'))
        require(row['terminal']==terminal and row['lastPattern']==pattern and row['fullScreenAndGuardsMatched']
                and row['unexpectedGuestRamWrites']==row['highPoolAccesses']==0,'Unexpected model outcome')
        if core:
            require(row['innerFvMatched'] and row['pageTablesMatched'] and
                    int(row['entry'],16)==int(row['coreBase'],16)+static['entryRva'],'Missing real DXE handoff')
    require(not expected,'Missing cases')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root, review, scope='terminal-edk2-sec-dxe',build_prefix='DEBUG-SEC_DXE-',
                                  sec_sources=SEC_SOURCES,required=REQUIRED,previous_record=PREVIOUS,
                                  validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root,LEDGER,image,tool,serial,preflight,report,output)


if __name__=='__main__':
    try:
        attended_main(ROOT,REVIEW,LEDGER,reviewed_inputs,'sec-dxe',measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
