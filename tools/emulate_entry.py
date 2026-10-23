"""Bounded direct-FD entry tests using QEMU's GDB protocol, no third-party Python.

Stops before the first BL; does not test C, MMU tables, DXE or Go peripherals.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import time

from verify_fd import BASE, verify


class Remote:
    def __init__(self, stream):
        self.stream = stream
        stream.settimeout(10)

    def byte(self):
        item = self.stream.recv(1)
        if not item:
            raise RuntimeError('QEMU disconnected')
        return item

    def command(self, text):
        raw = text.encode('ascii')
        self.stream.sendall(b'$' + raw + b'#' + f'{sum(raw) & 255:02x}'.encode())
        while self.byte() != b'$':
            pass
        packet = bytearray()
        while True:
            char = self.byte()
            if char == b'#':
                break
            packet.extend(char)
        expected = int(self.byte() + self.byte(), 16)
        if expected != sum(packet) & 255:
            raise RuntimeError('GDB checksum mismatch')
        self.stream.sendall(b'+')
        if b'*' in packet or b'}' in packet:
            raise RuntimeError('Unexpected encoded GDB response')
        return packet.decode('ascii')

    def set_register(self, number, value):
        width = 4 if number == 33 else 8
        if self.command(f'P{number:x}={value.to_bytes(width, "little").hex()}') != 'OK':
            raise RuntimeError(f'Cannot set register {number}')

    def register(self, number):
        result = self.command(f'p{number:x}')
        return int.from_bytes(bytes.fromhex(result), 'little')

    def read(self, address, length):
        result = self.command(f'm{address:x},{length:x}')
        data = bytes.fromhex(result)
        if len(data) != length:
            raise RuntimeError('Truncated target memory read')
        return data

    def write(self, address, data):
        if self.command(f'M{address:x},{len(data):x}:{data.hex()}') != 'OK':
            raise RuntimeError('Cannot initialize target memory')


def one_case(qemu, fd, harness, output, el, icache, debug_mask, reject):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    command = [qemu, '-machine', 'virt,virtualization=on,secure=off',
        '-cpu', 'cortex-a57', '-m', '2048', '-S', '-nodefaults',
        '-display', 'none', '-serial', 'none', '-monitor', 'none',
        '-gdb', f'tcp:127.0.0.1:{port}',
        '-device', f'loader,file={fd},addr={BASE:#x},force-raw=on',
        '-device', f'loader,file={harness},addr=0x40080000,force-raw=on']
    name = f'el{el}-i{int(icache)}-d{int(debug_mask)}-reject{int(reject)}'
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
            incoming = [0x82000000, 0x1122334455667788, 0xAABBCCDD, 0x99887766]
            for number, value in enumerate(incoming):
                remote.set_register(number, value)
            daif = 0x3C0 if debug_mask else 0x1C0
            remote.set_register(33, daif | (9 if el == 2 else 5))
            remote.set_register(31, 0x90010000)
            remote.set_register(30, 0x8877665544332210)
            remote.set_register(18, (0x1000 if icache else 0) | (4 if reject else 0))
            remote.set_register(20, BASE)
            remote.set_register(32, 0x40080000 + (64 if el == 2 else 0))
            state_address = 0x98000000 - 96
            remote.write(state_address, b'\xa5' * 96)
            previous = None
            for steps in range(160):
                pc = remote.register(32)
                if BASE <= pc < BASE + 0x400000:
                    instruction = struct.unpack('<I', remote.read(pc, 4))[0]
                    if instruction & 0xFC000000 == 0x94000000:
                        if reject:
                            raise RuntimeError('Rejected cache state reached a library call')
                        state = remote.read(state_address, 96)
                        values = struct.unpack('<IHH10QII', state)
                        if values[:3] != (0x31424D54, 1, 96):
                            raise RuntimeError('SEC record header mismatch')
                        if list(values[3:7]) != incoming or values[7] != el * 4:
                            raise RuntimeError('Original arguments / EL mismatch')
                        if values[9] & 0x1005 != (0x1000 if icache else 0):
                            raise RuntimeError('Active SCTLR snapshot mismatch')
                        if values[10:13] != (daif, 0x90010000, 0x8877665544332210):
                            raise RuntimeError('Initial DAIF/SP/LR not preserved')
                        if values[13:] != (1, 0):
                            raise RuntimeError('SEC phase mismatch')
                        return {'case': name, 'result': 'PASS', 'steps': steps,
                            'stoppedBeforeFirstBl': True, 'snapshotSha256': hashlib.sha256(state).hexdigest()}
                    if previous == pc:
                        if not reject or remote.read(state_address, 96) != b'\xa5' * 96:
                            raise RuntimeError('Unexpected rejection or a store before rejection')
                        return {'case': name, 'result': 'PASS', 'steps': steps,
                            'rejectedWithoutStackStore': True}
                previous = pc
                if not remote.command('s').startswith(('T', 'S')):
                    raise RuntimeError('Unexpected single-step response')
            raise RuntimeError('Entry did not reach a bounded stop')
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
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fd = args.fd.resolve()
    verify(fd.read_bytes())
    qemu = shutil.which('qemu-system-aarch64')
    if not qemu:
        raise SystemExit('QEMU is required')
    args.output.mkdir(parents=True, exist_ok=False)
    obj = args.output / 'harness.o'
    harness = (args.output / 'harness.bin').resolve()
    subprocess.run(['aarch64-linux-gnu-gcc', '-c', root / 'tests/entry_harness.S', '-o', obj], check=True)
    subprocess.run(['aarch64-linux-gnu-objcopy', '-O', 'binary', obj, harness], check=True)
    cases = []
    for el in (1, 2):
        for icache in (False, True):
            for debug_mask in (False, True):
                cases.append(one_case(qemu, fd, harness, args.output, el, icache, debug_mask, False))
        cases.append(one_case(qemu, fd, harness, args.output, el, False, True, True))
    report = {'result': 'PASS', 'fdSha256': hashlib.sha256(fd.read_bytes()).hexdigest(),
        'scope': 'direct header/FV/SEC, stop before first BL; no C/MMU/DXE/peripheral execution',
        'physicalExecution': 'UNKNOWN', 'cases': cases}
    (args.output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
