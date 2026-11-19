"""Inspect the delivered SEC_DXE firmware, guided section, inner FV and core image.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
import lzma
from pathlib import Path
import struct
import re
import subprocess
from uuid import UUID

from sec_mem_qemu import BASE, digest, require, symbols, verify

CORE = UUID('d6a2cb7f-6a18-4e2f-b43b-9920a733700a')
GUIDED = UUID('ee4e5898-3914-4259-9d6e-dc7bd79403cf')
POOL, LIMIT = 0x80200000, 0x80380000


def align(n, unit):
    return (n + unit - 1) & -unit


def files(fv):
    length, = struct.unpack_from('<Q', fv, 32)
    header, = struct.unpack_from('<H', fv, 48)
    require(fv[40:44] == b'_FVH' and length == len(fv) and 56 <= header <= length
            and header % 2 == 0 and sum(struct.unpack_from(f'<{header//2}H', fv)) % 65536 == 0,
            'Invalid FV header')
    pos = align(header, 8)
    while pos < length and fv[pos:pos+24] != b'\xff'*min(24,length-pos):
        require(pos+24 <= length and not fv[pos+19] & 1, 'Unsupported FFS header')
        size = int.from_bytes(fv[pos+20:pos+23], 'little')
        require(24 <= size <= length-pos, 'FFS size outside FV')
        yield fv[pos+18], UUID(bytes_le=fv[pos:pos+16]), fv[pos+24:pos+size]
        pos = align(pos+size, 8)
    require(all(b == 255 for b in fv[pos:]), 'Unexpected occupied FV tail')


def sections(data):
    pos = 0
    while pos < len(data):
        require(pos+4 <= len(data), 'Truncated section')
        size = int.from_bytes(data[pos:pos+3], 'little')
        require(4 <= size <= len(data)-pos and size != 0xffffff, 'Invalid section bounds')
        yield data[pos+3], data[pos:pos+size]
        pos = align(pos+size, 4)


def unique(items):
    items = list(items)
    require(len(items) == 1, f'Expected one match, got {len(items)}')
    return items[0]


def inspect(fd, fv, pe, sec_elf, dxe_elf, memory=False, gcd=False, tables=False):
    gcd = gcd or tables
    extra = {}
    info = verify(fd)
    outer = list(files(fd[0x1000:0x80000]))
    require([t for t, _, _ in outer if t != 0xf0] == [3,11], 'Unexpected outer executables or FVs')
    wrapped = unique(body for t, _, body in outer if t == 11)
    guided = unique(sec for t, sec in sections(wrapped) if t == 2)
    off, attr = struct.unpack_from('<HH', guided, 20)
    require(guided[4:20] == GUIDED.bytes_le and 24 <= off < len(guided) and attr & 1,
            'Unexpected guided section')
    data = guided[off:]
    out_size, = struct.unpack_from('<Q', data, 5)
    require(len(fv)+4 <= out_size <= len(fv)+8192 and out_size < LIMIT-POOL, 'Unexpected LZMA size')
    decoded = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(data, max_length=out_size+1)
    require(len(decoded) == out_size and unique(sec[4:] for t,sec in sections(decoded) if t == 0x17) == fv,
            'Embedded firmware volume differs from build')
    inner = [(t,g,b) for t,g,b in files(fv) if t != 0xf0]
    require([(t,g) for t,g,_ in inner] == [(5,CORE)], 'Unexpected DXE FV content')
    require(unique(sec[4:] for t,sec in sections(inner[0][2]) if t == 0x10) == pe, 'Packaged DXE PE mismatch')
    nt, = struct.unpack_from('<I',pe,60)
    pe_offset = fv.find(pe)
    require(pe_offset >= 0 and pe_offset % 8 == nt % 8 == 0, 'Unaligned in-place PE or NT header')
    machine,count = struct.unpack_from('<HH',pe,nt+4)
    opt_size, = struct.unpack_from('<H',pe,nt+20)
    opt = nt+24
    entry, = struct.unpack_from('<I',pe,opt+16)
    size, = struct.unpack_from('<I',pe,opt+56)
    require(pe[:2] == b'MZ' and pe[nt:nt+4] == b'PE\0\0' and machine == 0xaa64 and
            struct.unpack_from('<H',pe,opt)[0] == 0x20b and struct.unpack_from('<H',pe,opt+68)[0] == 11,
            'Unexpected DXE PE')
    text = []
    for i in range(count):
        pos = opt+opt_size+i*40
        vsize,rva,raw = struct.unpack_from('<III',pe,pos+8)
        flags, = struct.unpack_from('<I',pe,pos+36)
        if flags & 0x20000000:
            require(not flags & 0x80000000 and rva % 4096 == 0, 'Writable or unaligned executable section')
            text.append((rva,align(rva+max(vsize,raw),4096)))
    start,end = unique(text)
    core_names = symbols(dxe_elf)
    checkpoints = ('TrialDxeRejected','TrialDxeComplete')
    if memory or gcd:
        checkpoints = ('TrialDxeRejected','TrialMemoryComplete','TrialMemoryRejected',
                       'CoreInitializeMemoryServices','__wrap_CoreInitializeImageServices',
                       'CoreAllocatePool','CoreFreePool','CoreAllocatePages','CoreFreePages','CoreGetMemoryMap')
        if gcd:
            checkpoints = tuple(n for n in checkpoints if n != 'TrialMemoryComplete') + (
                'CoreInitializeImageServices','CoreInitializeGcdServices','__wrap_CoreInitializeGcdServices',
                'TrialGcdRejected','TrialGcdComplete','TrialCheckGcdMap','CoreGetMemorySpaceMap')
        if tables:
            checkpoints = tuple(n for n in checkpoints if n != 'TrialGcdComplete') + (
                '__wrap_ProcessLibraryConstructorList','__wrap_CoreInitializeDebugImageInfoTable',
                'TrialConstructorsRejected','TrialTablesRejected','TrialTablesComplete')
            listing = subprocess.check_output(['aarch64-linux-gnu-objdump','-d',
                '--disassemble=ProcessLibraryConstructorList',dxe_elf],text=True)
            ctors = re.findall(r'\bbl\s+[0-9a-f]+ <(\w+Constructor)>',listing)
            require(len(ctors) == 5 and set(ctors) == {
                'BaseDebugLibSerialPortConstructor','UefiRuntimeServicesTableLibConstructor',
                'UefiBootServicesTableLibConstructor','UefiLibConstructor',
                'DxeExtractGuidedSectionLibConstructor'}, 'Unexpected linked constructor list')
            extra['constructors'] = ctors
        assembly = subprocess.check_output(['aarch64-linux-gnu-objdump','-d','--disassemble=DxeMain',dxe_elf],text=True)
        calls = re.findall(r'\bbl\s+[0-9a-f]+ <([^>]+)>',assembly)
        order = [calls.index(n) for n in ('InitializeDebugAgent','CoreInitializeMemoryServices',
                                         '__wrap_CoreInitializeImageServices')]
        if gcd:
            order.append(calls.index('__wrap_CoreInitializeGcdServices'))
        if tables:
            installs = [i for i, name in enumerate(calls) if name == 'CoreInstallConfigurationTable']
            require(len(installs) >= 3, 'Missing configuration table calls')
            order.extend([calls.index('__wrap_ProcessLibraryConstructorList'),*installs[:3],
                          calls.index('__wrap_CoreInitializeDebugImageInfoTable')])
        require(order == sorted(order) and 'CoreInitializeImageServices' not in calls, 'Unexpected DxeMain path')
    require(entry == core_names['_ModuleEntryPoint'] and start <= entry < end <= size and
            all(start <= core_names[n] < end for n in
        ('DxeMain','InitializeDebugAgent',*checkpoints)), 'Checkpoint outside core text')
    sec_names = symbols(sec_elf)
    bias = int(info['secEntryAddress'],16)-sec_names['_ModuleEntryPoint']
    branch = bias+sec_names['TrialDxeBranch']-BASE
    require(fd[branch:branch+4] == bytes.fromhex('00023fd6') and not any(n in sec_names for n in checkpoints),
            'Missing SEC indirect handoff or duplicated DXE checkpoint')
    return {**extra,'result':'PASS-STATIC-DXE-TABLES' if tables else 'PASS-STATIC-DXE-GCD' if gcd else 'PASS-STATIC-DXE-MEM' if memory else 'PASS-STATIC-SEC-DXE','fdSha256':info['sha256'],'innerFvSha256':digest(fv),
            'peSha256':digest(pe),'secElfSha256':digest(sec_elf.read_bytes()),'coreElfSha256':digest(dxe_elf.read_bytes()),
            'innerFvBytes':len(fv),'peImageBytes':size,'entryRva':entry,'textRva':[start,end],
            'coreGuid':str(CORE),'lzmaBytes':len(data)}


def arguments():
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('fd','fv','pe','sec-elf','dxe-elf','report'):
        parser.add_argument('--'+k,type=Path,required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--tables',action='store_true',help='Audit DXE constructors and configuration tables')
    group.add_argument('--gcd',action='store_true',help='Audit the DXE image services and GCD profile')
    group.add_argument('--memory',action='store_true',help='Audit the DXE memory services profile')
    return parser.parse_args()


if __name__ == '__main__':
    a=arguments()
    result=inspect(a.fd.read_bytes(),a.fv.read_bytes(),a.pe.read_bytes(),a.sec_elf,a.dxe_elf,a.memory,a.gcd,a.tables)
    a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
