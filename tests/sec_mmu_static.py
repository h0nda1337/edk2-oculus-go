"""Audit the finished MMU experiment against the linked SEC code and literals.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from sec_mem_static import (ALU, LOADS, STORES, compare_section, conditional, disassembly,
                            load_word, require, symbols, target, verify)
from sec_mmu_qemu import NAMES, digest

FUNCTIONS = {'Descriptor', 'MmuBuildTables', 'MmuSignal'}


def audit(fd, elf):
    info = verify(fd)
    names = symbols(elf)
    bias = int(info['secEntryAddress'], 16) - names['_ModuleEntryPoint']
    loc = {k: names[k] + bias for k in (*NAMES, *FUNCTIONS)}
    code, ranges = disassembly(elf, bias, FUNCTIONS)
    comparison = compare_section(fd, elf, loc, code, bias)
    owners = {pc: k for k, addresses in ranges.items() for pc in addresses}
    owners.update(dict.fromkeys(range(loc['_ModuleEntryPoint'], loc['MmuException'] + 4, 4), 'entry'))
    vectors = range(loc['MmuVectors'], loc['MmuVectors'] + 2048, 128)
    owners.update(dict.fromkeys(vectors, 'vectors'))
    pending = [loc['_ModuleEntryPoint'], *vectors]
    visited, control_writes, stores = set(), [], Counter()
    allowed = ALU | LOADS | {'cmn', 'lsl', 'lsr', 'ubfx', 'sbfx', 'umaddl'}
    while pending:
        pc = pending.pop()
        if pc in visited:
            continue
        require(pc in owners and 0x80081000 <= pc < 0x80085000, 'Control leaves mapped SEC')
        visited.add(pc)
        word, op, args = code[pc]
        require(word == load_word(fd, pc), 'ELF and FD disagree')
        if op == 'ret':
            require(args in ('', 'x30') or (args == 'x17' and owners[pc] == 'entry'), 'Unexpected return')
            continue
        if op in ('b', 'bl') or conditional(op):
            pending.append(target(args, bias))
            if op == 'b':
                continue
        elif op == 'msr':
            require(owners[pc] == 'entry', 'System register write outside reviewed entry')
            control_writes.append((pc, args.lower()))
        elif op == 'mrs':
            require(args.split(', ')[1].lower() in {'currentel','mpidr_el1','sctlr_el1','sctlr_el2',
                                                      'hcr_el2','par_el1'}, 'Unexpected system register read')
        elif op in ('at','ic','tlbi','dsb','isb'):
            require((op, args.lower()) in {('at','s1e1w, x0'),('at','s1e2w, x0'),('ic','iallu'),
                                          ('tlbi','vmalle1'),('tlbi','alle2'),('dsb','sy'),('isb','')},
                    'Unexpected maintenance or address translation operation')
        elif op in STORES:
            stores[owners[pc]] += 1
        else:
            require(op in allowed, f'Unreviewed instruction {op} at {pc:#x}')
        pending.append(pc+4)
    expected_writes = ['daifset, #0xf','vbar_el1, x15','vbar_el2, x15']
    for el, tlb in [(1,'vmalle1'),(2,'alle2')]:
        ctl = f'sctlr_el{el}'
        regs = [f'mair_el{el}, x11', f'tcr_el{el}, x12', f'ttbr0_el{el}, x10', f'{ctl}, x12']
        expected_writes.extend(regs)
        at = next(pc for pc,args in control_writes if args == regs[0])
        steps = [('msr',regs[0]),('msr',regs[1]),('msr',regs[2]),('isb',''),('tlbi',tlb),
                 ('dsb','sy'),('isb',''),('mrs',f'x12, {ctl}'),('orr','x12, x12, #0x1'),
                 ('msr',regs[3]),('isb',''),('mrs',f'x12, {ctl}')]
        for index, (op, args) in enumerate(steps):
            entry = at + index * 4
            require(entry in visited and code[entry][1:] == (op,args), f'Wrong EL{el} activation sequence')
    require([args for _,args in sorted(control_writes)] == expected_writes, 'Unexpected system write')
    for k in ('MmuException','MmuComplete','MmuRejected'):
        require(loc[k] in visited and load_word(fd,loc[k]) == 0x14000000, 'Missing terminal loop')
    require(set(stores) <= {'entry','MmuSignal','MmuBuildTables'}, 'Unexpected writer')
    return {'result':'PASS-STATIC-SEC-MMU','fdSha256':info['sha256'],'elfSha256':digest(elf.read_bytes()),
            'linkedText':comparison,'reachableInstructions':len(visited),'storeSites':dict(stores),
            'controlWriteOperands':expected_writes,'checkedActivationLevels':[1,2]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd',type=Path,required=True)
    parser.add_argument('--sec-elf',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    report = audit(args.fd.read_bytes(),args.sec_elf)
    with args.report.open('x',encoding='utf-8',newline='\n') as out:
        json.dump(report,out,indent=2)
        out.write('\n')
    print(report['result'], report['reachableInstructions'])
