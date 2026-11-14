"""Recheck display data against exact preserved unit captures, without hardware.
No bootloader implementation is copied, linked, invoked or uploaded.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ABOOT_SHA = '6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74'
DTS_SHA = '48d04e4cda8e1d4b5b67a00ffca47150e642332c3bd15a443f7d88cc1b8222cc'
FB_BASE = 0x83401000
STRIDE = 4320
BAND_ROWS = (640, 1920)
BAND_HEIGHT = 32
BAND_BYTES = STRIDE * BAND_HEIGHT
SURFACE_BYTES = 1440 * 2560 * 3


def band_ranges():
    return tuple((FB_BASE + row * STRIDE, FB_BASE + row * STRIDE + BAND_BYTES)
                 for row in BAND_ROWS)


def expected_band():
    row = (b'\xff\xff\xff' * 360 + b'\x00\x00\x00' * 360
           + b'\x00\xff\x00' * 360 + b'\xff\x00\xff' * 360)
    return row * BAND_HEIGHT


def verify_data(aboot, dts):
    if len(aboot) != 1048576 or hashlib.sha256(aboot).hexdigest() != ABOOT_SHA:
        raise ValueError('Expected exact original aboot_a')
    if hashlib.sha256(dts).hexdigest() != DTS_SHA:
        raise ValueError('Expected exact preserved runtime DTS')
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', aboot)
    if header[0][:7] != b'\x7fELF\x01\x01\x01' or header[2] != 40 or header[4] != 0x91800000:
        raise ValueError('Unexpected ELF32 ARM bootloader header')
    if header[9] != 32 or not 0 < header[10] <= 32:
        raise ValueError('Unexpected ELF program-header table')
    loads = [struct.unpack_from('<8I', aboot, header[5] + i * header[9])
             for i in range(header[10])]
    expected = [p for p in loads if p[0] == 1 and
                p[1:6] == (0x8000, 0x91800000, 0x91800000, 0xCD2AC, 0xE84AC)]
    if len(expected) != 1:
        raise ValueError('Reviewed file-backed PT_LOAD mapping missing')

    def read(address, length):
        start = address - 0x91800000
        if start < 0 or start + length > 0xCD2AC:
            raise ValueError('Read outside reviewed file-backed segment')
        return aboot[0x8000 + start:0x8000 + start + length]

    # Data observations from this unit's binary, not imported source code.
    words = {
        0x918026F8: 0xE3A02000, 0x91802700: 0xE3482340,
        0x918456D8: 0xE1A08002, 0x91845994: 0xE2888A01,
        0x91845744: 0xE5848524, 0x91845940: 0xE5971000,
        0x918459A0: 0xE5871528, 0x918459A8: 0xE5871530,
    }
    for address, word in words.items():
        if struct.unpack('<I', read(address, 4))[0] != word:
            raise ValueError(f'Bootloader observation differs at {address:#x}')
    for address in (0x918977BC, 0x91897814):
        if struct.unpack('<HH', read(address, 4)) != (1440, 2560):
            raise ValueError('Panel resolution data differs')
    if read(0x918985D4, 1) != b'\x18':
        raise ValueError('Panel bit-depth data differs')
    source = dts.decode('utf-8')
    if not re.search(r'cont_splash_mem@83401000\s*\{\s*'
                     r'reg\s*=\s*<0x00 0x83401000 0x00 0x23ff000>;', source):
        raise ValueError('Runtime splash reservation differs')
    ranges = band_ranges()
    if (len(expected_band()) != BAND_BYTES or
            any(not FB_BASE <= start < end <= FB_BASE + SURFACE_BYTES
                for start, end in ranges) or ranges[0][1] > ranges[1][0]):
        raise ValueError('Invalid diagnostic footprint')
    return {'result': 'PASS-STATIC-DATA-ONLY', 'deviceContacted': False,
            'abootSha256': ABOOT_SHA, 'runtimeDtsSha256': DTS_SHA,
            'width': 1440, 'height': 2560, 'strideBytes': STRIDE,
            'bitsPerPixel': 24, 'framebufferBase': hex(FB_BASE),
            'surfaceBytes': SURFACE_BYTES,
            'bandRangesExclusive': [[hex(a), hex(b)] for a, b in ranges],
            'totalBytesWritten': BAND_BYTES * len(ranges),
            'liveScanout': 'UNKNOWN', 'deviceExecutionCleared': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aboot', type=Path, required=True)
    parser.add_argument('--runtime-dts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output already exists; preserve previous evidence')
    result = verify_data(args.aboot.read_bytes(), args.runtime_dts.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
