"""Independent QEMU observations of the real DXE allocator and the packaged arena.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from array import array
import struct
import sys

from sec_dxe_static import LIMIT, POOL
from sec_mem_qemu import require

PAGE = 4096
CORE_CASES = ('untested-resource','page-witness','pool-witness','map-type')
EXTRA_CASES = ('arena-readback', *CORE_CASES)
MASK = 0xa55ac33c5aa53cc3


def observe_arena(g,read,write,stop,sec,case):
    for mask in (MASK, MASK ^ 0xffffffffffffffff):
        stop(sec['TrialVerifyArenaPattern'],'read back whole arena')
        require(g.register(0)==mask,'Incorrect address-dependent sweep')
        expected=array('Q',(p^mask for p in range(POOL,LIMIT,8)))
        if sys.byteorder!='little':
            expected.byteswap()
        require(read(POOL,LIMIT-POOL)==expected.tobytes(),'SEC did not fill the complete arena')
        if case=='arena-readback':
            write(LIMIT-8,bytes(8))
            return
        require(g.command('s').startswith(('S','T')),'Cannot resume from sweep entry')
    stop(sec['HobConstructor'],'HOB construction after tested memory')
    require(read(POOL-PAGE,LIMIT-POOL+2*PAGE)==b'\xff'*(LIMIT-POOL+2*PAGE),
            'Arena and both guards were not restored before HOB construction')


def observe_services(g,read,write,stop,screen,core,base,case,after_memory=None):
    def word(address):
        return struct.unpack('<Q',read(address,8))[0]
    def arrive(name):
        stop(base+core[name],name)
    def returned(label):
        stop(g.register(30),label+' returned')
        require(g.register(0)==0,label+' returned an EFI error')

    unexpected = []
    if case!='untested-resource':
        unexpected.append('TrialDxeRejected')
    if case in ('valid','icache'):
        unexpected.append('TrialMemoryRejected')
    for name in unexpected:
        require(g.command(f'Z1,{base+core[name]:x},4')=='OK','Cannot monitor '+name)

    pos=POOL
    while True:
        kind,n=struct.unpack('<HH',read(pos,4))
        require(8<=n<=4096 and POOL<=pos<POOL+4096,'Resource HOB missing')
        if kind==3:
            break
        pos+=n
    attr=struct.unpack('<I',read(pos+28,4))[0]
    require(attr & 4,'SEC omitted EFI_RESOURCE_ATTRIBUTE_TESTED')
    if case=='untested-resource':
        write(pos+28,struct.pack('<I',attr & ~4))
        arrive('TrialDxeRejected')
        return 'TrialDxeRejected','branch',{'resourceRejectedBeforeInit':True}

    low=(word(POOL+40)+PAGE-1)&-PAGE
    high=word(POOL+32)
    arrive('CoreInitializeMemoryServices')
    screen('core')
    ptr,base_out,length_out=(g.register(i) for i in range(3))
    require(word(ptr)==POOL,'Upstream initializer received a different PHIT')
    returned('CoreInitializeMemoryServices')
    require(word(base_out)==low and word(length_out)==high-low,'Incorrect upstream allocator window')
    arrive('__wrap_CoreInitializeImageServices')
    require(g.register(0)==POOL,'Later DxeMain call did not receive the original HOB list')
    st=word(base+core['gDxeCoreST'])
    require(low<=st<high-120 and read(st,8)==b'IBI SYST','Invalid system table')
    rt=word(st+88)
    require(low<=rt<high-24 and read(rt,8)==b'RUNTSERV' and word(st+96)==base+core['mBootServices'],
            'Invalid runtime or Boot Services table')
    arrive('CoreAllocatePages')
    screen('services')
    require([g.register(i) for i in range(3)]==[0,2,2],'Missing 2-page EfiLoaderData request')
    page_out=g.register(3)
    returned('AllocatePages')
    pages=word(page_out)
    arrive('CoreAllocatePool')
    require((g.register(0),g.register(1))==(4,257),'Missing EfiBootServicesData pool request')
    pool_out=g.register(2)
    returned('AllocatePool')
    pool=word(pool_out)
    require(low<=pages<=high-8192 and pages%PAGE==0 and low<=pool<=high-257 and
            (pool+257<=pages or pages+8192<=pool),'Allocated addresses overlap or escape the window')
    arrive('TrialVerifyAllocations')
    require(g.register(0)==pages and g.register(1)==pool,'Wrong allocation witness pointers')
    require(read(pages,8192)==b''.join(struct.pack('<Q',p^0xa55a1234eeddbb66)
                                       for p in range(pages,pages+8192,8)) and
            read(pool,257)==bytes((0xc3^i)&255 for i in range(257)),'Guest allocation witnesses differ')
    evidence={'initReturnedSuccess':True,'freeWindow':[hex(low),hex(high)],'pages':hex(pages),
              'pool':hex(pool),'systemTable':hex(st),'runtimeTable':hex(rt),'witnessBytes':8449}
    if case in ('page-witness','pool-witness'):
        address=pages+8191 if case=='page-witness' else pool+256
        write(address,bytes([read(address,1)[0]^1]))
        arrive('TrialMemoryRejected')
        return 'TrialMemoryRejected','services',evidence

    def observe_map(expected,damage=False):
        arrive('CoreGetMemoryMap')
        size_ptr,buffer,key_ptr,stride_ptr,version_ptr=(g.register(i) for i in range(5))
        returned('GetMemoryMap')
        size,stride=word(size_ptr),word(stride_ptr)
        require(40<=stride<=size<=2048 and size%stride==0 and read(version_ptr,4)==b'\x01\0\0\0',
                'Unexpected map descriptor layout')
        ranges=[]
        for off in range(0,size,stride):
            kind,pa,va,count,_=struct.unpack('<I4xQQQQ',read(buffer+off,40))
            require(count and pa%PAGE==0 and va==0 and low<=pa<pa+count*PAGE<=high,'Invalid memory descriptor')
            ranges.append((pa,pa+count*PAGE,kind,off))
        ranges.sort()
        require(ranges[0][0]==low and ranges[-1][1]==high and
                all(b[0]==a[1] for a,b in zip(ranges,ranges[1:])),'Gaps or overlap in live map')
        def covering(address,length):
            return next((r for r in ranges if r[0]<=address and address+length<=r[1]),None)
        span=covering(pages,8192)
        require(span and span[2]==expected and covering(st,120)[2]==6 and covering(rt,24)[2]==6,
                'Wrong page or service table memory type')
        if expected==2:
            require(covering(pool,257)[2]==4,'Live pool missing from BootServicesData')
        if damage:
            write(buffer+span[3],struct.pack('<I',4))
        return word(key_ptr),len(ranges)

    key_live,n_live=observe_map(2,case=='map-type')
    if case=='map-type':
        arrive('TrialMemoryRejected')
        return 'TrialMemoryRejected','services',{**evidence,'alteredDescriptorRejected':True}
    arrive('CoreFreePool')
    require(g.register(0)==pool,'Unexpected FreePool argument')
    returned('FreePool')
    arrive('CoreFreePages')
    require(g.register(0)==pages and g.register(1)==2,'Unexpected FreePages arguments')
    returned('FreePages')
    key_free,n_free=observe_map(7)
    require(key_free!=key_live,'Memory map key did not change')
    evidence.update(mapKeys=[key_live,key_free], mapDescriptorCounts=[n_live,n_free],
                    loaderPagesReturnedToConventional=True, freePoolSuccess=True)
    if after_memory:
        return after_memory(evidence)
    arrive('TrialMemoryComplete')
    return 'TrialMemoryComplete','memory',evidence
