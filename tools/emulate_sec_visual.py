"""Bounded QEMU tests for the original terminal EDK2 SEC visual profile.

No device access, hardware model, private binary or external Python dependency.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import time

from emulate_entry import Remote
from emulate_sec_handoff import symbols
from verify_fd import BASE, verify
from verify_sec_visual_data import BAND_BYTES, band_ranges, expected_band


def read_chunks(remote, start, size):
    return b''.join(remote.read(start + offset, min(512, size - offset))
                    for offset in range(0, size, 512))


def audit_prefix(elf, data, names, bias):
    start = names['_ModuleEntryPoint']
    end = names['SecVisualComplete'] + 4
    reject = names['EntryRejected']
    text = subprocess.check_output(['aarch64-linux-gnu-objdump', '-d',
        f'--start-address={start}', f'--stop-address={end}',
        str(elf)], text=True)
    instructions = {}
    for line in text.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$', line)
        if match:
            address = int(match[1], 16)
            if struct.unpack_from('<I', data, bias + address - BASE)[0] != int(match[2], 16):
                raise RuntimeError('ELF and FD disagree within the diagnostic prefix')
            instructions[address] = (match[3], match[4].split('//', 1)[0].strip())
    if set(instructions) != set(range(start, end, 4)):
        raise RuntimeError('Incomplete diagnostic instruction decoding')
    stores = []
    edges = {}
    reads = []
    for address, (opcode, operands) in instructions.items():
        if opcode in ('b', 'b.eq', 'b.ne', 'b.cc'):
            target = int(operands.split()[0], 16)
            if target not in instructions and target != reject:
                raise RuntimeError('Diagnostic branch leaves its reviewed terminal paths')
            edges[address] = [target] + ([] if opcode == 'b' else [address + 4])
        else:
            edges[address] = [address + 4]
            if opcode == 'strb':
                if operands not in ('w9, [x15], #1', 'w10, [x15], #1', 'w11, [x15], #1'):
                    raise RuntimeError('Unexpected diagnostic store operand')
                stores.append(address)
            elif opcode == 'ldr':
                match = re.fullmatch(r'x(?:11|15|16), ([0-9a-f]+) <[^>]+>', operands)
                if not match:
                    raise RuntimeError('Diagnostic load is not a reviewed in-image literal')
                target = bias + int(match[1], 16)
                if not BASE <= target <= BASE + len(data) - 8:
                    raise RuntimeError('Literal read escapes the FD')
                literal = struct.unpack_from('<Q', data, target - BASE)[0]
                if literal not in {0xFF00FFFFFF, 0x80088000, *(a for a, _ in band_ranges())}:
                    raise RuntimeError('Unexpected diagnostic literal value')
                reads.append(target)
            elif opcode == 'mrs':
                if operands not in ('x9, currentel', 'x10, mpidr_el1',
                                     'x11, sctlr_el1', 'x11, sctlr_el2'):
                    raise RuntimeError('Unexpected system-register read')
            elif opcode == 'msr':
                if operands != 'daifset, #0xf':
                    raise RuntimeError('Unexpected system-register write')
            elif opcode == 'dsb':
                if operands != 'sy':
                    raise RuntimeError('Unexpected barrier')
            elif opcode not in ('cmp', 'tst', 'adr', 'mov', 'add', 'subs'):
                raise RuntimeError(f'Unreviewed instruction in diagnostic: {opcode}')
    visited = set()
    pending = [start]
    while pending:
        address = pending.pop()
        if address == reject or address in visited:
            continue
        if address not in instructions:
            raise RuntimeError('Diagnostic can fall through outside its prefix')
        visited.add(address)
        pending.extend(edges[address])
    if len(stores) != 3 or not set(stores).issubset(visited):
        raise RuntimeError('Expected exactly three reachable byte-store instructions')
    return {'decodedInstructions': len(instructions), 'reachableInstructions': len(visited),
            'storeInstructions': [hex(bias + address) for address in stores],
            'literalReadsWithinFd': [hex(address) for address in reads],
            'noCallsOrIndirectBranches': True,
            'noPathToStackCOrDrivers': True,
            'normalControlFlowOnly': True,
            'prefixSha256': hashlib.sha256(data[bias + start - BASE:bias + end - BASE]).hexdigest()}


def one_case(qemu, fd, harness, output, names, bias, el, icache=False,
             data_cache=False, relocated=False, debug_mask=True):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    load = BASE + (0x100000 if relocated else 0)
    delta = load - BASE
    rejected = bias + delta + names['EntryRejected']
    complete = bias + delta + names['SecVisualComplete']
    name = f'el{el}-i{int(icache)}-c{int(data_cache)}-reloc{int(relocated)}-d{int(debug_mask)}'
    command = [qemu, '-machine',
        f'virt,secure=off,virtualization={"on" if el == 2 else "off"}',
        '-cpu', 'cortex-a57', '-m', '2048', '-S', '-nodefaults',
        '-display', 'none', '-serial', 'none', '-monitor', 'none',
        '-gdb', f'tcp:127.0.0.1:{port}',
        '-device', f'loader,file={fd},addr={load:#x},force-raw=on',
        '-device', f'loader,file={harness},addr=0x41000000,force-raw=on']
    with (output / f'{name}.qemu.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        stream = None
        try:
            deadline = time.monotonic() + 15
            while stream is None:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f'QEMU startup failed: {name}')
                try:
                    stream = socket.create_connection(('127.0.0.1', port), timeout=1)
                except OSError:
                    time.sleep(0.03)
            remote = Remote(stream)
            remote.command('qSupported:qXfer:features:read+')
            remote.command('qXfer:features:read:target.xml:0,fff')
            remote.command('Hg0')
            remote.command('?')
            incoming = (0x82000000, 0x1122334455667788, 0xAABBCCDD, 0x99887766)
            for number, initial in enumerate(incoming):
                remote.set_register(number, initial)
            remote.set_register(33, (0x3C0 if debug_mask else 0x1C0) | (9 if el == 2 else 5))
            remote.set_register(31, 0x90010000)
            remote.set_register(30, 0x8877665544332210)
            remote.set_register(18, (0x1000 if icache else 0) | (4 if data_cache else 0))
            remote.set_register(20, load)
            remote.set_register(32, 0x41000000 + (64 if el == 2 else 0))
            stack_record = 0x98000000 - 96
            remote.write(stack_record, b'\xa5' * 96)
            guards = []
            for start, end in band_ranges():
                for address in (start - 64, end):
                    remote.write(address, b'\x5a' * 64)
                    guards.append(address)
                # Initialize the whole allowed write range to detect short fills.
                for offset in range(0, BAND_BYTES, 512):
                    remote.write(start + offset, b'\xa5' * min(512, BAND_BYTES - offset))
            for address in (rejected, complete):
                if remote.command(f'Z1,{address:x},4') != 'OK':
                    raise RuntimeError('Cannot install terminal breakpoint')
            remote.command('c')
            pc = remote.register(32)
            expect_reject = data_cache or relocated
            if pc != (rejected if expect_reject else complete):
                raise RuntimeError(f'Unexpected terminal PC: {name}: {pc:#x}')
            if tuple(remote.register(i) for i in range(4)) != incoming:
                raise RuntimeError('Diagnostic clobbered incoming x0-x3')
            if remote.register(31) != 0x90010000 or remote.register(30) != 0x8877665544332210:
                raise RuntimeError('Diagnostic changed SP/LR')
            if remote.read(stack_record, 96) != b'\xa5' * 96:
                raise RuntimeError('Diagnostic wrote a stack record')
            if any(remote.read(address, 64) != b'\x5a' * 64 for address in guards):
                raise RuntimeError('Band boundary sentinel changed')
            desired = b'\xa5' * BAND_BYTES if expect_reject else expected_band()
            for start, _ in band_ranges():
                if read_chunks(remote, start, BAND_BYTES) != desired:
                    raise RuntimeError('Diagnostic pattern/guard mismatch')
            if struct.unpack('<I', remote.read(pc, 4))[0] != 0x14000000:
                raise RuntimeError('Terminal instruction is not B-to-self')
            return {'case': name, 'result': 'PASS', 'rejected': expect_reject,
                    'terminalPc': hex(pc), 'argumentsPreserved': True,
                    'stackUntouched': True, 'boundarySentinelsIntact': True,
                    'bandsVerified': 2, 'bytesChanged': 0 if expect_reject else BAND_BYTES * 2}
        finally:
            if stream:
                stream.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path, required=True)
    parser.add_argument('--sec-elf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = args.fd.read_bytes()
    info = verify(data)
    if int(info['secEntryAddress'], 16) != 0x80088000:
        raise SystemExit('Diagnostic PC guard and linked entry disagree')
    names = symbols(args.sec_elf.resolve())
    if 'SecVisualComplete' not in names:
        raise SystemExit('This is not the terminal SEC visual profile')
    bias = int(info['secEntryAddress'], 16) - names['_ModuleEntryPoint']
    terminal = bias + names['SecVisualComplete']
    if struct.unpack_from('<I', data, terminal - BASE)[0] != 0x14000000:
        raise SystemExit('Terminal loop differs in the supplied FD')
    prefix = audit_prefix(args.sec_elf.resolve(), data, names, bias)
    args.output.mkdir(parents=True, exist_ok=False)
    obj = args.output / 'harness.o'
    harness = (args.output / 'harness.bin').resolve()
    subprocess.run(['aarch64-linux-gnu-gcc', '-c', root / 'tests/entry_harness.S', '-o', obj], check=True)
    subprocess.run(['aarch64-linux-gnu-objcopy', '-O', 'binary', obj, harness], check=True)
    qemu = shutil.which('qemu-system-aarch64')
    if not qemu:
        raise SystemExit('QEMU is required')
    cases = []
    for el in (1, 2):
        for icache in (False, True):
            for debug_mask in (False, True):
                cases.append(one_case(qemu, args.fd.resolve(), harness, args.output,
                                      names, bias, el, icache=icache, debug_mask=debug_mask))
        cases.append(one_case(qemu, args.fd.resolve(), harness, args.output,
                              names, bias, el, data_cache=True))
        cases.append(one_case(qemu, args.fd.resolve(), harness, args.output,
                              names, bias, el, relocated=True))
    report = {'result': 'PASS-EMULATOR-ONLY',
              'fdSha256': hashlib.sha256(data).hexdigest(), 'prefixAudit': prefix, 'cases': cases,
              'scope': 'Actual integrated header/FV/SEC; terminal pre-stack RAM bands; no C/MMU/DXE or Go peripheral model',
              'physicalExecution': 'UNKNOWN', 'deviceExecutionCleared': False}
    (args.output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n',
                                           encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
