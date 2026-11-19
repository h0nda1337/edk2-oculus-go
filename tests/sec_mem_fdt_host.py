"""Exercise the exact SEC_MEM FDT reader against the preserved Go trees on Linux.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import ctypes
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = '0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929'
STOCK = '70ae171c99befc564acec661f3afc4365a831ebd1d6e01ca0e53035a4d8b1f35'


def verified(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Capture differs from the specimen used in the memory review')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--stock', type=Path, required=True)
    args = parser.parse_args()
    live, stock = verified(args.runtime, RUNTIME), verified(args.stock, STOCK)
    with tempfile.TemporaryDirectory() as temp:
        lib = Path(temp) / 'reader.so'
        subprocess.run(['gcc', '-shared', '-fPIC', '-fshort-wchar', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', ROOT / 'edk2/MdePkg/Include', '-I', ROOT / 'edk2/MdePkg/Include/X64',
                        '-I', ROOT / 'OculusGoPkg/SecMem', '-x', 'c', '-', '-o', lib], check=True,
                       input=b'#include "Fdt.c"\n__attribute__((visibility("default"))) '
                             b'BOOLEAN HostCheck(CONST VOID *p) { return OculusGoSecMemValidateFdt(p); }\n')
        reader = ctypes.CDLL(str(lib)).HostCheck
        reader.argtypes, reader.restype = [ctypes.c_void_p], ctypes.c_uint8

        def check(label, data, expected):
            if bool(reader(ctypes.create_string_buffer(data))) != expected:
                raise ValueError(f'Unexpected result for {label}')
            print('PASS', label)

        check('runtime memory tuple', live, True)
        check('stock unpopulated RAM', stock, False)
        for offset, value in [(0, 0), (4, 512 * 1024 + 1), (4, 39), (8, 55),
                              (12, 0xffffffff), (16, 41), (20, 18), (24, 17),
                              (32, 0), (36, 0xfffffffc)]:
            data = bytearray(live)
            struct.pack_into('>I', data, offset, value)
            check(f'header field {offset}/{value}', bytes(data), False)

        # Re-encode using the system device-tree tools. The original captures are read only.
        path = Path(temp) / 'fixture.dtb'
        for address, size, allowed in [(0x93ffffff, 1, True), (0x93ffffff, 2, False),
                                       (0x94000007, 1, False), (0x94000008, 1, True),
                                       (0x97ffff9f, 2, False), (0x97ffffa7, 1, False),
                                       (0x97ffffa8, 1, True)]:
            path.write_bytes(live)
            subprocess.run(['fdtput', '-t', 'x', path,
                            '/reserved-memory/dfps_data_mem@83400000', 'reg',
                            '0', f'{address:x}', '0', f'{size:x}'], check=True)
            check(f'reserved interval {address:#x}+{size}', path.read_bytes(), allowed)


if __name__ == '__main__':
    main()
