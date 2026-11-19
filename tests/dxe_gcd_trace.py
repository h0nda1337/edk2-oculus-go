"""Observe upstream image registration, HOB migration and the PI GCD map in QEMU.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import struct
from uuid import UUID

import dxe_memory_trace as memory
from dxe_memory_trace import observe_arena
from sec_dxe_static import CORE, POOL, LIMIT
from sec_mmu_qemu import TOP, PAGE
from sec_mem_qemu import require

CONTROLS = ('image-metadata', 'hob-copy', 'gcd-owner', 'stack-type', 'hob-page-type')
CORE_CASES = memory.CORE_CASES + CONTROLS
EXTRA_CASES = memory.EXTRA_CASES + CONTROLS
LOADED_IMAGE = UUID('5b1b31a1-9562-11d2-8e3f-00a0c969723b')
DESCRIPTOR = struct.Struct('<QQQQI4xQQ')


def observe_services(g, read, write, stop, screen, core, base, case):
    def word(address):
        return struct.unpack('<Q', read(address, 8))[0]

    def arrive(name):
        stop(base + core[name], name)

    def check_gcd(evidence):
        arrive('CoreInitializeImageServices')
        require(g.register(0) == POOL, 'Image initializer received the wrong handoff')
        screen('memory')
        ret = g.register(30)
        arrive('CoreInstallProtocolInterface')
        require(read(g.register(1), 16) == LOADED_IMAGE.bytes_le, 'Wrong installed protocol')
        interface = g.register(3)
        stop(ret, 'image services return')
        require(g.register(0) == 0, 'Image services initialization failed')
        arrive('__wrap_CoreInitializeGcdServices')
        pointer, low, length = (g.register(i) for i in range(3))
        require(word(pointer) == POOL and evidence['freeWindow'] == [hex(low), hex(low+length)],
                'Unexpected GCD handoff')
        original = read(POOL, word(POOL+40) - POOL)
        handle = word(base+core['gDxeCoreImageHandle'])
        file_name = word(base+core['gDxeCoreFileName'])
        require(POOL <= file_name <= POOL+len(original)-16 and read(file_name,16) == CORE.bytes_le,
                'Unexpected source of DXE Core file GUID')
        image_size = word(interface+72)
        require(low <= handle < low+length and interface == word(base+core['gDxeCoreLoadedImage'])
                and word(interface+16) == int(evidence['systemTable'],16)
                and word(interface+64) == base and image_size == struct.unpack('<I',read(
                    base+struct.unpack('<I',read(base+60,4))[0]+24+56,4))[0],
                'Loaded image information differs from the relocated PE or live system table')
        arrive('CoreHandleProtocol')
        require(g.register(0) == handle and read(g.register(1),16) == LOADED_IMAGE.bytes_le,
                'Probe did not query the core handle')
        result = g.register(2)
        stop(g.register(30), 'HandleProtocol returned')
        require(g.register(0) == 0 and word(result) == interface, 'Loaded image lookup failed')
        evidence.update(imageInitSuccess=True, loadedImageProtocol=hex(interface), imageHandle=hex(handle),
                        loadedImageBytes=image_size)
        if case == 'image-metadata':
            write(interface+72, struct.pack('<Q',image_size+1))
            arrive('TrialGcdRejected')
            return 'TrialGcdRejected','memory',evidence

        arrive('CoreInitializeGcdServices')
        screen('image')
        require((g.register(0),g.register(1),g.register(2)) == (pointer, low, length),
                'Original GCD initializer arguments changed')
        stop(g.register(30), 'GCD initializer returned')
        moved = word(pointer)
        require(g.register(0) == 0 and low <= moved <= low+length-len(original)
                and word(base+core['gHobList']) == moved and read(moved,len(original)) == original,
                'GCD did not migrate the entire HOB list')
        evidence.update(gcdInitSuccess=True, relocatedHobs=hex(moved), hobBytesCompared=len(original),
                        coreFileGuidPointsIntoOriginalHobs=(word(base+core['gDxeCoreFileName']) == file_name))
        if case == 'hob-copy':
            write(moved+12, bytes([original[12]^1]))
            arrive('TrialGcdRejected')
            return 'TrialGcdRejected','image',evidence

        arrive('CoreGetMemoryMap')
        size_p, buf, _, stride_p, _ = (g.register(i) for i in range(5))
        stop(g.register(30), 'EFI memory map after HOB migration')
        size, stride = word(size_p), word(stride_p)
        require(g.register(0) == 0 and 40 <= stride <= size <= 2048 and size%stride == 0,
                'Invalid post-migration EFI memory map')
        hob_types = [(buf+off, struct.unpack('<I',read(buf+off,4))[0]) for off in range(0,size,stride)
                     if word(buf+off+8) == POOL and word(buf+off+24) >= 1]
        require(len(hob_types) == 1 and hob_types[0][1] == 4 and read(POOL,len(original)) == original
                and evidence['coreFileGuidPointsIntoOriginalHobs'], 'Original HOB page is unprotected')
        evidence['originalHobPageType'] = 'EfiBootServicesData'
        if case == 'hob-page-type':
            write(hob_types[0][0], struct.pack('<I',7))
            arrive('TrialGcdRejected')
            return 'TrialGcdRejected','image',evidence

        arrive('TrialCheckGcdMap')
        screen('relocated-hobs')
        address, count = g.register(0), g.register(1)
        require(3 <= count <= 64 and POOL <= address <= LIMIT-count*DESCRIPTOR.size,
                'Invalid GCD map buffer')
        ranges = []
        cursor = 0
        ram = 0
        stack_descriptor = None
        for i in range(count):
            p = address + i*DESCRIPTOR.size
            start,size,cap,attrs,kind,owner,device = DESCRIPTOR.unpack(read(p,DESCRIPTOR.size))
            require(start == cursor and size > 0 and device == 0, 'Gap, overlap or device owner')
            cursor += size
            if POOL <= start < LIMIT:
                require(cursor <= LIMIT and kind == 2 and owner == handle and cap & 1,
                        'Unexpected system memory in GCD')
                ram += size
                system_descriptor = p
            elif (start, cursor) == (TOP-16*PAGE, TOP):
                require(kind == 1 and owner == handle, 'Active stack lacks its reserved GCD resource')
                stack_descriptor = p
            else:
                require((cursor <= POOL or start >= LIMIT) and kind == 0 and owner == 0,
                        f'Unexpected GCD descriptor {start:#x}..{cursor:#x} type={kind} owner={owner:#x} cap={cap:#x}')
            ranges.append([hex(start),hex(cursor),kind])
        require(stack_descriptor is not None and cursor == 1<<32 and ram == LIMIT-POOL, 'Incomplete GCD map')
        evidence.update(gcdRanges=ranges, systemMemoryBytes=ram, reservedStackBytes=16*PAGE)
        if case in ('gcd-owner','stack-type'):
            if case == 'gcd-owner':
                write(system_descriptor+40, bytes(8))
            else:
                write(stack_descriptor+32, bytes(4))
            arrive('TrialGcdRejected')
            return 'TrialGcdRejected','relocated-hobs',evidence
        arrive('CoreFreePool')
        require(g.register(0) == address, 'Wrong GCD map released')
        stop(g.register(30), 'GCD map released')
        require(g.register(0) == 0, 'Failed to free GCD map')
        arrive('TrialGcdComplete')
        return 'TrialGcdComplete','gcd',{**evidence,'gcdMapFreed':True}

    return memory.observe_services(g, read, write, stop, screen, core, base, case, check_gcd)
