"""Exercise the delivered SEC_STACK FD and check every byte of the two scanout bands.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from sec_mem_qemu import (ARENA, BASE, FB_BASE, GUARD, POOL, POOL_END, RAM_START, SIZE,
                          SURFACE_BYTES, band_ranges, check_vectors, digest, expect_hob,
                          guest, require, symbols, until, verify, watch)

ROOT = Path(__file__).resolve().parents[1]
BOTTOM, TOP = 0x8043f000, 0x8047f000
MASK = 0xc35480aa703619dc
CASES = ('valid', 'relocated', 'wrong-x0', 'dcache', 'dirty-stack', 'lower-guard',
         'forward-fault', 'reverse-fault', 'live-frame', 'bad-phit', 'late-guard', 'exception')
NAMES = ('_ModuleEntryPoint', 'StackVerifyUp', 'StackVerifyDown', 'SecStackFrames',
         'HobConstructor', 'SecMemValidateHob', 'StackFramesReturn', 'StackPaint',
         'StackComplete', 'StackMemoryRejected', 'StackEntryRejected', 'StackFrameRejected',
         'StackGuardRejected', 'StackVectors', 'StackException')


def exercise(fd_path, data, sym, harness, el, case, patterns):
    shift = 0x100000 if case == 'relocated' else 0
    load = BASE + shift
    loc = {name: value + shift for name, value in sym.items()}
    early = case in ('dcache', 'relocated', 'wrong-x0', 'mmu-el1')
    screen = b'\xa5' * (SURFACE_BYTES + 2 * GUARD)
    with guest(fd_path, harness, el, load) as (g, ram):
        def read(start, size):
            buf = os.pread(ram, size, start - RAM_START)
            require(len(buf) == size, 'Incomplete model RAM read')
            return buf

        def seed(start, buf):
            require(os.pwrite(ram, buf, start - RAM_START) == len(buf), 'Incomplete model RAM seed')

        def stop(name):
            until(g, loc[name])

        for cmd in ('qSupported:qXfer:features:read+', 'qXfer:features:read:target.xml:0,fff', 'Hg0', '?'):
            g.command(cmd)
        require(read(load, SIZE) == data, 'Loaded FD differs from the reviewed bytes')
        seed(FB_BASE - GUARD, screen)
        incoming = {0: 0x82000008 if case == 'wrong-x0' else 0x82000000, 1: 23,
                    2: 47, 3: 83, 30: 0x55667788, 31: 0x90010000}
        g.set_register(33, 0x3c0 | (9 if el == 2 else 5))
        for n, val in incoming.items():
            g.set_register(n, val)
        g.set_register(18, 4 if case == 'dcache' else 0)
        g.set_register(20, load)
        g.set_register(32, 0x41000000 + (64 if el == 2 else 0))
        until(g, load)
        if case == 'mmu-el1':
            require(g.register(22) & 0x1005 == 1, 'MMU rejection fixture is inactive')
        # Trap guest stores throughout modeled RAM except the explicit measurement
        # footprint. Also stop on any read in the normal 64 MiB allocator.
        previous = RAM_START
        for first, end in sorted(((ARENA, ARENA + 64), (BOTTOM, TOP), *band_ranges())):
            watch(g, 2, previous, first)
            previous = end
        watch(g, 2, previous, RAM_START + (2 << 30))
        watch(g, 3, POOL, POOL_END)
        stop('_ModuleEntryPoint')
        pristine = bytearray(data)
        def inject(address):
            seed(address, bytes([read(address, 1)[0] ^ 0x80]))
            if load <= address < load + SIZE:
                pristine[address-load] ^= 0x80

        frame_sps = []
        if early:
            terminal = 'StackEntryRejected'
        elif case in ('dirty-stack', 'lower-guard'):
            inject(TOP - 1 if case == 'dirty-stack' else BOTTOM - 4096)
            terminal = 'StackMemoryRejected' if case == 'dirty-stack' else 'StackGuardRejected'
        else:
            stop('StackVerifyUp')
            require(read(BOTTOM, TOP-BOTTOM) == patterns[0], 'Forward write missed or aliased a word')
            if case == 'forward-fault':
                inject(BOTTOM + 0x20001)
                terminal = 'StackMemoryRejected'
            elif case == 'exception':
                fault = 0x41002000
                require(read(fault, 4) == bytes(4), 'Missing undefined-instruction fixture')
                g.set_register(32, fault)
                until(g, loc['StackVectors'] + 0x200)
                terminal = 'StackException'
            else:
                stop('StackVerifyDown')
                require(read(BOTTOM, TOP-BOTTOM) == patterns[1], 'Reverse write missed or aliased a word')
                if case == 'reverse-fault':
                    inject(BOTTOM)
                    terminal = 'StackMemoryRejected'
                else:
                    for depth in (3, 2, 1, 0):
                        stop('SecStackFrames')
                        sp = g.register(31)
                        require(g.register(0) == depth and BOTTOM <= sp <= TOP-96 and sp % 16 == 0,
                                'Unaligned frame or wrong recursion')
                        if frame_sps:
                            require(frame_sps[-1] - sp >= 1024, 'Live call frames overlap')
                        frame_sps.append(sp)
                        # Advance past the function-entry breakpoint before rearming it.
                        require(g.command('s').startswith(('T', 'S')), 'Could not step into C frame')
                    require(frame_sps[0] == TOP - 96, 'Entry state record has unexpected address')
                    fields = struct.unpack('<11QII', read(TOP-96, 96))
                    require(fields[:6] == (0x0060000131424d54, incoming[0], 23, 47, 83, el*4)
                            and fields[9:] == (incoming[31], incoming[30], 1, 0), 'Bad PrePi entry record')
                    stop('HobConstructor')
                    frame_sps.append(g.register(31))
                    require(BOTTOM <= frame_sps[-1] <= frame_sps[-2] - 1024
                            and frame_sps[-1] % 16 == 0, 'PI constructor is outside the tested stack')
                    if case == 'live-frame':
                        # Locate a known contiguous sequence in the outer caller's live frame.
                        signature = struct.pack('<4Q', *(3 << 16 | i for i in range(4)))
                        frame = read(frame_sps[1], frame_sps[0] - frame_sps[1])
                        require(frame.count(signature) == 1, 'Cannot identify outer frame')
                        inject(frame_sps[1] + frame.index(signature))
                    stop('SecMemValidateHob')
                    expect_hob(g)
                    if case == 'bad-phit':
                        inject(ARENA + 8)
                    stop('StackFramesReturn')
                    ok = case not in ('live-frame', 'bad-phit')
                    require(bool(g.register(0)) == ok, 'Frame/PI validation returned unexpected result')
                    if case == 'late-guard':
                        inject(TOP + 4095)
                        terminal = 'StackGuardRejected'
                    elif ok:
                        stop('StackPaint')
                        terminal = 'StackComplete'
                    else:
                        terminal = 'StackFrameRejected'
        stop(terminal)
        require(read(loc[terminal], 4) == bytes.fromhex('00000014'), 'Endpoint is not a terminal loop')
        result_screen = bytearray(screen)
        if case == 'valid':
            for n, val in incoming.items():
                require(g.register(n) == val, f'Entry register {n} was not restored')
            row = b''.join(bytes.fromhex(c)*288 for c in ('00ff00','ff00ff','ffffff','ff00ff','00ff00'))
            for first, end in band_ranges():
                offset = GUARD + first - FB_BASE
                require(end-first == len(row)*32, 'Bad checkpoint geometry')
                result_screen[offset:offset+end-first] = row*32
        require(read(FB_BASE-GUARD, len(screen)) == result_screen, 'Screen or its guards differ')
        actual = bytearray(read(load, SIZE))
        if not early and case not in ('dirty-stack', 'lower-guard'):
            a, b = BOTTOM-load, TOP-load
            actual[a:b] = pristine[a:b]
            if frame_sps:
                a = ARENA - load
                actual[a:a+64] = pristine[a:a+64]
        require(actual == pristine, 'Guest changed FD outside the expected footprint')
        return {'el': el, 'scenario': case, 'terminal': terminal, 'screenMatched': True,
                'fdOutsideFootprintMatched': True, 'unexpectedGuestRamWrites': 0,
                'normalPoolAccesses': 0, 'stackPointersAtCallEntries': [hex(n) for n in frame_sps]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path, required=True)
    parser.add_argument('--sec-elf', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    data = args.fd.read_bytes()
    info = verify(data)
    require(data[64:4096] == b'\xff'*(4096-64)
            and struct.unpack_from('<Q', data, 0x1020)[0] == BOTTOM-4096-BASE-4096
            and TOP + 4096 == BASE + SIZE, 'Image does not own the tested span')
    names = symbols(args.sec_elf)
    bias = int(info['secEntryAddress'],16) - names['_ModuleEntryPoint']
    loc = {k: names[k]+bias for k in NAMES}
    vectors = check_vectors(data, {'SecMemVectors': loc['StackVectors'], 'SecMemException': loc['StackException']})
    forward = b''.join(struct.pack('<Q', addr ^ MASK) for addr in range(BOTTOM, TOP, 8))
    cases = []
    with tempfile.TemporaryDirectory() as folder:
        for name in ('entry_harness', 'sec_visual_mmu_el1'):
            obj, harness = (Path(folder) / (name+ext) for ext in ('.o','.bin'))
            subprocess.run(['aarch64-linux-gnu-gcc', '-c', ROOT/'tests'/(name+'.S'), '-o', obj], check=True)
            subprocess.run(['aarch64-linux-gnu-objcopy', '-O','binary', obj, harness], check=True)
            for el, scenario in ([(1,'mmu-el1')] if name.endswith('el1') else
                                 [(n,s) for n in (1,2) for s in CASES]):
                try:
                    cases.append(exercise(args.fd.resolve(), data, loc, harness, el, scenario,
                                          (forward, bytes(x ^ 255 for x in forward))))
                except Exception as error:
                    raise RuntimeError(f'EL{el} {scenario}: {error}') from error
                print(f'EL{el} {scenario}: PASS', flush=True)
    with args.report.open('x', encoding='utf-8', newline='\n') as output:
        json.dump({'result':'PASS-QEMU-SEC-STACK', 'fdSha256':info['sha256'],
                   'elfSha256':digest(args.sec_elf.read_bytes()), 'vectors':vectors,
                   'stackRange':[hex(BOTTOM),hex(TOP)], 'bytesPerPattern':len(forward),
                   'physicalExecution':'UNKNOWN', 'cases':cases}, output, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
