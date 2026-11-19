"""Audit the reachable SEC_MEM instructions in the exact FD against their linked ELF.

Requires GNU AArch64 binutils. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from emulate_sec_handoff import symbols
from verify_fd import BASE, verify
from verify_sec_visual_data import band_ranges


FUNCTIONS = {'Be32', 'Be64', 'NameIs', 'ClearOfSamples', 'OculusGoSecMemValidateFdt',
             'HobConstructor', 'SecMemConstructHob', 'SecMemValidateHob'}
LOADS = {'ldr', 'ldp', 'ldrb', 'ldrh', 'ldur'}
STORES = {'str', 'stp', 'strb'}
ALU = {'add', 'adds', 'sub', 'subs', 'mov', 'movk', 'adr', 'adrp', 'and', 'ands', 'orr',
       'rev', 'tst', 'cmp', 'ccmp', 'csel', 'cset', 'csinc'}
HOB_BASE, HOB_LIMIT, STACK_TOP = BASE + 0x200, BASE + 0x800, BASE + 0x1000
TERMINALS = ('SecMemComplete', 'SecMemEntryRejected', 'SecMemFdtRejected', 'SecMemHobRejected',
             'SecMemException')
REVIEWED_FD = 'c15da640f8292d226924d06f63d5a1cd7f15d41215ce02b4ab0123675f505091'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def target(args, bias):
    return bias + int(args.rsplit(',', 1)[-1].strip().split()[0], 16)


def conditional(op):
    return op.startswith('b.') or op in ('cbz', 'cbnz', 'tbz', 'tbnz')


def load_word(data, physical, fmt='<I'):
    offset = physical - BASE
    require(0 <= offset <= len(data) - struct.calcsize(fmt), 'Read outside FD')
    return struct.unpack_from(fmt, data, offset)[0]


def disassembly(elf, bias):
    listing = subprocess.check_output(['aarch64-linux-gnu-objdump', '-d', '-w', elf], text=True)
    code = {}
    for line in listing.splitlines():
        mat = re.fullmatch(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)(?:\s+(.*))?', line)
        if mat:
            code[bias + int(mat[1], 16)] = (int(mat[2], 16), mat[3], (mat[4] or '').split('//')[0].strip())
    ranges = {}
    listing = subprocess.check_output(['aarch64-linux-gnu-nm', '-S', '--defined-only', elf], text=True)
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[2] in ('t', 'T') and parts[3] in FUNCTIONS:
            start = bias + int(parts[0], 16)
            ranges[parts[3]] = range(start, start + int(parts[1], 16), 4)
    require(ranges.keys() == FUNCTIONS, 'Missing reviewed C function')
    return code, ranges


def compare_section(data, elf, loc, code, bias):
    sections = subprocess.check_output(['aarch64-linux-gnu-objdump', '-h', elf], text=True)
    match = re.search(r'^\s*\d+\s+\.text\s+(\w+)\s+(\w+)\s+\w+\s+(\w+)\s', sections, re.M)
    require(match, 'No ELF text section')
    size, start, offset = (int(n,16) for n in match.groups())
    section = bytearray(elf.read_bytes()[offset:offset+size])
    base = bias + start
    require(BASE <= base <= BASE+len(data)-size, 'ELF section leaves the firmware image')
    entry = loc['_ModuleEntryPoint']
    literal = target(code[entry+0x4c][2],bias)
    require(struct.unpack_from('<Q',section,literal-base)[0] == entry-bias
            and load_word(data,literal,'<Q') == entry, 'Unexpected SEC entry relocation')
    struct.pack_into('<Q',section,literal-base,entry)
    converted = []
    for pc, (word,op,args) in list(code.items()):
        fixed = load_word(data,pc)
        if op != 'adrp' or fixed == word:
            continue
        # Upstream GenFw Elf64Convert.c may relax ADRP to ADR. Reconstruct
        # the signed ADR displacement and verify the resolved page and Rd.
        require((fixed & 0x9f000000) == 0x10000000 and (word & 31) == (fixed & 31),
                f'Unexpected page-relative relaxation at {pc:#x}')
        imm = ((fixed >> 29) & 3) | ((fixed >> 3) & 0x1ffffc)
        if imm & (1<<20):
            imm -= 1<<21
        require(pc+imm == target(args,bias), f'ADR resolved a different page at {pc:#x}')
        struct.pack_into('<I',section,pc-base,fixed)
        code[pc] = (fixed, 'adr', args)
        converted.append(hex(pc))
    require(section == data[base-BASE:base-BASE+size], 'ELF text/literals differ from packaged SEC')
    return {'sectionBytes': size, 'rebasedEntryLiteral':hex(literal), 'equivalentAdrpToAdr':converted}


def reachable(data, code, owner, loc, bias):
    entry = loc['_ModuleEntryPoint']
    pending = [entry]
    pending.extend(loc['SecMemVectors'] + offset for offset in range(0, 2048, 128))
    seen, calls, stores, system = set(), [], defaultdict(list), []
    for offset in range(0, 2048, 128):
        pc = loc['SecMemVectors'] + offset
        require(code[pc][1] == 'b' and target(code[pc][2], bias) == loc['SecMemException'],
                'Unexpected exception vector target')
    require(loc['SecMemVectors'] % 2048 == 0, 'Misaligned VBAR')
    while pending:
        pc = pending.pop()
        if pc in seen:
            continue
        require(pc in owner and pc in code, f'Unexpected reachable code at {pc:#x}')
        seen.add(pc)
        word, op, args = code[pc]
        require(load_word(data, pc) == word, f'ELF/FD instruction mismatch at {pc:#x}')
        if op == 'ret':
            require(owner[pc] in FUNCTIONS and args in ('', 'x30'), 'Unreviewed return')
            continue
        if op in ('bl', 'b') or conditional(op):
            dest = target(args, bias)
            if op == 'bl' or owner.get(dest) != owner[pc]:
                if owner[pc] != 'vectors':
                    require(owner.get(dest) in FUNCTIONS and dest == loc[owner[dest]],
                            f'Unexpected cross-function branch at {pc:#x}')
                    calls.append((pc, owner[pc], owner[dest], op))
            pending.append(dest)
            if op == 'b':
                continue
        elif op in STORES:
            stores[owner[pc]].append((pc, op, args))
        elif op in ('mrs', 'msr', 'dsb', 'isb'):
            require(owner[pc] == 'entry', 'Unexpected system instruction in C')
            system.append((op, args))
        else:
            require(op in LOADS | ALU, f'Unreviewed opcode {op} at {pc:#x}')
        pending.append(pc + 4)
    for label in TERMINALS:
        require(loc[label] in seen and load_word(data, loc[label]) == 0x14000000, 'Missing terminal loop')
    expected_system = [('mrs', f'x9, currentel'), ('mrs', 'x10, mpidr_el1'),
                       ('mrs', 'x11, sctlr_el1'), ('mrs', 'x11, sctlr_el2'),
                       ('msr', 'daifset, #0xf'), ('msr', 'vbar_el1, x15'), ('msr', 'vbar_el2, x15'),
                       ('isb', ''), ('dsb', 'sy'), ('dsb', 'sy'), ('dsb', 'sy')]
    require(sorted((op, args.lower()) for op, args in system) == sorted(expected_system),
            'Changed system register or barrier sequence')
    return seen, calls, stores


def materialize(data, code, pc, reg, bias):
    _, op, args = code[pc]
    dst, source = args.split(', ', 1)
    require(dst == reg, 'Constant uses unexpected register')
    if op == 'mov' and source.startswith('#'):
        return int(source[1:], 0)
    require(op == 'ldr' and '[' not in source, 'Expected literal load')
    return load_word(data, target(args, bias), '<Q')


def sample_path(data, code, seen, loc, bias):
    first, second, paint = (loc[name] for name in ('SecMemPoolRead', 'SecMemStackRead', 'SecMemPaint'))
    require(first + 12 == second and second + 12 == paint, 'Sample block changed length')
    require(materialize(data, code, first - 4, 'x14', bias) == 0x94000000 and
            materialize(data, code, second - 4, 'x14', bias) == 0x97ffffa0, 'Wrong sample address')
    for pc in (first, second):
        require(code[pc][1:] == ('ldr', 'x9, [x14]') and code[pc+4][1:] == ('dsb', 'sy'),
                'Expected a single aligned 64-bit sample followed by DSB')
    require(code[second + 8][1:] == ('mov', 'x9, xzr'), 'Sample value must be discarded')
    for name, func in [('SecMemFdtReturn', 'OculusGoSecMemValidateFdt'), ('SecMemHobReturn', 'SecMemConstructHob')]:
        pc = loc[name]
        require(code[pc - 4][1] == 'bl' and target(code[pc - 4][2], bias) == loc[func]
                and code[pc][1] == 'tbz' and code[pc][2].startswith('w0, #0, '), 'Wrong success guard')
    require(materialize(data, code, loc['_ModuleEntryPoint'] + 0x4c, 'x16', bias)
            == loc['_ModuleEntryPoint'], 'Relocated entry guard differs from SEC PC')
    # No alternate direct edge may enter the sample or painting sequence.
    for pc in seen:
        _, op, args = code[pc]
        if pc < first - 4 and (op in ('b','bl') or conditional(op)):
            dest = target(args, bias)
            require(not first - 4 <= dest < loc['SecMemComplete'], 'Branch bypasses the sample checks')


def check_paint(data, code, loc, bias):
    start = loc['SecMemPaint']
    # Counters and back edges bound the three postincrement byte stores for
    # each pixel to 288 columns x 5 blocks x 32 rows per band.
    instructions = {
        0x00: ('mov', 'w12, #0x2'), 0x08: ('mov', 'w16, #0x20'), 0x0c: ('mov', 'w6, #0x0'),
        0x10: ('mov', 'w9, #0xff'), 0x14: ('mov', 'w10, #0xff'), 0x18: ('mov', 'w11, #0x0'),
        0x1c: ('cmp', 'w6, #0x2'), 0x28: ('mov', 'w9, #0x0'), 0x2c: ('mov', 'w11, #0xff'),
        0x30: ('mov', 'w17, #0x120'), 0x34: ('strb', 'w9, [x15], #1'),
        0x38: ('strb', 'w10, [x15], #1'), 0x3c: ('strb', 'w11, [x15], #1'),
        0x40: ('subs', 'w17, w17, #0x1'), 0x48: ('add', 'w6, w6, #0x1'),
        0x4c: ('cmp', 'w6, #0x5'), 0x54: ('subs', 'w16, w16, #0x1'),
        0x5c: ('subs', 'w12, w12, #0x1'), 0x6c: ('dsb', 'sy'),
    }
    for offset, instruction in instructions.items():
        require(code[start + offset][1:] == instruction, 'Framebuffer loop or color changed')
    for offset, op, dest in ((0x20, 'b.eq', 0x2c), (0x24, 'tbz', 0x30), (0x44, 'b.ne', 0x34),
                             (0x50, 'b.ne', 0x10), (0x58, 'b.ne', 0xc), (0x60, 'b.eq', 0x6c),
                             (0x68, 'b', 8)):
        _, opcode, args = code[start + offset]
        require(opcode == op and target(args, bias) == start + dest, 'Unexpected framebuffer loop edge')
        if op == 'tbz':
            require(args.startswith('w6, #0, '), 'Unexpected block selector')
    require(start + 0x70 == loc['SecMemComplete'], 'Unexpected end of framebuffer loop')
    bases = [materialize(data, code, start + offset, 'x15', bias) for offset in (4, 0x64)]
    spans = tuple((addr, addr + 288 * 5 * 32 * 3) for addr in bases)
    require(spans == band_ranges(), 'Unreviewed framebuffer ranges')
    return [[hex(first), hex(end)] for first, end in spans]


def stack_depth(code, ranges, loc, calls, bias):
    call_at = {pc: (dst, op) for pc, _, dst, op in calls}
    bounds = []

    @lru_cache(None)
    def depth(name):
        work = [(loc[name], 0)]
        visited = {}
        minimum = 0
        while work:
            pc, offset = work.pop()
            if pc in visited:
                require(visited[pc] == offset, 'Inconsistent stack delta at CFG join')
                continue
            require(pc in ranges[name], 'Unexpected fallthrough between functions')
            visited[pc] = offset
            _, op, args = code[pc]
            match = re.search(r'\[sp(?:, #(-?\d+))?\](!)?(?:, #(-?\d+))?$', args)
            if match:
                displacement, preindex, postindex = match.groups()
                disp = int(displacement or 0)
                if op in STORES or op in LOADS:
                    reg = args.split(',')[0]
                    size = (8 if reg.startswith('x') else 4) * (2 if op in ('stp','ldp') else 1)
                    address = offset + disp
                    require(address + size <= 0, f'Stack access above C frame at {pc:#x}')
                    minimum = min(minimum, address)
                if preindex or postindex:
                    offset += disp if preindex else int(postindex)
            elif op in ('sub', 'add') and args.startswith('sp, sp, #'):
                amount = int(args.split('#')[1], 0)
                offset += amount if op == 'add' else -amount
            else:
                require(not args.startswith('sp,'), f'Unexpected SP assignment at {pc:#x}')
                if op in STORES and name != 'HobConstructor':
                    raise ValueError(f'Non-stack C store at {pc:#x}: {args}')
            minimum = min(minimum, offset)
            if pc in call_at:
                dest, branch = call_at[pc]
                minimum = min(minimum, offset + depth(dest))
                if branch == 'b':
                    require(offset == 0, 'Tail call with an active frame')
                    continue
            if op == 'ret':
                require(offset == 0, 'C return did not balance stack')
                continue
            if op == 'b' or conditional(op):
                work.append((target(args, bias), offset))
                if op == 'b':
                    continue
            work.append((pc + 4, offset))
        return minimum

    for name in ('OculusGoSecMemValidateFdt', 'SecMemConstructHob'):
        bounds.append(STACK_TOP - 48 + depth(name))
    require(min(bounds) >= HOB_LIMIT, 'C frames overlap the scratch HOB arena')
    return min(bounds)


def audit_hob(code, loc, bias):
    # The four AAPCS64 arguments are constants in this build. Evaluate their
    # construction and the actual stores in HobConstructor, including writeback.
    regs = {'sp': STACK_TOP - 48, 'xzr': 0}
    memory = bytearray(64)
    written = set()

    def get(reg):
        return regs['x' + reg[1:] if reg.startswith('w') else reg]

    def assign(dst, value):
        regs['x' + dst[1:] if dst.startswith('w') else dst] = value & ((1 << (32 if dst.startswith('w') else 64)) - 1)

    def value(arg):
        return int(arg[1:], 0) if arg.startswith('#') else get(arg)

    def arithmetic(op, args):
        parts = args.split(', ')
        if op == 'mov':
            assign(parts[0], value(parts[1]))
        elif op == 'movk':
            require(parts[2] == 'lsl #16', 'Unexpected MOVK shift')
            assign(parts[0], (get(parts[0]) & ~(0xffff << 16)) | (value(parts[1]) << 16))
        elif op == 'add':
            assign(parts[0], get(parts[1]) + value(parts[2]))
        else:
            raise ValueError(f'Unexpected HOB construction opcode {op}')

    pc = loc['SecMemConstructHob']
    while code[pc][1] != 'bl':
        _, op, args = code[pc]
        if (op, args) != ('stp','x29, x30, [sp, #-16]!'):
            arithmetic(op, args)
        pc += 4
    require(target(code[pc][2], bias) == loc['HobConstructor'] and
            [get(f'x{i}') for i in range(4)] == [HOB_BASE, HOB_LIMIT-HOB_BASE, HOB_BASE, HOB_LIMIT],
            'Unexpected PI constructor or memory arguments')
    pc = loc['HobConstructor']
    while code[pc][1] != 'ret':
        _, op, args = code[pc]
        if op in STORES:
            mat = re.fullmatch(r'([wx]\w+)(?:, ([wx]\w+))?, \[(x\d+)(?:, #(\d+))?\](!)?', args)
            require(mat, 'Unexpected PI store mode')
            first, other, base, immediate, writeback = mat.groups()
            dest = get(base) + int(immediate or '0')
            if writeback:
                assign(base, dest)
            for reg in (first, other) if other else (first,):
                n = 8 if reg.startswith('x') else 4
                i = dest - HOB_BASE
                require(0 <= i <= len(memory) - n, 'PI store outside scratch PHIT/end')
                memory[i:i+n] = get(reg).to_bytes(n, 'little')
                written.update(range(i, i+n))
                dest += n
        else:
            arithmetic(op, args)
        pc += 4
    expected = struct.pack('<HHIII5QHHI', 1, 56, 0, 9, 0, HOB_LIMIT, HOB_BASE,
                           HOB_LIMIT, HOB_BASE+64, HOB_BASE+56, 0xffff, 8, 0)
    require(memory == expected and len(written) == 64 and get('x0') == HOB_BASE,
            'PI constructor output bytes/pointer differ')


def audit(fd, elf):
    data = fd.read_bytes()
    info = verify(data)
    names = symbols(elf)
    bias = int(info['secEntryAddress'], 16) - names['_ModuleEntryPoint']
    loc = {k:v + bias for k,v in names.items()}
    code, ranges = disassembly(elf, bias)
    section = compare_section(data, elf, loc, code, bias)
    require(info['sha256'] == REVIEWED_FD, 'Unreviewed FD')
    owner = {pc:name for name, span in ranges.items() for pc in span}
    for pc in range(loc['_ModuleEntryPoint'], loc['SecMemException']+4, 4):
        owner[pc] = 'entry'
    for pc in range(loc['SecMemVectors'], loc['SecMemVectors']+2048, 128):
        owner[pc] = 'vectors'
    seen, calls, stores = reachable(data, code, owner, loc, bias)
    sample_path(data, code, seen, loc, bias)
    spans = check_paint(data, code, loc, bias)
    minimum = stack_depth(code, ranges, loc, calls, bias)
    audit_hob(code, loc, bias)
    entry_stores = sorted(stores['entry'])
    require([s[1:] for s in entry_stores] ==
            [('stp','x0, x1, [sp, #-48]!'), ('stp','x2, x3, [sp, #16]'),
             ('stp','x12, x30, [sp, #32]'), ('strb','w9, [x15], #1'),
             ('strb','w10, [x15], #1'), ('strb','w11, [x15], #1')],
            'Unexpected store in assembly entry')
    stack_store = entry_stores[0][0]
    require(materialize(data,code,stack_store-8,'x15',bias) == STACK_TOP and
            code[stack_store-4][1:] == ('mov','sp, x15'), 'Unexpected assembly stack')
    require(data[64:4096] == b'\xff' * (4096-64), 'Occupied image header padding')
    return {'result':'PASS-STATIC-SEC-MEM', 'fdSha256':info['sha256'], 'elfComparison':section,
            'elfSha256':hashlib.sha256(elf.read_bytes()).hexdigest(),
            'reachableInstructionsIncludingVectorSlots':len(seen),
            'normalCallGraphEdges':sorted({f'{src} -> {dest}' for _,src,dest,_ in calls}),
            'storeSites':{name:[{'pc':hex(pc),'op':op,'operands':args} for pc,op,args in sorted(rows)]
                          for name,rows in sorted(stores.items())}, 'stackMinimum':hex(minimum),
            'hobWritesExclusive':[hex(HOB_BASE), hex(HOB_BASE+64)], 'framebufferWritesExclusive':spans,
            'highReadAddresses':['0x94000000','0x97ffffa0'], 'vectorSlots':16,
            'scope':'ELF/FD code, ordinary direct control flow, checked PI stores and stack usage. Hardware DMA, synchronous fault behavior and RAM ownership are unmeasured.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', required=True, type=Path)
    parser.add_argument('--sec-elf', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = json.dumps(audit(args.fd, args.sec_elf), indent=2) + '\n'
    if args.report:
        with args.report.open('x', encoding='utf-8') as out:
            out.write(result)
    print(result, end='')


if __name__ == '__main__':
    main()
