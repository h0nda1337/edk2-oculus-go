"""Verify the reviewed DXE memory-services image, with a separate one-use RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import re
import subprocess

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_dxe_once import SEC_SOURCES as PREVIOUS_SOURCES, REQUIRED as PREVIOUS_INPUTS
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-mem-review-20261119.json'
LEDGER = 'local/physical-attempts/dxe-mem-20261119.json'
PREVIOUS = 'docs/evidence/sec-dxe-transfer-20261119.json'
SEC_SOURCES = PREVIOUS_SOURCES | {'OculusGoPkg/DxeCheckpoint/MemoryServices.c'}
REQUIRED = SEC_SOURCES | PREVIOUS_INPUTS | {
    'OculusGoPkg/DxeCheckpoint/MemoryCheckpoint.inf','tests/dxe_memory_trace.py','tests/test_dxe_mem_review.py','tools/run_dxe_mem_once.py'}
OUTCOMES = {
    'TrialMemoryComplete': ('memory',('valid','icache')),
    'TrialMemoryRejected': ('services',('page-witness','pool-witness','map-type')),
    'TrialDxeRejected': ('branch',('bad-module','untested-resource')),
}
EARLY = ('dcache','wrong-x0','relocated','dirty-pool','dirty-guard','arena-readback')


def validate_reports(model, static, digest):
    require(model['result']=='PASS-QEMU-DXE-MEM' and static['result']=='PASS-STATIC-DXE-MEM'
            and model['fdSha256']==static['fdSha256']==digest and model['vectors']['slotsVerified']==16,
            'Unverified FD or vectors')
    for k in ('innerFvSha256','peSha256','secElfSha256','coreElfSha256'):
        require(model[k]==static[k] and re.fullmatch('[0-9a-f]{64}',static[k]),'Invalid '+k)
    cases={k:(terminal,pattern) for terminal,(pattern,group) in OUTCOMES.items() for k in group}
    cases.update({k:('MmuRejected','untouched') for k in EARLY})
    cases['bad-fv']=('MmuRejected','hobs')
    missing={(el,k) for el in (1,2) for k in cases}
    for row in model['cases']:
        k=row['case']
        require((row['el'],k) in missing,'Unexpected case')
        missing.remove((row['el'],k))
        require((row['terminal'],row['lastPattern'])==cases[k] and row['fullScreenAndGuardsMatched'] is True
                and row['unexpectedGuestRamWrites']==row['highPoolAccesses']==0,'Unexpected terminal or footprint')
        if row['terminal']!='MmuRejected':
            require(row['innerFvMatched'] and row['pageTablesMatched']
                    and int(row['entry'],16)==int(row['coreBase'],16)+static['entryRva'],'Unverified handoff')
        if row['terminal'] in ('TrialMemoryComplete','TrialMemoryRejected'):
            lo,hi=(int(s,16) for s in row['freeWindow'])
            pages,pool=int(row['pages'],16),int(row['pool'],16)
            require(row['initReturnedSuccess'] and row['witnessBytes']==8449 and
                    0x80200000<lo<hi<=0x80380000 and lo%4096==hi%4096==0 and
                    lo<=pages<=hi-8192 and pages%4096==0 and lo<=pool<=hi-257 and
                    (pool+257<=pages or pages+8192<=pool),
                    'Missing real allocator observations')
        if k=='untested-resource':
            require(row['resourceRejectedBeforeInit'] is True,'Unqualified resource was accepted')
        if k=='map-type':
            require(row['alteredDescriptorRejected'] is True,'Descriptor control did not reject')
        if row['terminal']=='TrialMemoryComplete':
            a,b=row['mapKeys']
            require(a!=b and row['loaderPagesReturnedToConventional'] and row['freePoolSuccess'],
                    'Missing memory release evidence')
    require(not missing,'Incomplete model coverage')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root,review,scope='terminal-edk2-dxe-memory-services',build_prefix='DEBUG-DXE_MEM-',
                                  sec_sources=SEC_SOURCES,required=REQUIRED,previous_record=PREVIOUS,
                                  validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root,LEDGER,image,tool,serial,preflight,report,output)


if __name__=='__main__':
    try:
        attended_main(ROOT,REVIEW,LEDGER,reviewed_inputs,'dxe-mem',measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
