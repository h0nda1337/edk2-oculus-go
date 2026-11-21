"""Observe FV discovery, relocation, execution and a call into the loaded driver.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import struct
from uuid import UUID

import dxe_debug_trace as debug
from dxe_memory_trace import observe_arena
from sec_mem_qemu import require

FILE = UUID('9b680fce-ad6b-4f3a-b60b-f59899003443')
UTILITIES = UUID('0379be4e-d706-437d-b037-edb82fb772a4')
CONTROLS = ('false-depex', 'missing-load-path', 'wrong-file-guid', 'bad-protocol-result')
CORE_CASES = debug.CORE_CASES + CONTROLS
EXTRA_CASES = debug.EXTRA_CASES + CONTROLS


def executable_span(read, address, driver):
    # Infer text boundaries independently from the loaded PE section table.
    nt = address+int.from_bytes(read(address+60,4),'little')
    count = int.from_bytes(read(nt+6,2),'little')
    sections = nt+24+int.from_bytes(read(nt+20,2),'little')
    ranges = []
    for i in range(count):
        section = read(sections+40*i,40)
        flags, = struct.unpack_from('<I', section,36)
        if flags & (1<<29):
            vs, rva, raw = struct.unpack_from('<III',section,8)
            require(flags & (1<<31) == 0, 'Writable executable driver text')
            ranges.append((address+rva,address+rva+((max(vs,raw)+4095)&~4095)))
    require(len(ranges)==1 and ranges[0][0] <= address+driver['_ModuleEntryPoint'] < ranges[0][1],
            'Unexpected executable sections')
    return list(map(hex,ranges[0]))


def observe_services(g, read, write, stop, screen, core, base, case, constructors, driver, el, gop=None):
    if gop:
        import dxe_gop_trace as second
    def arrive(name):
        stop(base + core[name], name)

    def returned(label, status=0):
        stop(g.register(30), label)
        require(g.register(0) == status, f'{label}: x0={g.register(0):#x}')

    def word(address):
        return struct.unpack('<Q', read(address, 8))[0]

    def dispatch(evidence):
        def rejected(stage):
            arrive('TrialDispatchRejected')
            return 'TrialDispatchRejected', stage, evidence

        if case in ('valid', 'icache', 'table-order'):
            rejections = ('TrialDispatchRejected', 'TrialGopRejected') if gop else ('TrialDispatchRejected',)
            if gop and 'TextOutputString' in gop:
                rejections += ('TextRejected',)
            if gop and 'application' in gop:
                rejections += ('TrialAppRejected',)
            for name in rejections:
                require(g.command(f'Z1,{base+core[name]:x},4') == 'OK', 'Cannot monitor ' + name)
        arrive('CoreInitializeEventServices')
        screen('debug-image')
        returned('event services')
        for n in ('FwVolBlockDriverInit', 'FwVolDriverInit', 'InitializeSectionExtraction'):
            arrive(n)
            returned(n + ' return')
        arrive('CoreInitializeDispatcher')
        arrive('CoreAddToDriverList')
        fv_handle = g.register(1)
        require(g.register(3) == 7 and read(g.register(2),16) == FILE.bytes_le, 'Unexpected FFS driver')
        evidence.update(eventsInitialized=True, driverFile=str(FILE), fvHandle=hex(fv_handle))
        arrive('FvReadFileSection')
        dep_out, size_out = g.register(4), g.register(5)
        require(g.register(2) == 0x13 and read(g.register(1),16) == FILE.bytes_le, 'Unexpected DEPEX section')
        returned('read DEPEX from FV')
        dep = word(dep_out)
        lo, hi = (int(v,16) for v in evidence['freeWindow'])
        require(lo <= dep <= hi-2 and word(size_out) == 2 and read(dep,2) == bytes([6,8]),
                'Driver DEPEX was not a TRUE/END copy from the FV')
        if case == 'false-depex':
            write(dep, bytes([7]))
        if gop:
            second.read_dependency(g, read, write, arrive, returned, evidence, case)
        arrive('__wrap_CoreDispatcher')
        arrive('CoreDispatcher')
        screen('dispatch')
        arrive('CoreIsSchedulable')
        runnable = case != 'false-depex'
        returned('evaluate FFS dependency',int(runnable))
        evidence['dependencySatisfied'] = runnable
        if gop:
            arrive('CoreIsSchedulable')
            returned('GOP waits for Device Path Utilities', 0)
            evidence['gopWaitedForUtilities'] = True
        if not runnable:
            for n in ('CoreLoadImage','__wrap_CoreStartImage'):
                require(g.command(f'Z1,{base+core[n]:x},4') == 'OK', 'Cannot monitor unexpected load')
            return rejected('dispatch')
        arrive('CoreLoadImage')
        out = g.register(5)
        require(g.register(1) == int(evidence['imageHandle'],16) and g.register(2) and
                g.register(3) == g.register(4) == 0, 'Image did not use the FV device path')
        if case == 'missing-load-path':
            g.set_register(2,0)
            returned('missing FV path', (1<<63)|2)
            evidence['loadStatus'] = 'EFI_INVALID_PARAMETER'
            return rejected('dispatch')
        returned('loader return')
        handle = word(out)
        arrive('__wrap_CoreStartImage')
        require(handle != 0 and g.register(0) == handle, 'Wrong StartImage handle')
        arrive('CoreHandleProtocol')
        dest = g.register(2)
        returned('loaded image lookup')
        image = word(dest)
        header = int(evidence['debugImage']['header'],16)
        flags, entries, array = struct.unpack('<IIQ', read(header,16))
        require((flags, entries) == (2,2), 'New driver missing from debugger table')
        records = [struct.unpack('<I4xQQ', read(word(array+8*i),24)) for i in range(entries)]
        require((1,image,handle) in records, 'Debugger record does not match Loaded Image')
        path = word(image+32)
        address, size = struct.unpack('<QQ',read(image+64,16))
        require(word(image+24) == fv_handle and read(path,20) == bytes.fromhex('04061400')+FILE.bytes_le,
                'Loaded image does not belong to discovered FV file')
        low, high = map(lambda v:int(v,16), evidence['freeWindow'])
        require(low <= address < address+size <= high and read(address,2) == b'MZ', 'Image outside DXE arena')
        evidence.update(loadStatus='EFI_SUCCESS',driverImageBase=hex(address),driverImageBytes=size,
                        driverHandle=hex(handle))
        if case == 'wrong-file-guid':
            write(path+4,bytes(16))
            return rejected('dispatch')
        evidence['driverText'] = executable_span(read,address,driver)
        arrive('CoreStartImage')
        screen('start-driver')
        resume = g.register(30)
        stop(address+driver['_ModuleEntryPoint'],'driver PE entry')
        stop(address+driver['DevicePathEntryPoint'],'DevicePathDxe entry')
        require(g.register(0) == handle and g.register(1) == int(evidence['systemTable'],16),
                'Driver received wrong image handle or system table')
        arrive('CoreInstallMultipleProtocolInterfaces')
        require(read(g.register(1),16) == UTILITIES.bytes_le, 'Driver installed unexpected interface')
        interface = g.register(2)
        require(word(interface) == address+driver['GetDevicePathSize'], 'Interface points outside expected driver code')
        stop(resume,'StartImage returned')
        require(g.register(0)==0, 'Driver failed to start')
        # CoreDispatcher signals its dispatch group before it returns.
        stop(address+driver['GetDevicePathSize'],'call through published interface')
        require(read(g.register(0),4) == bytes.fromhex('7fff0400'), 'Wrong test path')
        returned('end node size',4)
        evidence.update(startStatus='EFI_SUCCESS',protocolGuid=str(UTILITIES),
                        protocolInterface=hex(interface),getDevicePathSize=4)
        if case == 'bad-protocol-result':
            g.set_register(0,3)
            return rejected('start-driver')
        if gop:
            return second.observe_driver(g, read, write, stop, screen, arrive, returned, evidence, case, gop)
        arrive('TrialDispatchComplete')
        return 'TrialDispatchComplete','protocol',evidence

    return debug.observe_services(g,read,write,stop,screen,core,base,case,constructors,after_debug=dispatch)
