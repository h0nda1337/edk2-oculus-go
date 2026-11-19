"""Recheck the exact reviewed SEC_C instructions, literal data and direct CFG.

Static inspection only, using upstream GNU binutils and the Python library.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
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


REVIEWED_FD = '3ee7a88df0d44ae7b68dc0ded6774b23a41e9e3f4ce0cffaef38b640ebc8e6f6'
ALU_AND_SYSTEM = {'add', 'sub', 'mov', 'movk', 'cmp', 'tst', 'adr', 'and', 'sbfx',
                  'mrs', 'msr', 'dsb'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def decode(elf, data, bias, start, end):
    listing = subprocess.check_output([
        'aarch64-linux-gnu-objdump', '-d', f'--start-address={start}',
        f'--stop-address={end}', str(elf)], text=True)
    instructions = {}
    for line in listing.splitlines():
        match = re.fullmatch(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)(?:\s+(.*))?', line)
        if match:
            pc = int(match[1], 16) + bias
            word = struct.unpack_from('<I', data, pc - BASE)[0]
            require(word == int(match[2], 16), f'FD disagrees with ELF at {pc:#x}')
            instructions[pc] = (match[3], (match[4] or '').split('//')[0].strip())
    require(list(instructions) == list(range(start + bias, end + bias, 4)),
            'Disassembled region is incomplete')
    return instructions


def branch_target(operands, bias):
    target = operands.split(',')[-1].strip().split(' ')[0]
    return bias + int(target, 16)


def constant(code, low_at, high_at, reg):
    op1, args1 = code[low_at]
    op2, args2 = code[high_at]
    low = re.fullmatch(reg + r', #0x([0-9a-f]+)', args1)
    high = re.fullmatch(reg + r', #0x([0-9a-f]+), lsl #16', args2)
    require(op1 == 'mov' and op2 == 'movk' and low and high, 'Constant construction changed')
    return int(low[1], 16) | (int(high[1], 16) << 16)


def audit(fd_path, elf):
    data = fd_path.read_bytes()
    header = verify(data)
    require(header['sha256'] == REVIEWED_FD, 'Unreviewed FD; inspect code before updating the pin')
    names = symbols(elf)
    entry = int(header['secEntryAddress'], 16)
    bias = entry - names['_ModuleEntryPoint']
    here = {name: names[name] + bias for name in ('SecCCall', 'SecCReturn', 'SecCComplete',
                                                   'EntryRejected', 'OculusGoSecColorCheckpoint')}
    leaf = here['OculusGoSecColorCheckpoint']
    size_listing = subprocess.check_output(['aarch64-linux-gnu-nm', '-S', elf], text=True)
    sizes = re.findall(r'^\w+\s+([0-9a-f]+)\s+[Tt]\s+OculusGoSecColorCheckpoint$',
                       size_listing, re.MULTILINE)
    require(len(sizes) == 1, 'Cannot identify C leaf extent')
    length = int(sizes[0], 16)
    code = {}
    for start, end in ((entry, here['SecCComplete'] + 4),
                       (here['EntryRejected'], here['EntryRejected'] + 4), (leaf, leaf + length)):
        code.update(decode(elf, data, bias, start - bias, end - bias))

    pending = [entry]
    seen = set()
    calls, returns, literals, accesses = [], [], [], []
    while pending:
        pc = pending.pop()
        if pc in seen:
            continue
        require(pc in code, f'Control flow escapes reviewed code at {pc:#x}')
        seen.add(pc)
        op, args = code[pc]
        if op == 'bl':
            require(pc == here['SecCCall'] and branch_target(args, bias) == leaf,
                    'Unexpected call')
            calls.append(hex(pc))
            pending.append(leaf)
            continue
        if op == 'ret':
            require(leaf <= pc < leaf + length and args in ('', 'x30'), 'Unexpected return')
            returns.append(hex(pc))
            pending.append(here['SecCReturn'])
            continue
        if op == 'b' or op.startswith('b.') or op in ('cbz', 'cbnz', 'tbz', 'tbnz'):
            pending.append(branch_target(args, bias))
            if op != 'b':
                pending.append(pc + 4)
            continue
        if op == 'ldr' and '[' not in args:
            target = branch_target(args, bias)
            require(BASE <= target <= BASE + len(data) - 8, 'Literal outside FD')
            value = struct.unpack_from('<Q', data, target - BASE)[0]
            literals.append((hex(pc), hex(target), hex(value)))
        elif op in ('ldp', 'stp', 'ldr', 'str', 'strb', 'sturb'):
            accesses.append((hex(pc), op, args))
        elif op not in ALU_AND_SYSTEM:
            raise ValueError(f'Unreviewed instruction {op} at {pc:#x}')
        pending.append(pc + 4)

    require(seen == set(code), 'Review ranges contain instructions not reached by the static CFG')
    require(calls == [hex(here['SecCCall'])] and len(returns) == 1, 'Call/return count changed')
    require(here['SecCReturn'] == here['SecCCall'] + 4, 'Unexpected link register destination')
    for pc in (here['EntryRejected'], here['SecCComplete']):
        require(struct.unpack_from('<I', data, pc - BASE)[0] == 0x14000000,
                'Unexpected terminal instruction')
    require(sorted(value for _, _, value in literals) == sorted(('0xff00ffffff', '0x80081000',
                                                                  '0x80088000')),
            'Unexpected literal load')
    require(data[64:4096] == bytes([data[64]]) * (4096 - 64) and data[64] in (0, 255),
            'Header padding is occupied')
    # Every data access on the reviewed graph must match its base register,
    # displacement, operand width and addressing mode.
    observed = {(int(pc, 16), op, args) for pc, op, args in accesses}
    expected = {
        (entry + 0x68, 'stp', 'x0, x1, [sp, #-48]!'), (entry + 0x6c, 'stp', 'x2, x3, [sp, #16]'),
        (entry + 0x70, 'stp', 'x12, x30, [sp, #32]'), (entry + 0x7c, 'ldp', 'x0, x1, [sp]'),
        (entry + 0x80, 'ldp', 'x2, x3, [sp, #16]'), (entry + 0x84, 'ldp', 'x12, x30, [sp, #32]'),
        (leaf + 0x0c, 'str', 'w0, [sp, #12]'), (leaf + 0x10, 'ldr', 'w1, [sp, #12]'),
        (leaf + 0x60, 'strb', 'w6, [x1]'), (leaf + 0x68, 'sturb', 'w5, [x1, #-2]'),
        (leaf + 0x6c, 'sturb', 'w4, [x1, #-1]'),
    }
    require(observed == expected, 'Memory access differs from review')
    for offset, insn in {
            0x00: ('sub', 'sp, sp, #0x10'), 0x9c: ('add', 'sp, sp, #0x10'),
            0x30: ('mov', 'x8, #0x10e0'), 0x34: ('add', 'x9, x2, x7'),
            0x38: ('mov', 'x1, x2'), 0x3c: ('mov', 'x3, #0x0'),
            0x5c: ('add', 'x10, x1, #0x2d0'), 0x64: ('add', 'x1, x1, #0x3'),
            0x70: ('cmp', 'x1, x10'), 0x78: ('add', 'x3, x3, #0x1'),
            0x7c: ('cmp', 'x3, #0x6'), 0x84: ('add', 'x2, x2, x8'),
            0x88: ('cmp', 'x9, x2'), 0x24: ('mov', 'x0, #0x0'),
            0xc8: ('mov', 'x0, #0x1'),
    }.items():
        require(code[leaf + offset] == insn, f'Leaf arithmetic changed at +{offset:#x}')
    for offset, opcode, dest in ((0x74, 'b.ne', 0x60), (0x80, 'b.ne', 0x40),
                                 (0x8c, 'b.ne', 0x38), (0x98, 'cbz', 0xc8),
                                 (0xcc, 'b', 0x34)):
        op, args = code[leaf + offset]
        require(op == opcode and branch_target(args, bias) == leaf + dest, 'Loop edge changed')
    first = constant(code, leaf + 0x1c, leaf + 0x28, 'x2')
    second = constant(code, leaf + 0x90, leaf + 0x94, 'x2')
    span = constant(code, leaf + 0x20, leaf + 0x2c, 'x7')
    spans = tuple((start, start + span) for start in (first, second))
    require(spans == band_ranges() and span == 32 * 6 * 0x2d0, 'Band ranges differ')
    cookie = constant(code, leaf + 4, leaf + 8, 'w0')
    require(cookie == 0x43434553, 'C stack witness mismatch')
    top = next(int(v, 16) for pc, _, v in literals if int(pc, 16) == entry + 0x60)
    require(top == BASE + 4096 and code[entry + 0x64] == ('mov', 'sp, x15'),
            'Temporary stack top mismatch')
    return {'result': 'PASS-STATIC-SEC-C', 'fdSha256': header['sha256'],
            'elfSha256': hashlib.sha256(elf.read_bytes()).hexdigest(),
            'entryBranches': header['entryBranches'], 'instructionsInNormalCFG': len(code),
            'directCallSites': calls, 'leafEntry': hex(leaf), 'leafBytes': length,
            'returnsToCaller': returns, 'returnSite': hex(here['SecCReturn']),
            'complete': hex(here['SecCComplete']), 'rejected': hex(here['EntryRejected']),
            'literalReads': sorted(literals), 'dataAccesses': sorted(accesses),
            'scratchSpMinimum': hex(top - 64), 'witness': hex(cookie),
            'stackWriteRangeExclusive': [hex(top - 64 + 12), hex(top)],
            'reviewedBandRangesExclusive': [[hex(a), hex(b)] for a, b in spans],
            'scope': 'Exact linked normal-control-flow image. Exceptions, DMA, physical translation and watchdog unmeasured.'}


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
