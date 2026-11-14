"""Run the exact direct FD through SEC, optionally through the TrustMeBro driver.

QEMU only, without a board profile replacement or any device communication.
The callsite is pinned to this first FD; a different build requires review.
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
import uuid

from emulate_entry import Remote
from verify_fd import BASE, verify

REVIEWED_FDS = {
    'a4acf898e51a814ad6ed4c84a9dacd8788120ad272c3fa528fb0b7579b698230': 0x6A34,
    # Only two generated DebugAssert line operands changed; callsites unchanged.
    '72f602d2eec7d2bff0117bf8d8370218e47ef22fbd7023ab42b3497af9294e58': 0x6A34,
}
ENTRY_GUID = uuid.UUID('6140ad32-c38e-4296-8d6b-2842463c22c1').bytes_le


def symbols(elf):
    text = subprocess.check_output(['aarch64-linux-gnu-nm', '-n', elf], text=True)
    return {parts[2]: int(parts[0], 16) for line in text.splitlines()
            if len(parts := line.split()) == 3}


def read_hobs(remote, address, target):
    if not 0x94000000 <= address < 0x97FC0000 or address % 8:
        raise RuntimeError('Invalid DXE HOB-list pointer')
    result = {'resources': [], 'firmwareVolumes': [], 'entry': None, 'dxeModule': None}
    for _ in range(512):
        kind, length, reserved = struct.unpack('<HHI', remote.read(address, 8))
        if kind == 0xFFFF:
            if result['entry'] is None or result['dxeModule'] is None:
                raise RuntimeError('Required SEC state or DXE module HOB missing')
            return result
        if length < 8 or length % 8 or address + length > 0x97FC0000 or reserved:
            raise RuntimeError('Malformed HOB')
        data = remote.read(address, length)
        if kind == 4 and data[8:24] == ENTRY_GUID:
            if length != 120:
                raise RuntimeError('Entry HOB size mismatch')
            state = struct.unpack('<IHH10QII', data[24:])
            if state[:3] != (0x31424D54, 1, 96) or state[13:] != (3, 0):
                raise RuntimeError('Entry HOB ABI/phase mismatch')
            result['entry'] = {'phase': state[13], 'currentEl': state[7],
                'fdt': hex(state[3]), 'originalX1': hex(state[4]),
                'originalX2': hex(state[5]), 'originalX3': hex(state[6])}
        elif kind == 3:
            resource_type, attributes, start, size = struct.unpack_from('<IIQQ', data, 24)
            result['resources'].append({'type': resource_type, 'base': hex(start), 'size': hex(size)})
        elif kind == 5:
            start, size = struct.unpack_from('<QQ', data, 8)
            result['firmwareVolumes'].append({'base': hex(start), 'size': hex(size)})
        elif kind == 2 and length == 72:
            base, size = struct.unpack_from('<QQ', data, 24)
            entry = struct.unpack_from('<Q', data, 64)[0]
            if entry == target and base <= target < base + size:
                result['dxeModule'] = {'base': hex(base), 'size': hex(size), 'entry': hex(entry)}
        address += length
    raise RuntimeError('HOB traversal exceeded bound')


def check_protocol(remote, dxe_base, dxe_names, return_stop):
    guid = uuid.UUID('4b7e5f2a-196d-47cc-b81f-54914a3e9d70').bytes_le
    install = dxe_base + dxe_names['CoreInstallMultipleProtocolInterfaces']
    assertion = dxe_base + dxe_names['DebugAssert']
    for address in (install, assertion):
        if remote.command(f'Z1,{address:x},4') != 'OK':
            raise RuntimeError('DXE breakpoint installation failed')
    for _ in range(128):
        remote.command('c')
        pc = remote.register(32)
        if pc != install:
            raise RuntimeError(f'DXE stopped before TrustMeBro install: {pc:#x}')
        pointer = remote.register(1)
        if pointer and remote.read(pointer, 16) == guid:
            interface = remote.register(2)
            handle_pointer = remote.register(0)
            caller = remote.register(30)
            remote.command(f'Z1,{caller:x},4')
            remote.command('s')
            remote.command('c')
            if remote.register(32) != caller or remote.register(0) != 0:
                raise RuntimeError('TrustMeBro installation did not return EFI_SUCCESS')
            handle = struct.unpack('<Q', remote.read(handle_pointer, 8))[0]
            if handle == 0:
                raise RuntimeError('Installed protocol has no handle')
            break
        remote.command('s')
    else:
        raise RuntimeError('TrustMeBro installation not observed')
    revision, get_state = struct.unpack('<QQ', remote.read(interface, 16))
    if revision != 0x10000:
        raise RuntimeError('Protocol revision mismatch')

    def invoke(function, arguments):
        for register, value in enumerate(arguments):
            remote.set_register(register, value)
        remote.set_register(30, return_stop)
        remote.set_register(32, function)
        remote.command('c')
        if remote.register(32) != return_stop:
            raise RuntimeError('Diagnostic protocol call did not return normally')
        return remote.register(0)

    # These scratch addresses exist solely in emulated RAM, outside the pool.
    scratch = 0x91800000
    remote.write(scratch + 0x120, guid)
    remote.write(scratch + 0x100, bytes(8))
    status = invoke(dxe_base + dxe_names['CoreLocateProtocol'],
                    (scratch + 0x120, 0, scratch + 0x100))
    if status != 0 or struct.unpack('<Q', remote.read(scratch + 0x100, 8))[0] != interface:
        raise RuntimeError('Boot-services LocateProtocol did not find TrustMeBro')
    remote.write(scratch, bytes(8))
    if invoke(get_state, (interface, scratch, 0)) != 0x8000000000000005:
        raise RuntimeError('GetState size query status mismatch')
    if struct.unpack('<Q', remote.read(scratch, 8))[0] != 96:
        raise RuntimeError('GetState size query length mismatch')
    remote.write(scratch + 0x10, b'\xa5' * 96)
    if invoke(get_state, (interface, scratch, scratch + 0x10)) != 0:
        raise RuntimeError('GetState failed')
    state = struct.unpack('<IHH10QII', remote.read(scratch + 0x10, 96))
    if state[:3] != (0x31424D54, 1, 96) or state[13:] != (4, 0):
        raise RuntimeError('GetState did not report the DXE checkpoint')
    if state[3:7] != (0x82000000, 0x1122334455667788, 0xAABBCCDD, 0x99887766):
        raise RuntimeError('Protocol lost the original entry arguments')
    return {'installed': True, 'locateProtocol': 'PASS', 'getStateSizeQuery': 'PASS',
            'getState': 'PASS', 'phase': state[13], 'revision': hex(revision),
            'currentEl': state[7], 'interface': hex(interface)}


def run_case(qemu, fd, harness, output, el, stops, handoff, dxe_names):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    command = [qemu, '-machine', f'virt,secure=off,virtualization={"on" if el == 2 else "off"}',
        '-cpu', 'cortex-a57', '-m', '2048', '-S', '-nodefaults', '-display', 'none',
        '-serial', 'none', '-monitor', 'none', '-gdb', f'tcp:127.0.0.1:{port}',
        '-device', f'loader,file={fd},addr={BASE:#x},force-raw=on',
        '-device', f'loader,file={harness},addr=0x41000000,force-raw=on']
    with (output / f'el{el}.qemu.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        connection = None
        try:
            deadline = time.monotonic() + 15
            while connection is None:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('QEMU startup failed')
                try:
                    connection = socket.create_connection(('127.0.0.1', port), timeout=1)
                except OSError:
                    time.sleep(0.03)
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            remote = Remote(connection)
            remote.command('qSupported:qXfer:features:read+')
            remote.command('qXfer:features:read:target.xml:0,fff')
            remote.command('Hg0')
            remote.command('?')
            for number, value in enumerate((0x82000000, 0x1122334455667788, 0xAABBCCDD, 0x99887766)):
                remote.set_register(number, value)
            remote.set_register(33, 0x3C9 if el == 2 else 0x3C5)
            remote.set_register(31, 0x90010000)
            remote.set_register(18, 0)
            remote.set_register(20, BASE)
            remote.set_register(32, 0x41000000 + (64 if el == 2 else 0))
            for address in (*stops, handoff):
                if remote.command(f'Z1,{address:x},4') != 'OK':
                    raise RuntimeError('Cannot install QEMU breakpoint')
            remote.command('c')
            pc = remote.register(32)
            if pc != handoff:
                raise RuntimeError(f'SEC stopped before handoff: EL{el}, pc={pc:#x}')
            target = remote.register(24)
            hob_list = remote.register(0)
            if not 0x94000000 <= target < 0x97FC0000:
                raise RuntimeError('DXE target outside the allocation pool')
            hobs = read_hobs(remote, hob_list, target)
            entry = hobs['entry']
            if (entry['currentEl'] != el * 4 or entry['fdt'] != '0x82000000' or
                entry['originalX1'] != '0x1122334455667788' or
                entry['originalX2'] != '0xaabbccdd' or entry['originalX3'] != '0x99887766'):
                raise RuntimeError('Entry arguments did not survive SEC')
            if len(hobs['firmwareVolumes']) < 2:
                raise RuntimeError('No decompressed inner FV HOB')
            remote.command('s')
            if remote.register(32) != target or remote.register(0) != hob_list:
                raise RuntimeError('DXE transfer did not preserve HOB argument')
            protocol = None
            if dxe_names is not None:
                bias = target - dxe_names['_ModuleEntryPoint']
                protocol = check_protocol(remote, bias, dxe_names, stops[0])
                if protocol['currentEl'] != el * 4:
                    raise RuntimeError('Protocol CurrentEL does not match entry')
            return {'el': el, 'result': 'PASS', 'handoffPc': hex(pc),
                'dxeEntryReached': hex(target), 'hobList': hex(hob_list), 'hobs': hobs,
                'trustMeBro': protocol,
                'scope': ('SEC and DXE through TrustMeBro LocateProtocol/GetState; stop before board driver dispatch'
                          if protocol else 'SEC C, memory setup, inner FV decompression, DXE loading and entry; stop before DXE instructions')}
        finally:
            if connection:
                connection.close()
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
    parser.add_argument('--dxe-elf', type=Path,
                        help='Also run DXE through original TrustMeBro protocol installation')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fd = args.fd.resolve()
    data = fd.read_bytes()
    info = verify(data)
    fd_sha = hashlib.sha256(data).hexdigest()
    if fd_sha not in REVIEWED_FDS:
        raise SystemExit('Review callsites for this different FD first')
    names = symbols(args.sec_elf.resolve())
    bias = int(info['secEntryAddress'], 16) - names['_ModuleEntryPoint']
    handoff = bias + REVIEWED_FDS[fd_sha]  # BLR x24, LoadDxeCoreFromFfsFile inlined.
    if struct.unpack_from('<I', data, handoff - BASE)[0] != 0xD63F0300:
        raise SystemExit('Reviewed BLR x24 callsite mismatch')
    stops = [bias + names[name] for name in
             ('EntryRejected', 'EntryException', 'DebugAssert', 'CpuDeadLoop')]
    args.output.mkdir(parents=True, exist_ok=False)
    obj = args.output / 'harness.o'
    harness = (args.output / 'harness.bin').resolve()
    subprocess.run(['aarch64-linux-gnu-gcc', '-c', root / 'tests/entry_harness.S', '-o', obj], check=True)
    subprocess.run(['aarch64-linux-gnu-objcopy', '-O', 'binary', obj, harness], check=True)
    dxe_names = symbols(args.dxe_elf.resolve()) if args.dxe_elf else None
    cases = [run_case(shutil.which('qemu-system-aarch64'), fd, harness, args.output,
                      el, stops, handoff, dxe_names) for el in (1, 2)]
    report = {'result': 'PASS', 'fdSha256': fd_sha, 'cases': cases,
        'physicalExecution': 'UNKNOWN', 'boardHardwareValidation': 'NOT-PERFORMED'}
    (args.output / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
