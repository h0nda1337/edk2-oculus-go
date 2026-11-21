"""Observe one FV application from LoadImage to its console call and automatic unload."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from hashlib import sha256
import os
from pathlib import Path
import struct
from uuid import UUID

import dxe_text_trace as text
from dxe_dispatch_trace import executable_span
from dxe_gop_trace import word
from dxe_memory_trace import observe_arena
from dxe_dispatch_trace import observe_services
from sec_dxe_static import POOL
from sec_mmu_qemu import TABLE, PAGE
from sec_mem_qemu import require
from sec_c_qemu import GUARD
from verify_sec_visual_data import FB_BASE, SURFACE_BYTES

CONTROLS = ('app-missing-file', 'app-output-error')
CORE_CASES = text.CORE_CASES + CONTROLS
EXTRA_CASES = text.EXTRA_CASES + CONTROLS
GUID = UUID('a63728d5-057a-43bb-88f7-89aa3e5856e9')
LINE = '5 APP EFI 6'
INVALID_PARAMETER = (1 << 63) | 2
NOT_FOUND = (1 << 63) | 14


def expected_surface(surface):
    return text.expected_surface(surface, (text.LINES[0], LINE), (text.WHITE, bytes.fromhex('55ff55')))


def file_node(read, path):
    for _ in range(8):
        kind, subtype, length = struct.unpack('<BBH', read(path, 4))
        if (kind, subtype) == (4, 6):
            require(length == 20 and read(path+4,16) == GUID.bytes_le and
                    read(path+20,4) == bytes.fromhex('7fff0400'), 'Wrong FV application path')
            return path
        require(kind != 0x7f and 4 <= length <= 256, 'Malformed FV device path')
        path += length
    raise ValueError('Missing FV file node')


def observe_application(g, read, write, stop, arrive, returned, row, case, gop_base, driver):
    symbols, pe_hash, pe_bytes = driver['application']
    def u64(p):
        return word(read,p)

    st = int(row['systemTable'],16)
    bs = u64(st+96)
    arrive('CoreLoadImage')
    path, handle_out = g.register(2), g.register(5)
    require(g.register(32) == u64(bs+200) and g.register(0) == 0 and
            g.register(1) == int(row['imageHandle'],16) and path and handle_out and
            g.register(3) == g.register(4) == 0, 'LoadImage did not use the FV path')
    node = file_node(read,path)
    loaded_return = g.register(30)
    if case == 'app-missing-file':
        write(node+4,bytes(16))
        stop(loaded_return,'missing application load return')
        require(g.register(0) == NOT_FOUND and u64(handle_out) == 0, 'Missing application was loaded')
        arrive('TrialAppRejected')
        row['appLoadStatus'] = 'EFI_NOT_FOUND'
        return 'TrialAppRejected','text-complete',row

    arrive('FvReadFileSection')
    require(read(g.register(1),16) == GUID.bytes_le and g.register(2) == 0x10 and g.register(3) == 0,
            'Expected the PE32 section of the application file')
    buffer, size = g.register(4), g.register(5)
    returned('FV application section read')
    require(u64(size) == pe_bytes and sha256(read(u64(buffer),pe_bytes)).hexdigest() == pe_hash,
            'FV section bytes differ from the compiled application')
    stop(loaded_return,'application LoadImage returned')
    handle = u64(handle_out)
    require(g.register(0) == 0 and handle and handle not in
            [int(row[k],16) for k in ('imageHandle','driverHandle','gopHandle')], 'Invalid application handle')
    arrive('CoreHandleProtocol')
    ptr = g.register(2)
    returned('application Loaded Image')
    image = u64(ptr)
    address, size = struct.unpack('<QQ',read(image+64,16))
    lo,hi = (int(n,16) for n in row['freeWindow'])
    require(lo <= address < address+size <= hi and u64(image+8) == int(row['imageHandle'],16) and
            u64(image+16) == st and u64(image+24) == int(row['fvHandle'],16) and
            struct.unpack('<II',read(image+80,8)) == (1,2), 'Wrong application Loaded Image')
    file_node(read,u64(image+32))
    span = executable_span(read,address,symbols)
    start,end = (int(x,16) for x in span)
    enter = address+symbols['_ModuleEntryPoint']
    nt = address+int.from_bytes(read(address+60,4),'little')
    require(enter == address+int.from_bytes(read(nt+40,4),'little'), 'PE entry RVA mismatch')
    def check_permissions(execute):
        el = (g.register(33)>>2)&3
        attrs = (0x787 | ((1<<54) if el==1 else 0)) if execute else (0x707 | (1<<54) | ((1<<53) if el==1 else 0))
        for page in range(start,end,PAGE):
            require(u64(TABLE + 7*PAGE + 8*((page-POOL)//PAGE)) == page | attrs, 'Application page attributes differ')
    def check_debug(expected, present):
        hdr = int(row['debugImage']['header'],16)
        _, count, ptr = struct.unpack('<IIQ',read(hdr,16))
        require(count == expected, 'Unexpected debugger image count')
        records = [struct.unpack('<I4xQQ',read(u64(ptr+i*8),24)) for i in range(count)]
        require(((1,image,handle) in records) == present, 'Application debug record mismatch')

    start_service = u64(bs+208)
    stop(start_service,'call through BootServices->StartImage')
    require(g.register(0) == handle and g.register(1) == g.register(2) == 0, 'Wrong StartImage arguments')
    started_return = g.register(30)
    check_permissions(True)
    check_debug(4,True)
    arrive('CoreStartImage')
    stop(enter,'application PE entry')
    require(g.register(0) == handle and g.register(1) == st,'Wrong PE entry arguments')
    stop(address+symbols['ConsoleProbeMain'],'ConsoleProbeMain')
    require(g.register(0) == handle and g.register(1) == st,'Wrong application arguments')
    conout = u64(st+64)
    stop(gop_base+driver['TextOutputString'],'application OutputString')
    caller = g.register(30)
    utf = (LINE+'\0').encode('utf-16le')
    require(start <= caller < end and g.register(0) == conout == int(row['textInterfaceOffered'],16)
            and read(g.register(1),len(utf)) == utf,'OutputString caller, console or UTF-16 mismatch')
    result = INVALID_PARAMETER if case == 'app-output-error' else 0
    if result:
        stop(gop_base+driver['Blt'],'first application glyph')
        g.set_register(2,4)
    stop(caller,'application OutputString returned')
    require(g.register(0) == result, 'Output status was lost')
    arrive('CoreExit')
    require(g.register(0) == handle and g.register(1) == result, 'Wrong application exit status')
    arrive('__wrap_UnprotectUefiImage')
    require(g.register(0) == image,'Wrong image cleanup')
    arrive('CoreFreePages')
    require(g.register(0) <= address and g.register(0)+g.register(1)*PAGE >= address+size,'Image pages not released')
    check_permissions(False)
    returned('release application image pages')
    stop(started_return,'application StartImage returned')
    require(g.register(0) == result,'Wrong StartImage result')
    check_debug(3,False)
    row.update(appLoadStatus='EFI_SUCCESS',appHandle=hex(handle),appBase=hex(address),appBytes=size,
               appText=span,appEntry=hex(enter),appOutputCaller=hex(caller),appFvPeSha256=pe_hash,
               appOutputStatus=result,appExitStatus=result,appStartStatus=result,appRemovedFromDebugTable=True,
               appCodeRestoredToRwXn=True)
    if result:
        arrive('TrialAppRejected')
        return 'TrialAppRejected','text-complete',row
    arrive('TrialAppComplete')
    surface = read(FB_BASE-GUARD,SURFACE_BYTES+2*GUARD)
    left,right = (text.eye_rgb(surface,i) for i in (0,1))
    require(left == right,'Application text differs between eyes')
    capture = text.png(left)
    target = os.environ.get('DXE_TEXT_CAPTURE')
    if target and case == 'valid':
        el = (g.register(33)>>2)&3
        Path(target,f'eye-el{el}.png').write_bytes(capture)
    row.update(appLine=LINE,appEyesMatch=True,appEyeRgbSha256=sha256(left).hexdigest(),
               appEyePngSha256=sha256(capture).hexdigest())
    return 'TrialAppComplete','app-complete',row
