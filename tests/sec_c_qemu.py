"""Exercise the SEC_C image and its in-header stack in QEMU, without a device.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from emulate_entry import Remote
from emulate_sec_handoff import symbols
from verify_fd import BASE, SIZE, verify
from verify_sec_visual_data import FB_BASE, SURFACE_BYTES, band_ranges

RAM_START = 0x40000000  # QEMU virt RAM, local to this test.
STACK_START, STACK_END = 0x800, 0x1000  # Offsets in the Android Image header page.
COOKIE = 0x43434553
GUARD = 64


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def expected_surface(before):
    byte0, byte2 = b'\xff\x00\x00', b'\x00\x00\xff'
    row = b''.join(c * 240 for c in (byte0, b'\xff' * 3, byte0, byte2, bytes(3), byte2))
    result = bytearray(before)
    for first, end in band_ranges():
        band = row * 32
        require(len(band) == end - first, 'Unexpected band geometry')
        offset = GUARD + first - FB_BASE
        result[offset:offset + len(band)] = band
    return result


def until(remote, address):
    require(remote.command(f'Z1,{address:x},4') == 'OK', 'Cannot set breakpoint')
    reply = remote.command('c')
    require(reply.startswith(('T', 'S')) and remote.register(32) == address,
            f'Did not reach expected PC {address:#x}')
    require(remote.command(f'z1,{address:x},4') == 'OK', 'Cannot clear breakpoint')


def exercise(remote, ram, data, sym, el, relocated, dcache):
    load = BASE + (0x100000 if relocated else 0)
    incoming = {0: 0x82000000, 1: 23, 2: 47, 3: 83, 30: 0x55667788, 31: 0x90010000}
    remote.command('qSupported:qXfer:features:read+')
    remote.command('qXfer:features:read:target.xml:0,fff')
    remote.command('Hg0')
    remote.command('?')
    remote.set_register(33, 0x3c0 | (9 if el == 2 else 5))
    for number, value in incoming.items():
        remote.set_register(number, value)
    remote.set_register(18, 4 if dcache else 0)
    remote.set_register(20, load)
    remote.set_register(32, 0x41000000 + (64 if el == 2 else 0))

    fd_offset = load - RAM_START
    screen_offset = FB_BASE - GUARD - RAM_START
    initial = b'\xa5' * (SURFACE_BYTES + 2 * GUARD)
    require(os.pread(ram, SIZE, fd_offset) == data, 'Loaded FD differs at reset')
    require(os.pwrite(ram, initial, screen_offset) == len(initial), 'Cannot seed model screen')
    until(remote, load)
    until(remote, sym['_ModuleEntryPoint'] + load - BASE)

    rejected = relocated or dcache
    if rejected:
        terminal = sym['EntryRejected'] + load - BASE
        until(remote, terminal)
        expected = initial
    else:
        until(remote, sym['SecCCall'])
        until(remote, sym['OculusGoSecColorCheckpoint'])
        require(remote.register(31) == BASE + STACK_END - 48 and
                remote.register(30) == sym['SecCReturn'], 'Unexpected stack or return address at C entry')
        until(remote, sym['SecCReturn'])
        require(remote.register(0) == 1, 'C stack witness failed')
        terminal = sym['SecCComplete']
        until(remote, terminal)
        expected = expected_surface(initial)
    require(remote.read(terminal, 4) == struct.pack('<I', 0x14000000), 'Invalid terminal loop')
    require(all(remote.register(n) == v for n, v in incoming.items()), 'Entry registers changed')
    require(os.pread(ram, len(expected), screen_offset) == expected, 'Screen/guard mismatch')

    after = os.pread(ram, SIZE, fd_offset)
    if rejected:
        require(after == data, 'Rejected entry modified FD')
        extent = None
    else:
        require(after[:STACK_START] == data[:STACK_START] and
                after[STACK_END:] == data[STACK_END:], 'Firmware changed outside its private stack')
        stack = after[STACK_START:STACK_END]
        require(struct.pack('<I', COOKIE) in stack[:-48], 'Missing C local stack witness')
        changed = [i + STACK_START for i, (a, b) in enumerate(zip(stack, data[STACK_START:STACK_END])) if a != b]
        extent = [hex(BASE + min(changed)), hex(BASE + max(changed) + 1)]
    return {'el': el, 'relocated': relocated, 'dataCacheEnabled': dcache, 'rejected': rejected,
            'terminalPc': hex(terminal), 'fdChangedByteExtentExclusive': extent,
            'fullSurfaceAndGuardsMatched': True, 'incomingRegistersRestored': True}


def run_case(fd, harness, temp, data, sym, el, relocated, dcache):
    with tempfile.TemporaryFile(dir=temp) as memory, socket.socket() as listener:
        memory.truncate(2 << 30)  # Sparse host RAM backing; inspect only with the guest stopped.
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(15)
        port = listener.getsockname()[1]
        ram = memory.fileno()
        command = ['qemu-system-aarch64', '-accel', 'tcg', '-cpu', 'cortex-a57', '-m', '2048',
                   '-object', f'memory-backend-file,id=ram,size=2G,mem-path=/proc/self/fd/{ram},share=on',
                   '-machine', f'virt,secure=off,virtualization={"on" if el == 2 else "off"},memory-backend=ram',
                   '-S', '-nodefaults', '-display', 'none', '-serial', 'none', '-monitor', 'none',
                   '-chardev', f'socket,id=debug,host=127.0.0.1,port={port},server=off',
                   '-gdb', 'chardev:debug', '-device', f'loader,file={harness},addr=0x41000000,force-raw=on',
                   '-device', f'loader,file={fd},addr={BASE + (0x100000 if relocated else 0):#x},force-raw=on']
        process = subprocess.Popen(command, pass_fds=(ram,))
        try:
            connection, _ = listener.accept()
            with connection:
                return exercise(Remote(connection), ram, data, sym, el, relocated, dcache)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path, required=True)
    parser.add_argument('--sec-elf', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    fd = args.fd.resolve()
    data = fd.read_bytes()
    info = verify(data)
    require(data[64:STACK_END] == bytes([data[64]]) * (STACK_END - 64)
            and data[64] in (0, 255), 'Header stack overlaps occupied data')
    names = symbols(args.sec_elf)
    bias = int(info['secEntryAddress'], 16) - names['_ModuleEntryPoint']
    sym = {n: bias + names[n] for n in ('_ModuleEntryPoint', 'SecCCall', 'SecCReturn',
           'OculusGoSecColorCheckpoint', 'SecCComplete', 'EntryRejected')}
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        obj, harness = temp / 'entry.o', temp / 'entry.bin'
        subprocess.run(['aarch64-linux-gnu-gcc', '-c', ROOT / 'tests/entry_harness.S', '-o', obj], check=True)
        subprocess.run(['aarch64-linux-gnu-objcopy', '-O', 'binary', obj, harness], check=True)
        cases = [run_case(fd, harness, temp, data, sym, el, reloc, dc)
                 for el in (1, 2) for reloc, dc in ((False, False), (False, True), (True, False))]
    report = {'result': 'PASS-QEMU-SEC-C', 'fdSha256': info['sha256'],
              'elfSha256': hashlib.sha256(args.sec_elf.read_bytes()).hexdigest(),
              'scope': 'Terminal C diagnostic on QEMU virt; physical execution UNKNOWN', 'cases': cases}
    encoded = json.dumps(report, indent=2) + '\n'
    if args.report:
        with args.report.open('x') as stream:
            stream.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
