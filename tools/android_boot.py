"""Original Android boot-v0 container writer; Python standard library only.

No external mkbootimg or firmware-copy stub is invoked. Local inputs are
pinned to the previously captured unit. Never communicates with a device.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import zlib

from verify_fd import verify

STOCK_SHA = 'cde63f886a379f51d328d7c01a65884ead57bf3b295755f0303e19876ce754be'
DTB_SHA = '70ae171c99befc564acec661f3afc4365a831ebd1d6e01ca0e53035a4d8b1f35'
HEADER = struct.Struct('<8s10I16s512s32s1024s')
PAGE = 4096


def digest(data):
    return hashlib.sha256(data).hexdigest()


def padded(data):
    return data + bytes((-len(data)) % PAGE)


def check_stock(stock):
    if digest(stock) != STOCK_SHA:
        raise ValueError('Original boot_a hash mismatch')
    if len(stock) < HEADER.size:
        raise ValueError('Stock header truncated')
    fields = HEADER.unpack_from(stock)
    if fields[0] != b'ANDROID!' or fields[8] != PAGE or fields[9] != 0:
        raise ValueError('Unexpected stock Android container format')
    return fields


def make_container(fd, dtb):
    verify(fd)
    if digest(dtb) != DTB_SHA:
        raise ValueError('Expected exact local Pacific EVT DTB')
    if len(dtb) < 40 or dtb[:4] != b'\xd0\x0d\xfe\xed':
        raise ValueError('Not a flattened device tree')
    if struct.unpack_from('>I', dtb, 4)[0] != len(dtb):
        raise ValueError('DTB total size mismatch')
    # Gzip's mtime is fixed. zlib/Python versions are captured in the manifest.
    kernel = gzip.compress(fd, compresslevel=9, mtime=0) + dtb
    identifier = hashlib.sha1()
    for component in (kernel, b'', b''):
        identifier.update(component)
        identifier.update(struct.pack('<I', len(component)))
    header = HEADER.pack(b'ANDROID!', len(kernel), 0x80008000,
        0, 0, 0, 0, 0x80000100, PAGE, 0, 0,
        b'oculusgo-uefi', bytes(512), identifier.digest().ljust(32, b'\0'), bytes(1024))
    return padded(header) + padded(kernel)


def verify_container(image, expected_fd, expected_dtb):
    if len(image) < PAGE:
        raise ValueError('Container truncated')
    fields = HEADER.unpack_from(image)
    if (fields[0] != b'ANDROID!' or fields[2:11] !=
            (0x80008000, 0, 0, 0, 0, 0x80000100, PAGE, 0, 0)):
        raise ValueError('Container header mismatch')
    length = fields[1]
    if length == 0 or len(image) != PAGE + (length + PAGE - 1) // PAGE * PAGE:
        raise ValueError('Container length mismatch')
    if any(image[HEADER.size:PAGE]) or any(image[PAGE + length:]):
        raise ValueError('Container padding is not zero')
    kernel = image[PAGE:PAGE + length]
    decoder = zlib.decompressobj(31)
    decoded = decoder.decompress(kernel, len(expected_fd) + 1)
    if not decoder.eof or decoded != expected_fd or decoder.unused_data != expected_dtb:
        raise ValueError('FD or appended DTB roundtrip failed')
    identifier = hashlib.sha1(kernel + struct.pack('<I', length) + bytes(8)).digest()
    if fields[13] != identifier.ljust(32, b'\0'):
        raise ValueError('Container identifier mismatch')
    return {'roundtrip': 'PASS', 'kernelSize': length,
            'decompressedFdSize': len(decoded), 'appendedDtbSize': len(expected_dtb)}


def main():
    import platform
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fd', type=Path, required=True)
    parser.add_argument('--dtb', type=Path, required=True)
    parser.add_argument('--stock-boot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix('.json').exists():
        raise SystemExit('Output exists; use a new output path')
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root / 'local'):
        raise SystemExit('Device-derived containers must stay under local/')
    check_stock(args.stock_boot.read_bytes())
    fd = args.fd.read_bytes()
    dtb = args.dtb.read_bytes()
    image = make_container(fd, dtb)
    checks = verify_container(image, fd, dtb)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    manifest = {
        'status': 'OFFLINE-CANDIDATE-NOT-FOR-DEVICE-EXECUTION',
        'imageSha256': digest(image), 'imageSize': len(image),
        'fdSha256': digest(fd), 'dtbSha256': digest(dtb), 'stockBootSha256': STOCK_SHA,
        'bootShim': False, 'externalPackager': False, 'firmwareCopyStage': False,
        'python': platform.python_version(), 'zlib': zlib.ZLIB_RUNTIME_VERSION,
        'deviceExecution': 'UNKNOWN', 'writesToDevice': False,
        'verification': checks,
    }
    output.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
