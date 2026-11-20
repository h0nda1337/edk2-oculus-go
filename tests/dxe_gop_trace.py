"""Check that a second FV image publishes the GOP which draws both BGR bands."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import struct
from uuid import UUID

import dxe_dispatch_trace as dispatch
from dxe_dispatch_trace import observe_services
from dxe_memory_trace import observe_arena
from sec_mem_qemu import require
from verify_sec_visual_data import FB_BASE, STRIDE, BAND_ROWS, BAND_HEIGHT

FILE = UUID('8cd15dc8-f091-4917-b779-342c1e0aa2de')
GOP = UUID('9042a9de-23dc-4a38-96fb-7aded080516a')
PATH = UUID('09576e91-6d3f-11d2-8e39-00a0c969723b')
CONTROLS = ('gop-depex','gop-file-guid','gop-readback','gop-fill-status')
CORE_CASES = dispatch.CORE_CASES + CONTROLS
EXTRA_CASES = dispatch.EXTRA_CASES + CONTROLS


def word(read, address):
    return int.from_bytes(read(address,8),'little')


def read_dependency(g, read, write, arrive, returned, evidence, case):
    arrive('CoreAddToDriverList')
    require(g.register(1) == int(evidence['fvHandle'],16) and g.register(3) == 7 and
            read(g.register(2),16) == FILE.bytes_le, 'GOP not discovered in the trial FV')
    arrive('FvReadFileSection')
    dest, length = g.register(4),g.register(5)
    require(g.register(2)==0x13 and read(g.register(1),16)==FILE.bytes_le, 'Unexpected second DEPEX read')
    returned('read second DEPEX from FV')
    dep = word(read,dest)
    low,high = (int(v,16) for v in evidence['freeWindow'])
    require(low <= dep <= high-18 and word(read,length)==18 and
            read(dep,18)==b'\x02'+dispatch.UTILITIES.bytes_le+b'\x08', 'Wrong protocol dependency')
    if case == 'gop-depex':
        write(dep+1,bytes(16))


def observe_driver(g, read, write, stop, screen, arrive, returned, evidence, case, driver):
    arrive('CoreIsSchedulable')
    screen('protocol')
    runnable = case != 'gop-depex'
    returned('re-evaluate GOP after first driver',int(runnable))
    evidence['gopDependencySatisfied'] = runnable
    if not runnable:
        arrive('TrialDispatchRejected')
        return 'TrialDispatchRejected','protocol',evidence
    arrive('CoreLoadImage')
    out = g.register(5)
    require(g.register(1)==int(evidence['imageHandle'],16) and g.register(2) and
            g.register(3)==g.register(4)==0,'Second driver did not use FV path')
    returned('second image loaded')
    handle = word(read,out)
    arrive('__wrap_CoreStartImage')
    require(handle and handle!=int(evidence['driverHandle'],16) and g.register(0)==handle,'Wrong second handle')
    arrive('CoreHandleProtocol')
    dest = g.register(2)
    returned('second Loaded Image')
    image = word(read,dest)
    path = word(read,image+32)
    require(read(path,20)==bytes.fromhex('04061400')+FILE.bytes_le and word(read,image+24)==int(evidence['fvHandle'],16),
            'Second image file path differs')
    address,size = struct.unpack('<QQ',read(image+64,16))
    lo,hi=map(lambda v:int(v,16),evidence['freeWindow'])
    first = int(evidence['driverImageBase'],16)
    require(lo<=address<address+size<=hi and (address+size<=first or first+evidence['driverImageBytes']<=address),
            'Driver images overlap or escape the arena')
    flags,count,table = struct.unpack('<IIQ',read(int(evidence['debugImage']['header'],16),16))
    require((flags,count)==(2,3) and (1,image,handle) in
            [struct.unpack('<I4xQQ',read(word(read,table+8*i),24)) for i in range(count)],
            'Missing GOP in debug image table')
    evidence.update(gopImageBase=hex(address),gopImageBytes=size,gopHandle=hex(handle))
    if case == 'gop-file-guid':
        write(path+4,bytes(16))
        arrive('TrialDispatchRejected')
        return 'TrialDispatchRejected','protocol',evidence
    evidence['gopText'] = dispatch.executable_span(read,address,driver)
    arrive('CoreStartImage')
    resume = g.register(30)
    stop(address+driver['_ModuleEntryPoint'],'second PE entry')
    stop(address+driver['InheritedGopDxeEntry'],'GOP driver entry')
    require(g.register(0)==handle and g.register(1)==int(evidence['systemTable'],16),'Wrong GOP entry arguments')
    arrive('CoreInstallMultipleProtocolInterfaces')
    require(read(g.register(1),16)==GOP.bytes_le and read(g.register(3),16)==PATH.bytes_le and
            read(g.register(4),24)==bytes.fromhex('01041400')+FILE.bytes_le+bytes.fromhex('7fff0400'),
            'GOP and its vendor device path not installed together')
    interface = g.register(2)
    query,_,blt,_ = struct.unpack('<4Q',read(interface,32))
    require(query==address+driver['QueryMode'] and blt==address+driver['Blt'],'GOP methods are not from second image')
    stop(resume,'GOP StartImage returned')
    require(g.register(0)==0,'GOP failed to start')
    stop(query,'GOP QueryMode')
    require(g.register(0)==interface and g.register(1)==0,'QueryMode on wrong GOP or mode')
    result = g.register(3)
    returned('QueryMode returned')
    require(struct.unpack('<9I',read(word(read,result),36))==(0,1440,2560,3,0,0,0,0,1440),'Wrong GOP mode')
    evidence.update(gopStarted=True,gopInterface=hex(interface),bltCalls=0)
    def blit(operation, x, y, width, height):
        stop(blt,'driver GOP.Blt')
        regs=[g.register(i) for i in range(8)]
        sp=g.register(31)
        require(regs[0]==interface and regs[2]==operation and word(read,sp)==height and word(read,sp+8)==0,
                'Unexpected BLT receiver, operation, height or pitch')
        expected=(0,0,x,y,width) if operation==0 else (x,y,0,0,width)
        require(tuple(regs[3:])==expected, 'Wrong BLT rectangle')
        evidence['bltCalls']+=1
        return regs[1]

    blue,red,black,yellow=[bytes.fromhex(s) for s in ('ff0000','0000ff','000000','00ffff')]
    fills = [(i*288,row,pixel) for row in BAND_ROWS for i,pixel in enumerate((blue,red,black,red,blue))]
    fills.extend((2*288,row,yellow) for row in BAND_ROWS)
    for x,y,color in fills:
        ptr=blit(0,x,y,288,BAND_HEIGHT)
        require(read(ptr,4)==color+b'\0','Wrong UEFI BLT pixel')
        returned('fill returned')
        require(read(FB_BASE+y*STRIDE+x*3,864)==color*288,'Packed RAM differs from requested color')
        if case=='gop-fill-status' and y==BAND_ROWS[-1] and color==yellow:
            g.set_register(0,(1<<63)|7)
            arrive('TrialGopErrorVisible')
            return 'TrialGopErrorVisible','gop-error',evidence
        sx,sy=(x,y) if color==yellow else (x+287,y+BAND_HEIGHT-1)
        ptr=blit(1,sx,sy,1,1)
        returned('readback returned')
        require(read(ptr,4)==color+b'\0','BGR-to-BLT readback differs')
        if case=='gop-readback' and color==red:
            write(ptr,blue+b'\0')
            arrive('TrialGopErrorVisible')
            return 'TrialGopErrorVisible','gop-error',evidence
    arrive('TrialGopComplete')
    screen('gop-blt')
    evidence['rawBgrRow'] = [read(FB_BASE+BAND_ROWS[0]*STRIDE+3*288*i,3).hex() for i in range(5)]
    return 'TrialGopComplete','gop-blt',evidence
