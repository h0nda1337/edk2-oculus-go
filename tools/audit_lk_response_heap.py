"""Check the UTRD response pointer and allocator path in the private stock ELF.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
import struct
from pathlib import Path

from audit_lk_ufs_dma import audit, require


def inspect(data):
    stock = audit(data)
    segment = stock["ptLoad"]
    va, size, offset = (int(segment[key], 16) for key in ("va", "fileBytes", "fileOffset"))

    def words(address, expected):
        start = address - va
        require(start >= 0 and start + 4*len(expected) <= size, "outside file-backed segment")
        actual = struct.unpack_from("<" + "I"*len(expected), data, offset+start)
        require(actual == tuple(expected), f"unexpected ARM code at {address:#x}")

    # Allocates aligned memory, stores its low 32 bits into the UTRD and
    # encodes the response offset in dwords. r6 owns the allocation.
    words(0x9182bedc, [0xe3a00080])
    words(0x9182bef4, [0xeb0086e9, 0xe2506000])
    words(0x9182c0c4, [0xe3c6203f, 0xe5c31008, 0xe1a01426, 0xe5c32010,
                       0xe1a02826, 0xe5c31011, 0xe1a01c26, 0xe5c32012,
                       0xe3a02008, 0xe5c31013, 0xe3a01020, 0xe5c3201a])
    words(0x9182c1d0, [0xe1a00006, 0xeb00865d])
    words(0x9184db80, [0xeafffbba])
    words(0x9184caac, [0xe5163008, 0xe5162004, 0xe1a00003, 0xe5832008, 0xebffff1e])
    words(0x9184c73c, [0xe3031168, 0xe349118e])
    words(0x9184c74c, [0xe591300c, 0xe2812008])
    words(0x9184c780, [0xe5933004])
    words(0x9184c7b8, [0xe5912008, 0xe0814002])
    return dict(stockElfSha256=stock["stockAbootSha256"], ucdAllocationAlignment=128,
                allocCall="0x9182bef4", utrdAddressStores=["0x9182c0c4", "0x9182c0e8"],
                responseOffsetBytes=32, offsetStore="0x9182c0f0", freeCall="0x9182c1d4",
                insertCall="0x9184cabc", freeListHead="0x918e3170",
                extentOffsets={"previous": 0, "next": 4, "bytes": 8}, retainedBusOfFdPage="UNKNOWN",
                scope="Static path. The last slot and current free-list membership require a live snapshot.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aboot", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.aboot.read_bytes())
    args.report.write_text(json.dumps(result, indent=2)+"\n", encoding="utf8", newline="\n")
