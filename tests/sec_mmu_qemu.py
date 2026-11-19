"""Run the packaged SEC_MMU instructions against stage-1 translation at EL1 and EL2.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from sec_mem_qemu import (BASE, FB_BASE, GUARD, RAM_START, SIZE, SURFACE_BYTES,
                          band_ranges, check_vectors, digest, guest, require, symbols, until, verify, watch)

ROOT = Path(__file__).resolve().parents[1]
PAGE = 4096
TABLE = 0x8043f000
STACK = 0x8047e000
TOP = STACK + PAGE
WINDOWS = (0x80000000, 0x80400000, 0x83600000, 0x83a00000, 0x83c00000)
CASES = ('valid', 'icache', 'dcache', 'wrong-x0', 'relocated', 'dirty-tables', 'dirty-stack',
         'last-page-absent', 'wrong-output', 'wrong-attribute', 'mapped-guard', 'instruction-fault',
         'mono-corruption', 'color-corruption')
NAMES = ('_ModuleEntryPoint', 'MmuBeforeEnable', 'MmuTranslated', 'MmuRepaint', 'MmuSeal',
         'MmuSignal', 'MmuComplete', 'MmuRejected', 'MmuException', 'MmuVectors')


def slot(va):
    table = 2 + WINDOWS.index(va & ~0x1fffff)
    return table * PAGE + ((va >> 12) & 511) * 8


def expected_tables(el):
    blob = bytearray(7 * PAGE)
    def put(offset, descriptor):
        struct.pack_into('<Q', blob, offset, descriptor)
    put(2 * 8, (TABLE + PAGE) | 3)
    for index, base in enumerate(WINDOWS):
        put(PAGE + ((base >> 21) & 511)*8, (TABLE + (index+2)*PAGE) | 3)
    rx = 0x787 | (1 << 54 if el == 1 else 0)
    data = 0x707 | (1 << 54) | (1 << 53 if el == 1 else 0)
    for va in range(0x80081000, 0x80085000, PAGE):
        put(slot(va), va | rx)
    for first, end in [(STACK,TOP), *band_ranges()]:
        for va in range(first,end,PAGE):
            put(slot(va), va | data)
    return blob


def screen_pattern(stage):
    buf = bytearray(b'\xa5' * (SURFACE_BYTES + GUARD*2))
    if stage:
        colors = {'mono':['ffffff','000000','ffffff','000000','ffffff'],
                  'color':['ff0000','00ffff','000000','00ffff','ff0000'],
                  'sealed':['ff0000','00ffff','0000ff','00ffff','ff0000']}[stage]
        row = b''.join(bytes.fromhex(c)*288 for c in colors)
        for first,end in band_ranges():
            index = GUARD + first - FB_BASE
            buf[index:index+end-first] = row*32
    return buf


def exercise(path, fd, sym, harness, el, case):
    shift = 0x100000 if case == 'relocated' else 0
    load = BASE + shift
    early = case in ('wrong-x0', 'dcache', 'relocated', 'mmu-el1', 'dirty-stack')
    screen_base = FB_BASE-GUARD
    initial = bytearray(fd)
    tables = expected_tables(el)
    first, last = band_ranges()
    expected = screen_pattern(None)
    phase = 'untouched'
    controls = None
    with guest(path, harness, el, load) as (g, ram):
        def read(pa, size):
            result = os.pread(ram, size, pa-RAM_START)
            require(len(result) == size, 'Incomplete guest RAM read')
            return result

        def write(pa, buf):
            require(os.pwrite(ram, buf, pa-RAM_START) == len(buf), 'Incomplete host injection')

        def stop(name):
            until(g, sym[name]+shift)

        def screen_is(buf):
            require(read(screen_base, len(buf)) == buf, f'Scanout/guards differ ({case}, {phase})')

        for cmd in ('qSupported:qXfer:features:read+', 'qXfer:features:read:target.xml:0,fff', 'Hg0', '?'):
            g.command(cmd)
        require(read(load,SIZE) == fd, 'Wrong firmware loaded')
        write(screen_base, expected)
        g.set_register(33, 0x3c0 | (9 if el == 2 else 5))
        g.set_register(0, 0x82000008 if case == 'wrong-x0' else 0x82000000)
        g.set_register(31, 0x90010000)
        g.set_register(18, {'icache':0x1000, 'dcache':4}.get(case,0))
        g.set_register(20,load)
        g.set_register(32,0x41000000 + (64 if el == 2 else 0))
        until(g,load)
        if case == 'mmu-el1':
            require(g.register(22) & 0x1005 == 1, 'MMU fixture failed')
        previous = RAM_START
        for begin,end in sorted(((TABLE,TABLE+len(tables)), (STACK,TOP), first,last)):
            watch(g,2,previous,begin)
            previous=end
        watch(g,2,previous,RAM_START+(2<<30))
        watch(g,3,0x94000000,0x98000000)
        stop('_ModuleEntryPoint')
        terminal = 'MmuRejected'
        if case in ('dirty-tables','dirty-stack'):
            addr = TABLE+80 if case == 'dirty-tables' else TOP-1
            write(addr,b'\x7f')
            initial[addr-load] = 0x7f
        if not early and case != 'dirty-tables':
            stop('MmuBeforeEnable')
            phase = 'mono'
            expected = screen_pattern(phase)
            screen_is(expected)
            require(read(TABLE,len(tables)) == tables, 'Descriptor mismatch anywhere in seven tables')
            bad = case in ('last-page-absent','wrong-output','wrong-attribute','mapped-guard')
            if bad:
                va = {'last-page-absent':(last[1]-1)&-PAGE, 'wrong-output':first[0],
                      'wrong-attribute':first[0], 'mapped-guard':TOP}[case]
                off = slot(va)
                desc, = struct.unpack_from('<Q',tables,off)
                desc = {'last-page-absent':0, 'wrong-output':desc+PAGE,
                        'wrong-attribute':desc & ~4,
                        'mapped-guard':struct.unpack_from('<Q',tables,slot(STACK))[0]+PAGE}[case]
                struct.pack_into('<Q',tables,off,desc)
                write(TABLE+off, tables[off:off+8])
            stop('MmuTranslated')
            control = g.register(12)
            controls = hex(control)
            require(control & 0x1005 == (0x1001 if case == 'icache' else 1),
                    f'SCTLR at translated PC: {control:#x}')
            if case == 'instruction-fault':
                g.set_register(32,TOP)
                until(g,sym['MmuVectors']+0x200)
                terminal='MmuException'
            elif not bad:
                if case == 'mono-corruption':
                    write(last[1]-1,b'\x47')
                    expected[last[1]-1-screen_base] = 0x47
                else:
                    stop('MmuRepaint')
                    screen_is(expected)
                    if case == 'color-corruption':
                        stop('MmuSignal')
                        require(g.register(0) == 1 and g.register(1) == 0, 'Missing translated drawing call')
                        require(g.command('s').startswith(('T','S')), 'Cannot step from painter')
                        stop('MmuSignal')
                        require(g.register(0) == 1 and g.register(1) == 1, 'Missing translated readback')
                    else:
                        stop('MmuSeal')
                    phase = 'color'
                    expected = screen_pattern(phase)
                    screen_is(expected)
                    if case == 'color-corruption':
                        write(last[1]-1,b'\x47')
                        expected[last[1]-1-screen_base] = 0x47
                    else:
                        terminal='MmuComplete'
                        phase = 'sealed'
                        expected = screen_pattern(phase)
        stop(terminal)
        screen_is(expected)
        actual = bytearray(read(load,SIZE))
        if not early:
            actual[STACK-load:TOP-load] = initial[STACK-load:TOP-load]
        if not early and case != 'dirty-tables':
            require(read(TABLE,len(tables)) == tables, 'Tables changed after publication')
            actual[TABLE-load:TABLE-load+len(tables)] = initial[TABLE-load:TABLE-load+len(tables)]
        require(actual == initial, 'Unexpected change elsewhere in the FD')
        require(read(sym[terminal]+shift,4) == bytes.fromhex('00000014'), 'Unexpected terminal opcode')
    return {'el':el, 'case':case, 'terminal':terminal, 'lastPattern':phase, 'translatedSctlr':controls,
            'fullScreenAndGuardsMatched':True,'unexpectedGuestRamWrites':0,'highPoolAccesses':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path,required=True)
    parser.add_argument('--sec-elf', type=Path,required=True)
    parser.add_argument('--report', type=Path,required=True)
    args=parser.parse_args()
    fd=args.fd.read_bytes()
    info=verify(fd)
    names=symbols(args.sec_elf)
    bias=int(info['secEntryAddress'],16)-names['_ModuleEntryPoint']
    sym={k:names[k]+bias for k in NAMES}
    vectors=check_vectors(fd,{'SecMemVectors':sym['MmuVectors'],'SecMemException':sym['MmuException']})
    cases=[]
    with tempfile.TemporaryDirectory() as folder:
        for fixture in ('entry_harness','sec_visual_mmu_el1'):
            obj,harness=(Path(folder)/(fixture+ext) for ext in ('.o','.bin'))
            subprocess.run(['aarch64-linux-gnu-gcc','-c',ROOT/'tests'/(fixture+'.S'),'-o',obj],check=True)
            subprocess.run(['aarch64-linux-gnu-objcopy','-O','binary',obj,harness],check=True)
            scenarios = [(1,'mmu-el1')] if fixture.endswith('el1') else [(el,k) for el in (1,2) for k in CASES]
            for el,case in scenarios:
                try:
                    cases.append(exercise(args.fd.resolve(),fd,sym,harness,el,case))
                except Exception as error:
                    raise RuntimeError(f'EL{el} {case}: {error}') from error
                print(f'EL{el} {case}: PASS',flush=True)
    with args.report.open('x',encoding='utf-8',newline='\n') as out:
        json.dump({'result':'PASS-QEMU-SEC-MMU','fdSha256':info['sha256'],
                   'elfSha256':digest(args.sec_elf.read_bytes()),'vectors':vectors,'cases':cases},out,indent=2)
        out.write('\n')


if __name__=='__main__':
    main()
