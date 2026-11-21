"""Validate the exact artifacts of a terminal trial using the guarded FD layout.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json
import re
import zlib

from android_boot import DTB_SHA, HEADER, PAGE, verify_container
from run_sec_c_once import require
from run_sec_visual_once import checked_file, sha
from verify_fd import verify


def verify_terminal_inputs(root, review, *, scope, build_prefix, sec_sources, required, previous_record, validate_reports):
    require(review['scope'] == scope and review['decision'] == 'ONE-ATTENDED-TEMPORARY-BOOT'
            and type(review['maxAttempts']) is int and review['maxAttempts'] == 1, 'Wrong review')
    fd_path, fd = checked_file(root, review['fd'], ('build',))
    image_path, image = checked_file(root, review['image'], ('local',))
    require(fd_path.parent.name.startswith(build_prefix) and len(fd) == review['fd']['size']
            and len(image) == review['image']['size'] and fd[0x3be000:0x3be008] == b'GOSTACK1'
            and fd[64:PAGE] == b'\xff'*(PAGE-64), 'Unexpected diagnostic layout')
    info = verify(fd)
    require(info['secEntryAddress'] == review['entryAddress'], 'Different SEC entry')
    compressed = image[PAGE:PAGE + HEADER.unpack_from(image)[1]]
    decoder = zlib.decompressobj(31)
    require(decoder.decompress(compressed, len(fd)+1) == fd and decoder.eof and sha(decoder.unused_data) == DTB_SHA,
            'Unexpected FD or Pacific EVT tree')
    verify_container(image, fd, decoder.unused_data)
    reports = {}
    for key, filename in [('model','QEMU.json'), ('staticAudit','STATIC.json'), ('sourceAudit','SOURCES.json')]:
        path, raw = checked_file(root, review[key], ('build',))
        require(path == fd_path.parent/filename, f'{key} belongs to a different build')
        reports[key] = json.loads(raw)
    validate_reports(reports['model'], reports['staticAudit'], info['sha256'])
    audit = reports['sourceAudit']
    require(audit['result'] == 'PASS' and audit['rejected'] == [] and audit['upstreamTreeClean'] is True
            and audit['upstreamInputsTracked'] is True and
            audit['edk2'] == json.loads((root/'sources.lock.json').read_bytes())['edk2'], 'Source audit failed')
    originals = [r for r in audit['files'] if r['origin'] in ('original-project','adapted-edk2-font')]
    require({r['file'] for r in originals} == sec_sources, 'Unexpected platform code in SEC')
    require({r['file'] for r in review['checkedSourceFiles']} == required, 'Reviewed inputs incomplete')
    for row in [*originals, *review['checkedSourceFiles']]:
        checked_file(root, row, ('OculusGoPkg','scripts','tests','tools'))
    _, raw = checked_file(root, review['priorReadback'], ('local',))
    previous = json.loads((root/previous_record).read_bytes())
    require(sha(raw) == previous['recovery']['reportSha256'], 'Prior device evidence differs')
    serial = json.loads(raw)['serial']
    require(re.fullmatch('[A-Za-z0-9]+', serial), 'Unexpected prior device identity')
    return image_path, serial
