"""Run the exact approved SEC_VISUAL FD at EL1 with stage-1 translation active.

Usage under Linux/WSL: python3 tests/sec_visual_mmu_el1.py [--report PATH]
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from emulate_entry import Remote
from verify_fd import BASE, verify
from verify_sec_visual_data import band_ranges


def check(condition, message):
    if not condition:
        raise ValueError(message)


def exercise(remote, info):
    remote.command('qSupported:qXfer:features:read+')
    remote.command('qXfer:features:read:target.xml:0,fff')
    remote.command('Hg0')
    remote.command('?')
    remote.set_register(33, 0x3c5)  # EL1h, all asynchronous exceptions masked.
    preserved = {0: 0x82000000, 1: 17, 2: 23, 3: 31, 30: 0x88776655, 31: 0x90010000}
    for reg, value in preserved.items():
        remote.set_register(reg, value)
    remote.set_register(20, BASE)

    sentinels = {0x98000000 - 96: b'\xa5' * 96}
    for first, end in band_ranges():
        for address in (first - 32, first, end - 32, end):
            sentinels[address] = b'\x5a' * 32
    for address, pattern in sentinels.items():
        remote.write(address, pattern)

    check(remote.command(f'Z1,{BASE:x},4') == 'OK', 'Cannot stop at FD header')
    remote.command('c')
    check(remote.register(32) == BASE, 'Translated execution did not reach the header')
    check(remote.command(f'z1,{BASE:x},4') == 'OK', 'Cannot clear header breakpoint')
    active_sctlr = remote.register(22)  # Harness MRS after ISB.
    check(active_sctlr & 0x1005 == 1, 'MMU/cache state differs from test')
    entry = int(info['secEntryAddress'], 16)
    rejected = entry + 0x170  # Self-branch in the specific SHA-bound diagnostic.
    trace = [BASE]
    for _ in range(32):
        check(remote.command('s').startswith(('S', 'T')), 'QEMU did not single-step')
        trace.append(remote.register(32))
        if trace[-1] == rejected:
            break
    check(trace[:3] == [int(a, 16) for a in info['entryBranches']],
          'Header/FV/SEC fetch sequence differs')
    # The final steps in SEC belong to the EL1 SCTLR selection
    # and MMU guard. The D-cache and framebuffer paths must not be visited.
    check(trace[-5:] == [entry + offset for offset in (0x2c, 0x30, 0x38, 0x3c, 0x170)],
          'Did not reject at the MMU guard')
    check(remote.read(rejected, 4) == bytes.fromhex('00000014'), 'Unexpected terminal instruction')
    check(remote.register(11) == active_sctlr, 'SEC did not read the active EL1 SCTLR')
    check(all(remote.register(n) == value for n, value in preserved.items()),
          'Incoming register changed')
    check(all(remote.read(a, len(p)) == p for a, p in sentinels.items()),
          'Stack or display sentinel changed')
    return {'result': 'PASS-QEMU-EL1-MMU-REJECTION', 'fdSha256': info['sha256'],
            'sctlrEl1': hex(active_sctlr), 'pcTrace': [hex(a) for a in trace],
            'sentinelsChecked': len(sentinels), 'argumentsSpLrPreserved': True,
            'physicalExecution': 'UNKNOWN'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    review = json.loads((ROOT / 'docs/evidence/sec-visual-review-20261025.json').read_text())
    fd = ROOT / review['fd']['file']
    data = fd.read_bytes()
    check(hashlib.sha256(data).hexdigest() == review['fd']['sha256'], 'FD hash differs from review')
    info = verify(data)
    with tempfile.TemporaryDirectory() as scratch, socket.socket() as listener:
        temp = Path(scratch)
        obj, image = temp / 'harness.o', temp / 'harness.bin'
        subprocess.run(['aarch64-linux-gnu-gcc', '-c', Path(__file__).with_suffix('.S'),
                        '-o', obj], check=True)
        subprocess.run(['aarch64-linux-gnu-objcopy', '-O', 'binary', obj, image], check=True)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(15)
        port = listener.getsockname()[1]
        command = ['qemu-system-aarch64', '-machine', 'virt,secure=off,virtualization=off',
                   '-accel', 'tcg', '-cpu', 'cortex-a57', '-m', '2048', '-S', '-nodefaults',
                   '-display', 'none', '-serial', 'none', '-monitor', 'none',
                   '-chardev', f'socket,id=debug,host=127.0.0.1,port={port},server=off',
                   '-gdb', 'chardev:debug',
                   '-device', f'loader,file={fd},addr={BASE:#x},force-raw=on',
                   '-device', f'loader,file={image},addr=0x41000000,cpu-num=0,force-raw=on']
        process = subprocess.Popen(command)
        try:
            stream, _ = listener.accept()
            with stream:
                report = exercise(Remote(stream), info)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    result = json.dumps(report, indent=2)
    if args.report:
        with args.report.open('x', encoding='utf-8') as out:
            print(result, file=out)
    print(result)


if __name__ == '__main__':
    main()
