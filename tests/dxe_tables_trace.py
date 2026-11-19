"""Verify the linked DXE constructors and read back configuration entries from guest RAM.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import struct
from uuid import UUID

import dxe_gcd_trace as gcd
from dxe_memory_trace import observe_arena
from sec_dxe_static import POOL, LIMIT
from sec_mem_qemu import require
from sec_mmu_qemu import TOP, PAGE

DXE = UUID('05ad34ba-6f02-4214-952e-4da0398e2bb9')
HOB = UUID('7739f24c-93d7-11d4-9a3a-0090273fc14d')
TYPES = UUID('4c19049f-4137-4dd3-9c10-8b97a83ffdfa')
CONTROLS = ('ctor-cache', 'config-count', 'dxe-pointer', 'hob-source', 'hob-content', 'duplicate-guid')
CORE_CASES = gcd.CORE_CASES + CONTROLS + ('table-order',)
EXTRA_CASES = gcd.EXTRA_CASES + CONTROLS + ('table-order',)


def observe_services(g, read, write, stop, screen, core, base, case, constructors, after_tables=None):
    def arrive(name):
        stop(base+core[name], name)

    def word(address):
        return struct.unpack('<Q',read(address,8))[0]

    def put(address, value):
        write(address, struct.pack('<Q',value))

    def check(evidence):
        st = int(evidence['systemTable'],16)
        handle = int(evidence['imageHandle'],16)
        hobs = int(evidence['relocatedHobs'],16)
        ds = word(base+core['gDxeCoreDS'])
        targets = {DXE:ds, HOB:hobs, TYPES:base+core['gMemoryTypeInformation']}

        def entries(count):
            require(word(st+104) == count, 'Unexpected NumberOfTableEntries')
            array = word(st+112)
            require(POOL <= array <= LIMIT-24*count and array%8 == 0, 'Invalid ConfigurationTable')
            return {UUID(bytes_le=read(array+24*i,16)):word(array+24*i+16) for i in range(count)}

        arrive('ProcessLibraryConstructorList')
        screen('gcd')
        require((g.register(0),g.register(1)) == (handle,st), 'Wrong constructor list arguments')
        ret = g.register(30)
        statuses = []
        for name in constructors:
            arrive(name)
            if name != 'BaseDebugLibSerialPortConstructor':
                require((g.register(0),g.register(1)) == (handle,st), 'Wrong arguments to '+name)
            stop(g.register(30), name+' returned')
            statuses.append(g.register(0))
            require(statuses[-1] == 0, name+' returned an error')
        stop(ret,'constructor list returned')
        require(word(base+core['gST']) == st and word(base+core['gImageHandle']) == handle
                and word(base+core['gBS']) == word(st+96) and word(base+core['gRT']) == word(st+88)
                and word(base+core['gRT']) == int(evidence['runtimeTable'],16), 'Library cache mismatch')
        for name in ('mExtractHandlerGuidTable','mExtractDecodeHandlerTable','mExtractGetInfoHandlerTable'):
            require(POOL <= word(base+core[name]) < LIMIT, 'Missing guided handler allocation')
        require(word(st+104) == word(st+112) == 0, 'Configuration entries predate publication')
        evidence.update(constructorStatuses=dict(zip(constructors,statuses)), libraryCachesVerified=True)
        if case == 'ctor-cache':
            put(base+core['gBS'],0)
            arrive('TrialConstructorsRejected')
            return 'TrialConstructorsRejected','gcd',evidence

        installed = {}
        for guid, target in targets.items():
            arrive('CoreInstallConfigurationTable')
            screen('ctors')
            require(read(g.register(0),16) == guid.bytes_le and g.register(1) == target,
                    'Wrong upstream configuration install arguments')
            stop(g.register(30),'configuration install returned')
            require(g.register(0) == 0, 'Upstream installation failed')
            installed[guid] = target
            require(entries(len(installed)) == installed, 'Registration missing, duplicated or misbound')

        arrive('__wrap_CoreInitializeDebugImageInfoTable')
        array = word(st+112)
        addresses = {UUID(bytes_le=read(array+24*i,16)):array+24*i for i in range(3)}
        require(entries(3) == targets and read(hobs,evidence['hobBytesCompared']) ==
                read(POOL,evidence['hobBytesCompared']), 'Published HOB list differs')
        evidence.update(configurationTable=hex(array), installedByGuid={str(k):hex(v) for k,v in installed.items()},
                        entryCountsAfterInstall=[1,2,3], dxeServices=hex(ds), earlySystemTableCrc=word(st+16)&0xffffffff)
        if case == 'table-order':
            first, last = read(array,24), read(array+48,24)
            write(array,last)
            write(array+48,first)
        elif case == 'config-count':
            put(st+104,4)
        elif case == 'dxe-pointer':
            put(addresses[DXE]+16,hobs)
        elif case == 'hob-source':
            put(addresses[HOB]+16,POOL)
        elif case == 'hob-content':
            write(hobs+12,bytes([read(hobs+12,1)[0]^1]))
        elif case == 'duplicate-guid':
            write(addresses[TYPES],HOB.bytes_le)
        if case in ('config-count','dxe-pointer'):
            arrive('TrialTablesRejected')
            return 'TrialTablesRejected','ctors',evidence

        arrive('CoreGetMemorySpaceDescriptor')
        stack = g.register(1)
        require(g.register(0) == TOP-16*PAGE, 'Unexpected GCD query')
        stop(g.register(30),'published GCD descriptor returned')
        start,length,_,_,kind,owner,_ = gcd.DESCRIPTOR.unpack(read(stack,gcd.DESCRIPTOR.size))
        require(g.register(0) == 0 and (start,length,kind,owner) == (TOP-16*PAGE,16*PAGE,1,handle),
                'Published DXE services returned the wrong stack reservation')
        evidence['queryThroughPublishedServices'] = True
        if case in ('hob-source','hob-content','duplicate-guid'):
            arrive('TrialTablesRejected')
            return 'TrialTablesRejected','dxe-table',evidence
        arrive('TrialInitializeDebugPage' if after_tables else 'TrialTablesComplete')
        require(entries(3) == targets, 'Final array changed unexpectedly')
        evidence['tableLookupOrderIndependentControl'] = case == 'table-order'
        if after_tables:
            return after_tables(evidence)
        return 'TrialTablesComplete','tables',evidence

    return gcd.observe_services(g,read,write,stop,screen,core,base,case,after_gcd=check)
