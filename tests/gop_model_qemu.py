"""Boot the GOP_MODEL FD in QEMU and exercise its installed EFI GOP via AAPCS64.

Run from Linux/WSL: python3 tests/gop_model_qemu.py [--report output.json]
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from emulate_entry import Remote
from emulate_sec_handoff import read_hobs, symbols
from verify_fd import BASE, verify


GOP = uuid.UUID('9042a9de-23dc-4a38-96fb-7aded080516a').bytes_le
TRUST = uuid.UUID('4b7e5f2a-196d-47cc-b81f-54914a3e9d70').bytes_le
FB = 0x83401000
WIDTH, HEIGHT = 1440, 2560
END = FB + WIDTH * HEIGHT * 3
ERROR = 1 << 63
INVALID = ERROR + 2
UNSUPPORTED = ERROR + 3


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def handoff_address(sec_elf, fd, bias):
    # On this pinned upstream revision the non-switching indirect DXE call
    # has source-line information. Match its debug location, not a build offset.
    source = ROOT / 'edk2/EmbeddedPkg/Library/PrePiLib/PrePiLib.c'
    statement = '((DXE_CORE_ENTRY_POINT)(UINTN)EntryPoint)(Hob);'
    lines = [n for n, line in enumerate(source.read_text().splitlines(), 1)
             if line.strip() == statement]
    require(len(lines) == 1, 'Cannot identify upstream DXE handoff statement')
    listing = subprocess.check_output(['aarch64-linux-gnu-objdump', '-dl', sec_elf], text=True)
    site = re.findall(r'/PrePiLib/PrePiLib\.c:' + str(lines[0]) +
                      r'(?: \(discriminator [0-9]+\))?\n\s*([0-9a-f]+):\s+'
                      r'([0-9a-f]{8})\s+blr\s+x(\d+)\b', listing)
    require(len(site) == 1, 'Cannot identify unique BLR in SEC ELF')
    address, word, register = site[0]
    pc = bias + int(address, 16)
    require(struct.unpack_from('<I', fd, pc - BASE)[0] == int(word, 16),
            'SEC ELF and FD differ at DXE handoff')
    return pc, int(register)


def bp(remote, address, add=True):
    command = 'Z1' if add else 'z1'
    require(remote.command(f'{command},{address:x},4') == 'OK', 'Breakpoint failed')


def locate_install(remote, install):
    # Observe the real dispatcher calling the two driver entries. Return only
    # after GOP's installation returned EFI_SUCCESS to its own caller.
    saw_trust = False
    bp(remote, install)
    for _ in range(256):
        remote.command('c')
        pc = remote.register(32)
        require(pc == install, f'DXE stopped at {pc:#x} before GOP installation')
        first_guid = remote.register(1)
        guid = remote.read(first_guid, 16) if first_guid else None
        if guid == TRUST:
            saw_trust = True
        if guid == GOP:
            require(saw_trust, 'Expected TrustMeBro before GOP')
            handle_out, interface, caller = (remote.register(n) for n in (0, 2, 30))
            bp(remote, install, False)
            bp(remote, caller)
            remote.command('c')
            require(remote.register(32) == caller and remote.register(0) == 0,
                    'GOP installation did not return success')
            require(int.from_bytes(remote.read(handle_out, 8), 'little') != 0,
                    'GOP installed on a null handle')
            return interface, caller
        remote.command('s')
    raise RuntimeError('GOP installation not observed')


def exercise(remote, core, interface, caller):
    # Borrow unused stack space below the stopped caller. Function arguments
    # 9 and 10 go at SP; callee stack frames grow down, away from test buffers.
    sp = remote.register(31) - 1024
    require(sp % 16 == 0, 'Misaligned caller stack')
    scratch = sp + 32
    remote.set_register(31, sp)
    checks = []

    def call(label, address, args, expected=0):
        for n, value in enumerate(args[:8]):
            remote.set_register(n, value)
        for n, value in enumerate(args[8:]):
            remote.write(sp + n * 8, struct.pack('<Q', value))
        remote.set_register(30, caller)
        remote.set_register(32, address)
        remote.command('c')
        require(remote.register(32) == caller, f'{label} did not return')
        require(remote.register(0) == expected, f'{label}: EFI status {remote.register(0):#x}')
        require(remote.register(31) == sp, f'{label} did not preserve SP')
        checks.append(label)

    def pixel(x, y):
        return FB + 3 * (y * WIDTH + x)

    remote.write(scratch, GOP)
    call('LocateProtocol', core['CoreLocateProtocol'], (scratch, 0, scratch + 16))
    require(int.from_bytes(remote.read(scratch + 16, 8), 'little') == interface,
            'LocateProtocol returned the wrong GOP instance')
    query, setmode, blt, mode = struct.unpack('<4Q', remote.read(interface, 32))
    max_modes, current, mode_info, info_size, fb_base, fb_size = struct.unpack(
        '<2I4Q', remote.read(mode, 40))
    require((max_modes, current, info_size, fb_base, fb_size) == (1, 0, 36, 0, 0),
            'Unexpected PixelBltOnly mode descriptor')
    call('QueryMode', query, (interface, 0, scratch, scratch + 8))
    size, info = struct.unpack('<QQ', remote.read(scratch, 16))
    require(size == 36 and info != mode_info, 'QueryMode did not return an owned copy')
    expected_info = struct.pack('<9I', 0, WIDTH, HEIGHT, 3, 0, 0, 0, 0, WIDTH)
    require(remote.read(info, size) == remote.read(mode_info, size) == expected_info,
            'Mode geometry/format mismatch')
    call('FreePool-mode-copy', core['CoreFreePool'], (info,))
    call('QueryMode-invalid', query, (interface, 1, scratch, scratch + 8), INVALID)
    call('QueryMode-null-output', query, (interface, 0, 0, scratch + 8), INVALID)

    marks = (FB, pixel(731, 1092), END - 3)
    require(all(remote.read(a, 3) == b'\xa5' * 3 for a in marks),
            'Installing GOP changed inherited pixels')
    call('SetMode-invalid', setmode, (interface, 1), UNSUPPORTED)
    call('SetMode-clear', setmode, (interface, 0))
    require(all(remote.read(a, 3) == bytes(3) for a in marks), 'SetMode failed to clear')

    buf = scratch + 64
    remote.write(buf, bytes.fromhex('1958c3fe'))  # UEFI BLT pixel = B,G,R,reserved
    call('VideoFill', blt, (interface, buf, 0, 0, 0, WIDTH - 2, HEIGHT - 2, 2, 2, 0))
    for y in (HEIGHT - 2, HEIGHT - 1):
        require(remote.read(pixel(WIDTH - 3, y), 9) == bytes(3) + bytes.fromhex('c35819') * 2,
                'Fill pitch, channel order or adjacent pixel mismatch')
    row = bytes.fromhex('030201ff060504ff090807ff')
    remote.write(buf, row)
    call('BufferToVideo-tight-pitch', blt, (interface, buf, 2, 0, 0, 0, 10, 3, 1, 0))
    call('VideoToVideo-horizontal-overlap', blt, (interface, 0, 3, 0, 10, 1, 10, 3, 1, 0))
    require(remote.read(pixel(0, 10), 12) == bytes.fromhex('010203010203040506070809'),
            'Same-row overlapping copy corrupted source pixels')

    # Upload a 3x3 source at nonzero buffer origin, with unaligned byte pitch.
    pitch = 21
    source = bytearray([0xcd] * (pitch * 4))
    rgb = {}
    for y in range(3):
        for x in range(3):
            color = bytes((0x40 + x, 0x70 + y, x + 8 * y))
            rgb[x, y] = color
            offset = (y + 1) * pitch + (x + 1) * 4
            source[offset:offset + 4] = color[::-1] + b'\xff'
    remote.write(buf, bytes(source))
    call('BltBufferToVideo', blt, (interface, buf, 2, 1, 1, 19, 37, 3, 3, pitch))
    for y in range(3):
        require(remote.read(pixel(19, 37 + y), 9) == b''.join(rgb[x, y] for x in range(3)),
                'BufferToVideo matrix differs')
    # Overlap in both directions, checking destination contents individually.
    for label, src_x, src_y, dst_x, dst_y in (
            ('down-right', 19, 37, 20, 38), ('up-left', 20, 38, 19, 37)):
        call('VideoToVideo-' + label, blt, (interface, 0, 3, src_x, src_y, dst_x, dst_y, 3, 3, 0))
        for y in range(3):
            require(remote.read(pixel(dst_x, dst_y + y), 9) == b''.join(rgb[x, y] for x in range(3)),
                    'Overlapping VideoToVideo corrupted source pixels')
    download = bytearray([0x5a] * (pitch * 4))
    remote.write(buf, bytes(download))
    call('VideoToBltBuffer', blt, (interface, buf, 1, 19, 37, 1, 1, 3, 3, pitch))
    for y in range(3):
        for x in range(3):
            offset = (y + 1) * pitch + (x + 1) * 4
            download[offset:offset + 4] = rgb[x, y][::-1] + b'\0'
    require(remote.read(buf, len(download)) == download, 'Download pixels or buffer guards differ')
    for label, args in (
            ('invalid-operation', (buf, 4, 0, 0, 0, 0, 1, 1, 0)),
            ('null-fill', (0, 0, 0, 0, 0, 0, 1, 1, 0)),
            ('empty-width', (buf, 0, 0, 0, 0, 0, 0, 1, 0)),
            ('off-screen', (buf, 0, 0, 0, WIDTH - 1, HEIGHT - 1, 2, 1, 0)),
            ('short-pitch', (buf, 2, 1, 1, 0, 0, 3, 3, 12)),
            ('row-overflow', (buf, 2, 0, (1 << 64) - 1, 0, 0, 1, 2, 8))):
        call(label, blt, (interface, *args), INVALID)
    require(remote.read(buf, len(download)) == download and remote.read(FB, 3) == bytes(3),
            'Rejected call changed the buffer or screen origin')
    return checks


def run(fd, el, handoff, target_reg, dxe_names):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(15)
        port = listener.getsockname()[1]
        command = ['qemu-system-aarch64', '-machine',
                   'virt,secure=off,virtualization=' + ('on' if el == 2 else 'off'),
                   '-accel', 'tcg', '-cpu', 'cortex-a57', '-m', '2048', '-S', '-nodefaults',
                   '-display', 'none', '-monitor', 'none', '-serial', 'none',
                   '-chardev', f'socket,id=probe,host=127.0.0.1,port={port},server=off',
                   '-gdb', 'chardev:probe',
                   '-device', f'loader,file={fd},addr={BASE:#x},cpu-num=0,force-raw=on']
        process = subprocess.Popen(command)
        try:
            stream, _ = listener.accept()
            with stream:
                remote = Remote(stream)
                remote.command('qSupported:qXfer:features:read+')
                remote.command('qXfer:features:read:target.xml:0,fff')
                remote.command('Hg0')
                remote.command('?')
                remote.set_register(0, 0x82000000)
                remote.set_register(33, 0x3c9 if el == 2 else 0x3c5)
                remote.set_register(31, 0x90010000)
                require(remote.register(32) == BASE, 'QEMU did not start at image header')
                boundary = (FB - 16, END)
                for addr in boundary:
                    remote.write(addr, b'\x5a' * 16)
                for addr in (FB, FB + 3 * (1092 * WIDTH + 731), END - 3):
                    remote.write(addr, b'\xa5' * 3)
                bp(remote, handoff)
                remote.command('c')
                require(remote.register(32) == handoff, 'SEC did not reach DXE')
                target = remote.register(target_reg)
                hobs = read_hobs(remote, remote.register(0), target)
                require(hobs['entry']['currentEl'] == el * 4, 'Wrong SEC entry EL')
                overlaps = [item for item in hobs['resources']
                            if int(item['base'], 16) < END and
                            int(item['base'], 16) + int(item['size'], 16) > FB]
                require(overlaps == [{'type': 5, 'base': hex(FB), 'size': hex(END - FB)}],
                        'Framebuffer resource HOB must be exclusively reserved')
                core_base = target - dxe_names['_ModuleEntryPoint']
                require(core_base == int(hobs['dxeModule']['base'], 16), 'DXE symbol bias mismatch')
                core = {name: core_base + dxe_names[name] for name in
                        ('CoreInstallMultipleProtocolInterfaces', 'CoreLocateProtocol', 'CoreFreePool')}
                bp(remote, handoff, False)
                bp(remote, core_base + dxe_names['DebugAssert'])
                interface, caller = locate_install(remote, core['CoreInstallMultipleProtocolInterfaces'])
                checks = exercise(remote, core, interface, caller)
                require(remote.command('Qqemu.PhyMemMode:1') == 'OK', 'Cannot inspect outer RAM guards')
                require(all(remote.read(a, 16) == b'\x5a' * 16 for a in boundary),
                        'Framebuffer boundary overwritten')
                return {'el': el, 'result': 'PASS', 'gopInterface': hex(interface),
                        'dxeEntry': hex(target), 'framebufferHob': overlaps[0],
                        'checks': checks, 'outerGuardsIntact': True}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    build = ROOT / 'Build/OculusGoGopModel/DEBUG_GCC5'
    fd = build / 'FV/OCULUS_GO_DIRECT.fd'
    sec = build / 'AARCH64/OculusGoPkg/PrePi/PrePi/DEBUG/OculusGoSec.dll'
    dxe = build / 'AARCH64/MdeModulePkg/Core/Dxe/DxeMain/DEBUG/DxeCore.dll'
    data = fd.read_bytes()
    info = verify(data)
    bias = int(info['secEntryAddress'], 16) - symbols(sec)['_ModuleEntryPoint']
    handoff, register = handoff_address(sec, data, bias)
    dxe_names = symbols(dxe)
    runs = [run(fd, el, handoff, register, dxe_names) for el in (1, 2)]
    report = {'result': 'PASS-QEMU-GOP', 'fdSha256': info['sha256'], 'cases': runs,
              'modelPixelOrder': 'packed RGB888', 'physicalGop': 'UNTESTED'}
    if args.report:
        with args.report.open('x', encoding='utf-8') as out:
            print(json.dumps(report, indent=2), file=out)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
