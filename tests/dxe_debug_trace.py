"""Walk the UEFI debugger structures from the aligned page in the packaged guest.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import struct
import zlib
from uuid import UUID

import dxe_tables_trace as tables
from dxe_memory_trace import observe_arena
from sec_dxe_static import LIMIT, POOL
from sec_mem_qemu import BASE, SIZE, require

PAGE = 4096
LOCATOR = 0x80400000
DEBUG_GUID = UUID('49152e77-1ada-4764-b7a2-7afefed95e8b')
CONTROLS = ('locator-dirty', 'locator-readback', 'oversize', 'locator-efi-type',
            'locator-crc', 'debug-record', 'debug-guid')
CORE_CASES = tables.CORE_CASES + CONTROLS
EXTRA_CASES = tables.EXTRA_CASES + CONTROLS


def observe_services(g, read, write, stop, screen, core, base, case, constructors, after_debug=None):
    def arrive(name):
        stop(base + core[name], name)

    def word(addr):
        return struct.unpack('<Q', read(addr, 8))[0]

    def returned(label, status=0):
        stop(g.register(30), label)
        require(g.register(0) == status, f'{label}: status {g.register(0):#x}, expected {status:#x}')

    def debug(ev):
        st = int(ev['systemTable'], 16)
        handle = int(ev['imageHandle'], 16)
        image = int(ev['loadedImageProtocol'], 16)
        screen('tables')
        require(read(LOCATOR-PAGE, 3*PAGE) == b'\xff'*(3*PAGE), 'Page or guard changed before qualification')
        ev['debugPageTouched'] = True

        def rejected(stage):
            arrive('TrialDebugRejected')
            return 'TrialDebugRejected', stage, ev

        if case == 'locator-dirty':
            # Single dirty byte at the far end detects a partial pristine-page scan.
            corrupt = b'\xff'*(PAGE-1) + b'\x01'
            write(LOCATOR+PAGE-1, corrupt[-1:])
            result = rejected('tables')
            require(read(LOCATOR, PAGE) == corrupt, 'Guest wrote before checking the entire page')
            return result
        mask = 0x2e8163d4c7095bfa
        for pattern in (mask, mask ^ ((1 << 64)-1)):
            arrive('TrialCheckDebugPage')
            require(g.register(0) == pattern and read(LOCATOR, PAGE) ==
                    b''.join(struct.pack('<Q', a ^ pattern) for a in range(LOCATOR, LOCATOR+PAGE, 8)),
                    'Aligned page did not contain the address-dependent pattern')
            if case == 'locator-readback' and pattern != mask:
                write(LOCATOR+PAGE-1, bytes([read(LOCATOR+PAGE-1,1)[0] ^ 1]))
                return rejected('tables')
            require(g.command('s').startswith(('S','T')), 'Could not resume page sweep')
        arrive('CoreAddMemorySpace')
        require(tuple(g.register(i) for i in range(4)) == (2,LOCATOR,PAGE,1), 'Unexpected GCD admission')
        returned('admit debugger page')
        ev['qualifiedBytes'] = PAGE
        arrive('CoreAllocatePages')
        out = g.register(3)
        require(tuple(g.register(i) for i in range(3)) == (2,4,1) and word(out) == LOCATOR,
                'Allocation was not for the one exact BootServicesData page')
        if case == 'oversize':
            # Repeat the original AllocateMaxAddress request against the real allocator.
            g.set_register(0,1)
            g.set_register(2,1025)
            write(out, b'\xff'*8)
            returned('original-sized request', (1 << 63) | 9)
            ev['oversizeRequest'] = {'pages':1025, 'status':'EFI_OUT_OF_RESOURCES'}
            return rejected('tables')
        returned('allocate single debugger page')
        require(word(out) == LOCATOR, 'Wrong AllocateAddress result')
        ev['allocation'] = {'base':hex(LOCATOR), 'pages':1, 'type':'EfiBootServicesData'}
        arrive('CoreGetMemorySpaceDescriptor')
        ptr = g.register(1)
        require(g.register(0) == LOCATOR, 'Wrong GCD resource')
        returned('read debugger GCD descriptor')
        start,length,cap,_,kind,owner,device = tables.gcd.DESCRIPTOR.unpack(read(ptr,tables.gcd.DESCRIPTOR.size))
        require((start,length,kind,owner,device) == (LOCATOR,PAGE,2,handle,0) and cap & 1, 'GCD ownership mismatch')
        arrive('CoreGetMemoryMap')
        count, buf, stride = (g.register(i) for i in (0,1,3))
        returned('read debugger EFI map')
        n, step = word(count), word(stride)
        require(40 <= step <= n <= 2048 and n % step == 0, 'Bad EFI map')
        matches = [buf+i for i in range(0,n,step) if word(buf+i+8) == LOCATOR]
        require(len(matches) == 1 and read(matches[0],4) == struct.pack('<I',4) and word(matches[0]+24) == 1,
                'Debugger page is not exactly one allocated EFI descriptor')
        ev['gcdAndEfiOwnershipVerified'] = True
        if case == 'locator-efi-type':
            write(matches[0], struct.pack('<I',7))
            return rejected('tables')

        header = base+core['mDebugInfoTableHeader']
        arrive('CoreInstallConfigurationTable')
        require(read(g.register(0),16) == DEBUG_GUID.bytes_le and g.register(1) == header and
                read(header,16) == bytes(16), 'Initial debug header is not empty or GUID differs')
        returned('publish debug header')
        arrive('CoreNewDebugImageInfoEntry')
        screen('debug-locator')
        require(tuple(g.register(i) for i in range(3)) == (1,image,handle), 'Wrong upstream debug record arguments')
        stop(g.register(30), 'core debug image registered')
        # Inspect from the firmware image boundary as an external debugger would.
        alignment = 4 << 20
        first = (BASE + alignment - 1) & -alignment
        candidates = [addr for addr in reversed(range(first, BASE+SIZE, alignment))
                      if read(addr, 8) == b'IBI SYST']
        require(candidates == [LOCATOR], 'Aligned scan of the delivered FD failed')
        locator = read(candidates[0],24)
        signature, system_base, crc = struct.unpack('<8sQI4x', locator)
        checked_crc = zlib.crc32(locator[:16] + bytes(4) + locator[20:])
        require(signature == b'IBI SYST' and system_base == st and crc == checked_crc and
                read(LOCATOR+20,PAGE-20) == bytes(PAGE-20), 'Invalid debugger locator or page tail')
        arr = word(system_base+112)
        require(word(system_base+104) == 4 and POOL <= arr <= LIMIT-4*24, 'Invalid EFI configuration array')
        found = {UUID(bytes_le=read(arr+i*24,16)):word(arr+i*24+16) for i in range(4)}
        expected = {UUID(k):int(v,16) for k,v in ev['installedByGuid'].items()}
        require(found == {**expected, DEBUG_GUID:header}, 'Wrong fourth GUID or displaced existing entry')
        flags, entries, table = struct.unpack('<IIQ', read(found[DEBUG_GUID],16))
        require((flags,entries) == (2,1) and POOL <= table <= LIMIT-PAGE, 'Wrong image table header')
        record = word(table)
        require(POOL <= record <= LIMIT-24 and read(table+8,PAGE-8) == bytes(PAGE-8), 'Invalid record array')
        kind, protocol, registered_handle = struct.unpack('<I4xQQ', read(record,24))
        require((kind,protocol,registered_handle) == (1,image,handle) and
                word(protocol+16) == st and word(protocol+64) == base, 'Record does not identify DXE Core')
        ev['debugLocator'] = {'address':hex(LOCATOR), 'systemTable':hex(st), 'crc32':f'{crc:08x}'}
        ev['debugImage'] = {'guid':str(DEBUG_GUID),'header':hex(header),'table':hex(table),'record':hex(record),
                            'entries':entries,'updateStatus':flags,'loadedImage':hex(protocol),
                            'handle':hex(registered_handle),'imageBase':hex(base)}
        if case == 'locator-crc':
            write(LOCATOR+16,struct.pack('<I',crc ^ 1))
        elif case == 'debug-record':
            write(record+16,bytes(8))
        elif case == 'debug-guid':
            index = next(i for i in range(4) if read(arr+24*i,16) == DEBUG_GUID.bytes_le)
            write(arr+24*index, bytes(16))
        if case in ('locator-crc','debug-record','debug-guid'):
            return rejected('debug-locator')
        if after_debug:
            return after_debug(ev)
        arrive('TrialDebugComplete')
        return 'TrialDebugComplete','debug-image',ev

    return tables.observe_services(g, read, write, stop, screen, core, base, case, constructors, after_tables=debug)
