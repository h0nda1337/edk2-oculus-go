"""Check the DXE_TABLES evidence offline or run one attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path
import subprocess

from attended_terminal import attended_main, measure_once
from run_dxe_gcd_once import OUTCOMES as GCD_OUTCOMES, REQUIRED as GCD_INPUTS, SOURCES as GCD_SOURCES, validate_gcd_cases
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-tables-review-20261119.json'
LEDGER = 'local/physical-attempts/dxe-tables-20261119.json'
PREVIOUS = 'docs/evidence/dxe-gcd-transfer-20261119.json'
SOURCES = GCD_SOURCES | {'OculusGoPkg/DxeCheckpoint/ConfigTables.c'}
REQUIRED = GCD_INPUTS | SOURCES | {'OculusGoPkg/DxeCheckpoint/TablesCheckpoint.inf',
    'tools/run_dxe_tables_once.py', 'tests/dxe_tables_trace.py', 'tests/test_dxe_tables_review.py'}
CTORS = {'BaseDebugLibSerialPortConstructor', 'UefiRuntimeServicesTableLibConstructor',
         'UefiBootServicesTableLibConstructor', 'UefiLibConstructor', 'DxeExtractGuidedSectionLibConstructor'}
DXE = '05ad34ba-6f02-4214-952e-4da0398e2bb9'
HOB = '7739f24c-93d7-11d4-9a3a-0090273fc14d'
TYPES = '4c19049f-4137-4dd3-9c10-8b97a83ffdfa'
TABLE_CASES = {
    'valid': ('TrialTablesComplete','tables'), 'icache': ('TrialTablesComplete','tables'),
    'table-order': ('TrialTablesComplete','tables'), 'ctor-cache': ('TrialConstructorsRejected','gcd'),
    'config-count': ('TrialTablesRejected','ctors'), 'dxe-pointer': ('TrialTablesRejected','ctors'),
    'hob-source': ('TrialTablesRejected','dxe-table'), 'hob-content': ('TrialTablesRejected','dxe-table'),
    'duplicate-guid': ('TrialTablesRejected','dxe-table')}


def validate_reports(model, static, digest):
    validate_table_cases(model, static, digest, 'DXE-TABLES', TABLE_CASES)


def validate_table_cases(model, static, digest, profile, table_cases):
    validate_gcd_cases(model, static, digest, profile, {**GCD_OUTCOMES, **table_cases})
    ctors = static['constructors']
    require(len(ctors) == len(CTORS) and set(ctors) == CTORS and model['constructors'] == ctors,
            'Unexpected constructors in the linked core')
    for row in model['cases']:
        case = row['case']
        if case not in table_cases:
            continue
        statuses = row['constructorStatuses']
        require(list(statuses) == ctors and all(type(s) is int and s == 0 for s in statuses.values())
                and row['libraryCachesVerified'] is True, 'Missing successful constructor returns')
        if case == 'ctor-cache':
            continue
        entries = row['installedByGuid']
        base = int(row['coreBase'],16)
        end = base + static['peImageBytes']
        array = int(row['configurationTable'],16)
        require(row['entryCountsAfterInstall'] == [1,2,3] and set(entries) == {DXE,HOB,TYPES} and
                0x80200000 <= array <= 0x80380000-72 and array%8 == 0 and
                entries[HOB] == row['relocatedHobs'] and entries[DXE] == row['dxeServices'] and
                base <= int(entries[DXE],16) < end and base <= int(entries[TYPES],16) < end and
                len(set(entries.values())) == 3, 'Invalid configuration table publication')
        if case in ('config-count','dxe-pointer'):
            continue
        require(row['queryThroughPublishedServices'] is True, 'Missing GCD query via EFI System Table')
        if case in ('valid','icache','table-order'):
            require(row['tableLookupOrderIndependentControl'] is (case == 'table-order'),
                    'Wrong reordered-entry observation')


def reviewed_inputs(root, review):
    return verify_terminal_inputs(root, review, scope='terminal-edk2-dxe-constructors-tables',
                                  build_prefix='DEBUG-DXE_TABLES-', sec_sources=SOURCES, required=REQUIRED,
                                  previous_record=PREVIOUS, validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'dxe-tables', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
