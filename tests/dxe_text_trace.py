"""Check the real SystemTable->ConOut call and both scanout rasters against EDK2's font."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
from functools import lru_cache
from hashlib import sha256
import os
from pathlib import Path
import re
import struct
from uuid import UUID
import zlib

import dxe_gop_trace as gop
from dxe_dispatch_trace import observe_services
from dxe_memory_trace import observe_arena
from sec_c_qemu import GUARD
from sec_mem_qemu import require
from verify_sec_visual_data import FB_BASE, STRIDE, SURFACE_BYTES

CONTROLS = ('text-missing-interface', 'text-blt-error')
CORE_CASES = gop.CORE_CASES + CONTROLS
EXTRA_CASES = gop.EXTRA_CASES + CONTROLS
TEXT = UUID('387477c2-69c7-11d2-8e39-00a0c969723b')
FONT = Path(__file__).resolve().parents[1] / 'edk2/MdeModulePkg/Universal/Console/GraphicsConsoleDxe/LaffStd.c'
LINES = ('1 EDK2 GO 2', '3 UEFI 42 4')
# Native scanout rectangle for the marked message, before applying the optics.
# In the physical DXE_TEXT trial rotating the headset half a turn restored reading order.
X0, Y0, WIDTH, HEIGHT = 701, 544, 176, 76
WHITE, CYAN = bytes.fromhex('ffffff'), bytes.fromhex('ffff55')  # packed BGR


@lru_cache(maxsize=1)
def font():
    rows = re.findall(r'\{\s*(0x[0-9a-fA-F]+),\s*0x00,\s*\{([^}]+)\}', FONT.read_text())
    return {chr(int(code,16)): bytes(int(v,16) for v in re.findall(r'0x[0-9a-fA-F]{2}', raster))
            for code,raster in rows if 32 <= int(code,16) <= 126}


def display_ranges():
    # Each envelope includes its original SEC band. All other rows retain write watchpoints.
    return [(FB_BASE + (Y0+eye*1280)*STRIDE, FB_BASE + (Y0+WIDTH+eye*1280)*STRIDE) for eye in (0,1)]


def pixel_offset(eye,u,v):
    return GUARD + (eye*1280 + Y0 + u)*STRIDE + (X0+HEIGHT-1-v)*3


def expected_surface(data):
    glyphs = font()
    for v in range(HEIGHT):
        line = v//38
        for u in range(WIDTH):
            bits = glyphs[LINES[line][u//16]][(v%38)//2]
            color = (WHITE,CYAN)[line] if bits & (0x80 >> ((u%16)//2)) else bytes(3)
            for eye in (0,1):
                at = pixel_offset(eye,u,v)
                data[at:at+3] = color
    return data


def eye_rgb(surface, eye):
    return b''.join(surface[at:at+3][::-1] for v in range(HEIGHT) for u in range(WIDTH)
                    for at in (pixel_offset(eye,u,v),))


def png(rgb):
    def chunk(name,data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data))
    stride = WIDTH*3
    rows = b''.join(b'\0'+rgb[y:y+stride] for y in range(0,len(rgb),stride))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',WIDTH,HEIGHT,8,2,0,0,0))+
            chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))


def observe_install(g,read,row,case,address,symbols):
    require(read(g.register(5),16)==TEXT.bytes_le and g.register(7)==0,'Text Out missing from display handle')
    text = g.register(6)
    require(gop.word(read,text+8)==address+symbols['TextOutputString'],'Unexpected text interface')
    row['textInterfaceOffered']=hex(text)
    if case=='text-missing-interface':
        g.set_register(5,0)  # terminate InstallMultipleProtocolInterfaces before the text pair


def observe_console(g,read,stop,arrive,row,case,address,symbols):
    if case=='text-missing-interface':
        arrive('TrialTextErrorVisible')
        return 'TrialTextErrorVisible','text-error',row
    out = address+symbols['TextOutputString']
    blt = address+symbols['Blt']
    interface = int(row['textInterfaceOffered'],16)
    table = int(row['systemTable'],16)
    uploads = 0
    for line, string in enumerate((LINES[0]+'\r\n',LINES[1])):
        stop(out,'call through SystemTable->ConOut')
        header_size = int.from_bytes(read(table+12,4),'little')
        require(header_size==120,'Wrong system table size')
        system = bytearray(read(table,header_size))
        checksum,=struct.unpack_from('<I',system,16)
        system[16:20]=bytes(4)
        display,text=struct.unpack_from('<QQ',system,56)
        require(display==int(row['displayHandle'],16) and text==interface==g.register(0) and checksum==zlib.crc32(system),
                'Installed console and CRC disagree with system table')
        expected=(string+'\0').encode('utf-16le')
        require(read(g.register(1),len(expected))==expected,'Unexpected UTF-16 input')
        resume=g.register(30)
        for col in range(len(LINES[line])):
            for eye in (0,1):
                stop(blt,'glyph upload through GOP')
                regs=[g.register(i) for i in range(8)]
                require(regs[0]==int(row['gopInterface'],16) and tuple(regs[2:])==
                        (2,0,0,X0+38*(1-line),eye*1280+Y0+16*col,38)
                        and gop.word(read,g.register(31))==16 and gop.word(read,g.register(31)+8)==0,
                        f'Unexpected glyph BLT at line {line}, column {col}, eye {eye}: {regs[2:]}')
                uploads+=1
                if case=='text-blt-error':
                    g.set_register(2,4)  # invalid operation returns an actual GOP error without writing
                    stop(resume,'OutputString error propagation')
                    require(g.register(0)==(1<<63)|2,'GOP error lost by OutputString')
                    arrive('TrialTextErrorVisible')
                    row['glyphUploadsAttempted']=uploads
                    return 'TrialTextErrorVisible','text-error',row
                stop(g.register(30),'glyph upload returned')
                require(g.register(0)==0,'GOP rejected a valid glyph upload')
        stop(resume,'OutputString returned')
        require(g.register(0)==0,'OutputString returned an error')
    arrive('TrialTextComplete')
    data=read(FB_BASE-GUARD,SURFACE_BYTES+2*GUARD)
    left,right=(eye_rgb(data,eye) for eye in (0,1))
    require(left==right and len(set(left))>1,'Eyes differ or empty glyphs')
    # Crop in native packed-BGR row order as an independent check on the viewing rotation.
    def native(eye):
        base = GUARD + (eye*1280+Y0)*STRIDE + X0*3
        return b''.join(data[base+y*STRIDE:base+y*STRIDE+HEIGHT*3] for y in range(WIDTH))
    native_left = native(0)
    require(native_left == native(1), 'Raw scanout differs between eyes')
    row['nativeBgrSha256'] = sha256(native_left).hexdigest()
    capture=png(left)
    target=os.environ.get('DXE_TEXT_CAPTURE')
    if target and case=='valid':
        Path(target).joinpath('eye-el'+str((g.register(33)>>2)&3)+'.png').write_bytes(capture)
    row.update(textLines=list(LINES), outputStringReturns=[0,0], glyphUploads=uploads,
               consoleCrcVerified=True, eyesMatch=True, eyeRgbSha256=sha256(left).hexdigest(),
               eyePngSha256=sha256(capture).hexdigest())
    return 'TrialTextComplete','text-complete',row
