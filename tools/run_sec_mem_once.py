"""Check the SEC_MEM experiment offline or send its reviewed image once from stock Fastboot.

Live mode belongs to a later, owner-attended Windows session. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json
from pathlib import Path
import re
import subprocess
import zlib

from attended_terminal import attended_main, measure_once
from android_boot import DTB_SHA, HEADER, PAGE, verify_container
from run_sec_c_once import capture, check_readback, require
from run_sec_visual_once import checked_file, sha
from verify_fd import verify


ROOT = Path(__file__).resolve().parents[1]
REVIEW = 'docs/evidence/sec-mem-review-20261118.json'
LEDGER = 'local/physical-attempts/sec-mem-20261118.json'
PRIOR_TRIAL = 'docs/evidence/sec-c-transfer-20261118.json'
SEC_SOURCES = {f'OculusGoPkg/SecMem/{name}' for name in ('Entry.S', 'Hob.c', 'Fdt.c')}
REQUIRED_SOURCES = SEC_SOURCES | {
    'OculusGoPkg/SecMem/SecMem.inf', 'OculusGoPkg/OculusGoPkg.dsc', 'OculusGoPkg/OculusGoPkg.fdf',
    'scripts/build.sh', 'tests/sec_mem_qemu.py', 'tests/sec_mem_static.py', 'tests/sec_mem_fdt_host.py',
    'tests/sec_c_qemu.py', 'tests/entry_harness.S', 'tests/sec_visual_mmu_el1.S',
    'tools/verify_sec_visual_data.py',
    'tools/android_boot.py', 'tools/verify_fd.py',
    'tools/audit_build_sources.py', 'tools/collect_readonly_preflight.py', 'tools/inspect_fastboot.py',
    'tools/emulate_entry.py', 'tools/emulate_sec_handoff.py', 'tools/run_sec_visual_once.py',
    'tools/run_sec_c_once.py', 'tools/run_sec_mem_once.py',
}
CAPTURED_FDT_SHA = '0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929'


def validate_model(model, static, fd_sha):
    require(static['result'] == 'PASS-STATIC-SEC-MEM' and model['result'] == 'PASS-QEMU-SEC-MEM'
            and static['fdSha256'] == model['fdSha256'] == fd_sha
            and re.fullmatch(r'[0-9a-f]{64}', model['elfSha256'])
            and model['elfSha256'] == static['elfSha256'], 'Reports do not cover the same FD and SEC ELF')
    require(static['vectorSlots'] == model['physicalVectorTable']['slotsVerified'] == 16,
            'Incomplete exception vector coverage')
    observed = set()
    for row in model['cases']:
        key = row['el'], row['scenario']
        require(type(key[0]) is int and key[0] in (1, 2) and key not in observed,
                'Duplicate or unexpected model case')
        observed.add(key)
        require(type(row['unexpectedCpuRamWrites']) is int and row['unexpectedCpuRamWrites'] == 0
                and all(row[name] is True for name in ('highPoolUnchanged', 'fullSurfaceAndGuardsMatched',
                        'fdOutsideScratchUnchanged', 'fdtAndGuardsUnchanged', 'incomingRegistersRestored')),
                'Model memory footprint failed')
        if key[1] == 'captured-fdt':
            require(row['fdtSha256'] == CAPTURED_FDT_SHA, 'Wrong captured FDT')
        if key[1] in ('valid-fdt', 'captured-fdt'):
            require(row['rejected'] is False and row['hobVerified'] is True and
                    row['highReadAddresses'] == ['0x94000000', '0x97ffffa0'],
                    'Missing successful PHIT or its two measured reads')
        else:
            require(row['rejected'] is True and row['highReadAddresses'] == [],
                    'Invalid input reached a high memory sample')
    expected = {(el, case) for el in (1, 2) for case in
                ('valid-fdt', 'captured-fdt', 'reserved-pool', 'reserved-stack', 'bad-phit',
                 'undefined-instruction', 'relocated', 'dcache', 'wrong-x0', 'bad-magic', 'short-ram')}
    expected.add((1, 'mmu-el1'))
    require(expected <= observed, 'Missing positive or rejection coverage')


def reviewed_inputs(root, review):
    require(review['scope'] == 'terminal-edk2-sec-mem'
            and review['decision'] == 'APPROVED-FOR-ONE-TERMINAL-SEC-MEM-MEASUREMENT'
            and type(review['maxAttempts']) is int and review['maxAttempts'] == 1,
            'Review does not approve one SEC_MEM measurement')
    fd_path, fd = checked_file(root, review['fd'], ('build',))
    image_path, image = checked_file(root, review['image'], ('local',))
    info = verify(fd)
    require(info['secEntryAddress'] == review['entryAddress'] and fd[64:PAGE] == b'\xff' * (PAGE - 64)
            and len(fd) == review['fd']['size'] and len(image) == review['image']['size'],
            'Unexpected entry, occupied header padding or wrong artifact size')
    length = HEADER.unpack_from(image)[1]
    decoder = zlib.decompressobj(31)
    expanded = decoder.decompress(image[PAGE:PAGE + length], len(fd) + 1)
    require(decoder.eof and expanded == fd and sha(decoder.unused_data) == DTB_SHA,
            'Container differs from the reviewed FD and original EVT DTB')
    verify_container(image, fd, decoder.unused_data)
    _, qemu = checked_file(root, review['model'], ('build',))
    _, static = checked_file(root, review['staticAudit'], ('build',))
    validate_model(json.loads(qemu), json.loads(static), info['sha256'])

    audit_path, data = checked_file(root, review['sourceAudit'], ('build',))
    audit = json.loads(data)
    require(fd_path.parent.name.startswith('DEBUG-SEC_MEM-') and audit_path == fd_path.parent / 'SOURCES.json'
            and audit['result'] == 'PASS' and audit['rejected'] == [] and audit['upstreamTreeClean'] is True
            and audit['upstreamInputsTracked'] is True
            and audit['edk2'] == json.loads((root / 'sources.lock.json').read_bytes())['edk2'],
            'Firmware source audit mismatch')
    originals = [r for r in audit['files'] if r['origin'] == 'original-project']
    require(SEC_SOURCES <= {r['file'] for r in originals}, 'Source audit omits SEC_MEM inputs')
    for row in originals:
        checked_file(root, row, ('OculusGoPkg',))
    require(REQUIRED_SOURCES <= {r['file'] for r in review['checkedSourceFiles']},
            'Incomplete reviewed source set')
    for row in review['checkedSourceFiles']:
        checked_file(root, row, ('OculusGoPkg', 'scripts', 'tests', 'tools'))

    _, prior = checked_file(root, review['priorReadback'], ('local',))
    previous = json.loads((root / PRIOR_TRIAL).read_bytes())
    require(sha(prior) == previous['recovery']['reportSha256'],
            'Device identity source differs from the recovered SEC_C unit')
    serial = json.loads(prior)['serial']
    require(re.fullmatch('[A-Za-z0-9]+', serial), 'Invalid previous unit identity')
    return image_path, serial


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output, capture, check_readback)


def main():
    attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, 'sec-mem', measure)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
