"""Observe the packaged LZMA -> HOB -> relocated upstream DxeMain handoff at EL1 and EL2.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from uuid import UUID

from sec_mem_qemu import (BASE, FB_BASE, GUARD, RAM_START, SIZE, SURFACE_BYTES, band_ranges,
                          check_vectors, digest, guest, require, symbols, until, verify, watch)
from sec_dxe_static import CORE, LIMIT, POOL, arguments, inspect
from sec_mmu_qemu import PAGE, TABLE, TOP, WINDOWS

ROOT = Path(__file__).resolve().parents[1]
STACK = TOP - 16*PAGE
CASES = ('valid','icache','dcache','wrong-x0','relocated','dirty-pool','dirty-guard','bad-fv','bad-module')
MODULE = UUID('f8e21975-0899-4f58-a4be-5525a9c6d77a')


def screen(stage):
    data = bytearray(b'\xa5' * (SURFACE_BYTES+2*GUARD))
    if stage == 'untouched':
        return data
    side = {'hobs':'ff0000','fv':'00ffff','branch':'ffff00','core':'00ff00',
            'services':'0080ff','memory':'ff0000','image':'00ffff',
            'relocated-hobs':'0080ff','gcd':'ff00ff','ctors':'ff0000','dxe-table':'ffff00','tables':'00ff00',
            'debug-locator':'0080ff','debug-image':'0000ff'}[stage]
    center = {'core':'ff00ff','memory':'00ff00','image':'ff00ff','relocated-hobs':'ffffff','gcd':'ffff00',
              'ctors':'00ffff','dxe-table':'ff0000','tables':'0080ff',
              'debug-locator':'ffff00','debug-image':'ffff00'}.get(stage,'000000')
    row = b''.join(bytes.fromhex(c)*288 for c in ('ffffff',side,center,side,'ffffff'))
    for start,end in band_ranges():
        pos = start - FB_BASE + GUARD
        data[pos:pos+end-start] = row*32
    return data


def tables(el, text_start, text_end, debug_span=()):
    windows = (*WINDOWS,POOL)
    buf = bytearray(8*PAGE)
    def put(off,val):
        struct.pack_into('<Q',buf,off,val)
    put(16,TABLE+PAGE+3)
    for i,va in enumerate(windows):
        put(PAGE+((va>>21)&511)*8,TABLE+(i+2)*PAGE+3)
    rx = 0x787 | ((1<<54) if el == 1 else 0)
    rw = 0x707 | (1<<54) | ((1<<53) if el == 1 else 0)
    for lo,hi in ((0x80081000,0x80100000),(POOL,LIMIT),(STACK,TOP),*debug_span,*band_ranges()):
        for va in range(lo,hi,PAGE):
            off=(windows.index(va & ~0x1fffff)+2)*PAGE+((va>>12)&511)*8
            put(off,va | (rx if va < 0x80100000 or text_start <= va < text_end else rw))
    return buf


def hobs(read, fv, target, meta):
    blob=read(POOL, PAGE)
    top,low,free_top,free_low,end=struct.unpack_from('<5Q',blob,16)
    require((low,top)==(POOL,LIMIT) and POOL < end < POOL+PAGE and end+8==free_low<=free_top,
            'Incorrect PHIT arena')
    offset=0
    found=[]
    module=None
    resources=[]
    while offset < free_low-POOL:
        kind,size,_=struct.unpack_from('<HHI',blob,offset)
        require(size>=8 and size%8==0 and offset+size<=free_low-POOL, 'Malformed HOB chain')
        if kind==5:
            found.append(struct.unpack_from('<QQ',blob,offset+8))
        if kind==3:
            resources.append(struct.unpack_from('<IIQQ',blob,offset+24))
        if kind==2 and size==72 and blob[offset+48:offset+64]==CORE.bytes_le:
            base,length=struct.unpack_from('<QQ',blob,offset+24)
            entry,=struct.unpack_from('<Q',blob,offset+64)
            require(module is None and blob[offset+8:offset+24]==MODULE.bytes_le and
                    free_top<=base and base+length<=LIMIT and length==meta['peImageBytes']
                    and target==entry==base+meta['entryRva'],'Invalid DXE module HOB')
            module=(offset,base,length)
        if kind==0xffff:
            require(size==8 and POOL+offset==end,'Incorrect HOB terminator')
            break
        offset+=size
    expected = [(0, 0x407 if meta['result'] != 'PASS-STATIC-SEC-DXE' else 0x403, POOL, LIMIT-POOL)]
    if meta['result'] in ('PASS-STATIC-DXE-GCD','PASS-STATIC-DXE-TABLES','PASS-STATIC-DXE-DEBUG'):
        expected.append((5, 0x403, STACK, TOP-STACK))
    require(POOL+offset==end and kind==0xffff and module and resources==expected
            and len(found)==2 and found[0]==(0x80081000,0x7f000),'Missing resource, module, or FV HOB')
    addr,size=found[1]
    require(module[1]+module[2]<=addr and size==len(fv) and addr+size<=LIMIT and read(addr,size)==fv,
            'Decompressed guest FV differs byte-for-byte from build')
    return (*module, addr, free_top-free_low)


def exercise(path, fd, fv, sec, core, meta, harness, el, case, memory=None):
    load=BASE+(0x100000 if case=='relocated' else 0)
    bias=load-BASE
    sec={k:v+bias for k,v in sec.items()}
    debug_span = ((int(meta["debugPage"],16),int(meta["debugPage"],16)+PAGE),) if "debugPage" in meta else ()
    original=bytearray(fd)
    with guest(path,harness,el,load) as (g,ram):
        g.stream.settimeout(30)
        def read(addr,n):
            data=os.pread(ram,n,addr-RAM_START)
            require(len(data)==n,'Short RAM read')
            return data
        def write(addr,data):
            require(os.pwrite(ram,data,addr-RAM_START)==len(data),'Short RAM injection')
        def stop(addr,label):
            try:
                until(g,addr)
            except Exception as e:
                raise RuntimeError(f'{label}: PC={g.register(32):#x}, LR={g.register(30):#x}, x0={g.register(0):#x}') from e
        def check_screen(stage):
            expect=screen(stage)
            require(read(FB_BASE-GUARD,len(expect))==expect,f'Unexpected two-band surface at {stage}')
        for cmd in ('qSupported:qXfer:features:read+','qXfer:features:read:target.xml:0,fff','Hg0','?'):
            g.command(cmd)
        require(read(load,SIZE)==fd,'Wrong loaded FD')
        write(FB_BASE-GUARD,screen('untouched'))
        g.set_register(33,0x3c0 | (9 if el==2 else 5))
        g.set_register(0,0x82000008 if case=='wrong-x0' else 0x82000000)
        g.set_register(31,0x90010000)
        g.set_register(18,{'icache':0x1000,'dcache':4}.get(case,0))
        g.set_register(20,load)
        g.set_register(32,0x41000000+(64 if el==2 else 0))
        stop(load,'firmware entry')
        previous=RAM_START
        for begin,end in sorted(((POOL,LIMIT),(TABLE,TABLE+8*PAGE),(STACK,TOP),*debug_span,*band_ranges())):
            watch(g,2,previous,begin)
            previous=end
        watch(g,2,previous,RAM_START+(2<<30))
        watch(g,3,0x94000000,0x98000000)
        if case in ('dirty-pool','dirty-guard'):
            addr=POOL+PAGE if case=='dirty-pool' else LIMIT+PAGE-8
            write(addr,b'\x13')
            original[addr-load]=0x13
        success=case in ('valid','icache','bad-module') or (memory and case in memory.CORE_CASES)
        if memory and (success or case in ('arena-readback','bad-fv')):
            memory.observe_arena(g,read,write,stop,sec,case)
        runtime={}
        stage='untouched'
        if case=='arena-readback':
            terminal='MmuRejected'
            stop(sec[terminal],terminal)
        elif case=='bad-fv':
            stop(sec['DecompressFirstFv'],'decompress')
            check_screen('hobs')
            stop(g.register(30),'decompress return')
            require(g.register(0)==0,'Decompression failed before control')
            body=read(POOL,PAGE)
            offset=0
            inner=[]
            while offset+8<=PAGE:
                t,n,_=struct.unpack_from('<HHI',body,offset)
                if t==0xffff:
                    break
                require(n>=8 and n%8==0 and offset+n<=PAGE,'Bad HOB')
                if t==5:
                    addr,size=struct.unpack_from('<QQ',body,offset+8)
                    if POOL<=addr and addr+size<=LIMIT:
                        inner.append((addr,size))
                offset+=n
            require(len(inner)==1 and read(*inner[0])==fv,'Missing original decompressed FV')
            addr=inner[0][0]+50
            write(addr,bytes([read(addr,1)[0]^1]))
            terminal='MmuRejected'
            stop(sec[terminal],terminal)
            stage='hobs'
        elif success:
            for name in ('MmuRejected','MmuException','CpuDeadLoop','DebugAssert'):
                if name in sec:
                    require(g.command(f'Z1,{sec[name]:x},4')=='OK','Cannot monitor '+name)
            stop(sec['DecompressFirstFv'],'decompress')
            check_screen('hobs')
            stop(sec['LoadPeCoffImage'],'load core')
            check_screen('fv')
            stop(sec['MmuTranslated'],'translated SEC')
            require(g.register(12)&0x1005==(0x1001 if case=='icache' else 1),'Unexpected SCTLR')
            stop(sec['TrialDxeBranch'],'DXE transfer')
            check_screen('branch')
            entry=g.register(16)
            require(g.register(0)==POOL,'Wrong HOB pointer in x0')
            offset,base,_,fv_base,free_bytes=hobs(read,fv,entry,meta)
            a,b=meta['textRva']
            checked=tables(el,base+a,base+b,debug_span)
            require(read(TABLE,len(checked))==checked,'Incorrect W^X mapping or guards')
            if memory:
                original_text=read(base+a,b-a)
                hob_bytes=struct.unpack('<Q',read(POOL+40,8))[0]-POOL
                original_hobs=read(POOL,hob_bytes)
            for name in ('CpuDeadLoop','DebugAssert','DefaultExceptionHandler'):
                if name in core:
                    require(g.command(f'Z1,{base+core[name]:x},4')=='OK','Cannot monitor core '+name)
            require(g.command('s').startswith(('T','S')) and g.register(32)==entry,'Failed to enter relocated PE')
            stop(base+core['DxeMain'],'upstream DxeMain')
            stop(base+core['InitializeDebugAgent'],'DXE callback')
            require(g.register(0)==3 and g.register(1)==POOL and g.register(2)==0,'Wrong callback arguments')
            if case=='bad-module':
                write(POOL+offset+48,bytes(16))
            if memory and case!='bad-module':
                extra = {'constructors': meta['constructors']} if 'constructors' in meta else {}
                terminal,stage,measurement=memory.observe_services(g,read,write,stop,check_screen,core,base,case,**extra)
            else:
                terminal='TrialDxeRejected' if case=='bad-module' else 'TrialDxeComplete'
                stop(base+core[terminal],terminal)
                stage='branch' if case=='bad-module' else 'core'
                measurement={}
            if memory:
                require(read(fv_base,len(fv))==fv and read(base+a,b-a)==original_text and
                        read(TABLE,len(checked))==checked,'Core altered firmware, executable text or translations')
                if case not in ('bad-module','untested-resource') and not measurement.get('relocatedHobs'):
                    # Upstream GCD may reuse the original HOB storage after migration.
                    require(read(POOL,hob_bytes)==original_hobs,'Core altered the input HOB list')
            runtime={**measurement,'coreBase':hex(base),'entry':hex(entry),'dxeMain':hex(base+core['DxeMain']),
                     'terminalPc':hex(g.register(32)),'innerFvBase':hex(fv_base),'remainingArenaBytes':free_bytes,
                     'innerFvMatched':True,'pageTablesMatched':True}
        else:
            terminal='MmuRejected'
            stop(sec[terminal],terminal)
        check_screen(stage)
        actual=bytearray(read(load,SIZE))
        spans=((POOL,LIMIT),(TABLE,TABLE+8*PAGE),(STACK,TOP)) if success else (
            ((POOL,LIMIT),(STACK,TOP)) if case in ('bad-fv','arena-readback') else (((STACK,TOP),) if case.startswith('dirty-') else ()))
        if runtime.get("debugPageTouched"):
            spans += debug_span
        for lo,hi in spans:
            actual[lo-load:hi-load]=original[lo-load:hi-load]
        require(actual==original,'FD or guard outside owned workspace changed')
        return {'el':el,'case':case,'terminal':terminal,'lastPattern':stage,'fullScreenAndGuardsMatched':True,
                'unexpectedGuestRamWrites':0,'highPoolAccesses':0,**runtime}


def main():
    a=arguments()
    fd,fv,pe=(p.read_bytes() for p in (a.fd,a.fv,a.pe))
    memory=None
    if a.debug_image:
        import dxe_debug_trace as memory
    elif a.tables:
        import dxe_tables_trace as memory
    elif a.gcd:
        import dxe_gcd_trace as memory
    elif a.memory:
        import dxe_memory_trace as memory
    meta=inspect(fd,fv,pe,a.sec_elf,a.dxe_elf,a.memory,a.gcd,a.tables,a.debug_image)
    names=symbols(a.sec_elf)
    bias=int(verify(fd)['secEntryAddress'],16)-names['_ModuleEntryPoint']
    sec={k:v+bias for k,v in names.items()}
    core=symbols(a.dxe_elf)
    vectors=check_vectors(fd,{'SecMemVectors':sec['MmuVectors'],'SecMemException':sec['MmuException']})
    cases=[]
    with tempfile.TemporaryDirectory() as tmp:
        obj,harness=(Path(tmp)/n for n in ('entry.o','entry.bin'))
        subprocess.run(['aarch64-linux-gnu-gcc','-c',ROOT/'tests/entry_harness.S','-o',obj],check=True)
        subprocess.run(['aarch64-linux-gnu-objcopy','-O','binary',obj,harness],check=True)
        scenarios = (*CASES,*memory.EXTRA_CASES) if memory else CASES
        if a.debug_image:
            # Run the new stage and its fault controls before the inherited suite.
            scenarios = ('valid',*memory.CONTROLS,*(c for c in scenarios if c != 'valid' and c not in memory.CONTROLS))
        for el in (1,2):
            for case in scenarios:
                print(f'EL{el} {case}',flush=True)
                cases.append(exercise(a.fd.resolve(),fd,fv,sec,core,meta,harness,el,case,memory))
    a.report.write_text(json.dumps({**meta,'result':meta['result'].replace('PASS-STATIC-','PASS-QEMU-'),'vectors':vectors,'cases':cases},indent=2)+'\n')


if __name__=='__main__':
    main()
