"""Review the half-turn console candidate or boot it once in an attended session."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from pathlib import Path
import json
import subprocess

from attended_terminal import attended_main, measure_once
from run_dxe_text_once import POSITIVE, REQUIRED as TEXT_INPUTS, SOURCES, validate_text_cases, verify_captures
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/dxe-text-upright-review-20261120.json'
LEDGER = 'local/physical-attempts/dxe-text-upright-20261120.json'
PREVIOUS = 'docs/evidence/dxe-text-transfer-20261120.json'
REQUIRED = TEXT_INPUTS | {'tools/run_dxe_text_upright_once.py', 'tests/text_scroll_qemu.c',
                          'scripts/test-text-scroll-qemu.sh'}
LINES = ['1 EDK2 GO 2', '3 UEFI 42 4']
EYE_RGB = '6b62c0ea0c40948228216ccc00ac275b8ee97f9fe36dc3aba589cc4cbb513da6'
NATIVE_BGR = '4f94cc2d104d32e5d99ac6544e70fdaf723c5e35ad7dae4aaadd2c79b2ce5bb8'


def validate_reports(model, static, digest):
    validate_text_cases(model, static, digest, LINES, EYE_RGB)
    for row in model['cases']:
        if row['case'] in POSITIVE:
            require(row.get('nativeBgrSha256') == NATIVE_BGR, 'Incorrect native scanout orientation')


def reviewed_inputs(root, review):
    prior = json.loads((root/PREVIOUS).read_bytes())
    require(review['image']['sha256'] != prior['imageSha256'] and review['fd']['sha256'] != prior['fdSha256'],
            'Expected a distinct corrected image')
    verify_captures(root, review)
    return verify_terminal_inputs(root, review, scope='terminal-edk2-dxe-text-upright', build_prefix='DEBUG-DXE_TEXT-',
                                  sec_sources=SOURCES, required=REQUIRED, previous_record=PREVIOUS,
                                  validate_reports=validate_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == '__main__':
    try:
        attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'dxe-text-upright', measure)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
