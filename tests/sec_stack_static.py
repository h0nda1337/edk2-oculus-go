"""Check the final in-place SEC machine code and its direct control flow.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from sec_mem_static import (ALU, LOADS, STORES, compare_section, conditional, disassembly,
                            load_word, require, symbols, target, verify)
from sec_stack_qemu import NAMES, digest

C_FUNCTIONS = {'SecStackFrames', 'SecMemValidateHob', 'SecMemConstructHob', 'HobConstructor'}
SYSTEM = [('mrs','x9, currentel'), ('mrs','x10, mpidr_el1'), ('mrs','x11, sctlr_el1'),
          ('mrs','x11, sctlr_el2'), ('mrs','x13, daif'), ('msr','daifset, #0xf'),
          ('msr','vbar_el1, x15'), ('msr','vbar_el2, x15'), ('isb',''),
          ('dsb','sy'), ('dsb','sy'), ('dsb','sy')]


def audit(fd, elf):
    info = verify(fd)
    names = symbols(elf)
    bias = int(info['secEntryAddress'], 16) - names['_ModuleEntryPoint']
    sym = {k: names[k] + bias for k in (*NAMES, 'StackCheckGuards', 'SecMemConstructHob')}
    code, ranges = disassembly(elf, bias, C_FUNCTIONS)
    comparison = compare_section(fd, elf, sym, code, bias)
    owners = {pc: func for func, addresses in ranges.items() for pc in addresses}
    owners.update(dict.fromkeys(range(sym['_ModuleEntryPoint'], sym['StackException']+4, 4), 'entry'))
    vectors = range(sym['StackVectors'], sym['StackVectors'] + 2048, 128)
    owners.update(dict.fromkeys(vectors, 'vectors'))
    pending = [sym['_ModuleEntryPoint'], *vectors]
    visited, calls, system, stores = set(), set(), [], Counter()
    while pending:
        pc = pending.pop()
        if pc in visited:
            continue
        require(pc in owners and pc in code, f'Unexpected control target {pc:#x}')
        visited.add(pc)
        word, op, args = code[pc]
        owner = owners[pc]
        require(load_word(fd, pc) == word, 'Packaged instruction changed')
        if op == 'ret':
            require((owner in C_FUNCTIONS or sym['StackCheckGuards'] <= pc < sym['StackEntryRejected'])
                    and args in ('','x30'), 'Unexpected return')
            continue
        if op in ('bl','b') or conditional(op):
            dest = target(args, bias)
            if op == 'bl' or (owner in C_FUNCTIONS and owners.get(dest) != owner):
                allowed = C_FUNCTIONS | {'StackCheckGuards'}
                require(dest in {sym[k] for k in allowed}, 'Unexpected call target')
                calls.add((owner, next(k for k in allowed if sym[k] == dest)))
            pending.append(dest)
            if op == 'b':
                continue
        elif op in STORES:
            stores[owner] += 1
        elif op in ('mrs','msr','dsb','isb'):
            require(owner == 'entry','Unexpected system instruction')
            system.append((op, args.lower()))
        else:
            require(op in ALU | LOADS | {'cmn','eor','mvn','lsl'}, f'Unexpected instruction {op} at {pc:#x}')
        pending.append(pc+4)
    require(Counter(system) == Counter(SYSTEM), 'Changed system state or barriers')
    require(calls == {('entry','StackCheckGuards'), ('entry','SecStackFrames'),
                      ('SecStackFrames','SecStackFrames'), ('SecStackFrames','SecMemConstructHob'),
                      ('SecMemConstructHob','HobConstructor'), ('SecMemConstructHob','SecMemValidateHob')},
            'Different reachable call graph')
    require(stores == {'entry':12, 'SecStackFrames':3, 'SecMemConstructHob':1, 'HobConstructor':5},
            'Store instruction sites differ')
    for name in ('StackComplete', 'StackEntryRejected', 'StackMemoryRejected', 'StackGuardRejected',
                 'StackFrameRejected', 'StackException'):
        require(sym[name] in visited and load_word(fd,sym[name]) == 0x14000000, f'Unexpected terminal {name}')
    return {'result':'PASS-STATIC-SEC-STACK', 'fdSha256':info['sha256'], 'elfSha256':digest(elf.read_bytes()),
            'linkedText':comparison, 'reachableInstructions':len(visited),
            'storeInstructions':dict(stores), 'callEdges':sorted(calls)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path, required=True)
    parser.add_argument('--sec-elf', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.fd.read_bytes(), args.sec_elf)
    with args.report.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print(report['result'], report['reachableInstructions'])
