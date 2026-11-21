"""Reconstruct LUN 4 from private readbacks in a sparse, host-only fixture.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from collect_ufs_layout import layout


def write_lun(path, source, capture):
    measured = json.loads((ROOT / "docs/evidence/ufs-splash-physical-layout-20261120.json").read_text())
    live = json.loads((capture / "layout.json").read_text())
    header = (capture / "primary-header.bin").read_bytes()
    entries = (capture / "primary-entries.bin").read_bytes()
    block, capacity = live["blockSize"], live["diskBytes"]
    if (block, capacity, live["scsiDevice"].split("/")[-1]) != (
            measured["logicalBlockBytes"], measured["lunBytes"], measured["scsiAddress"]):
        raise ValueError("Private LUN geometry differs from the reviewed measurement")
    last = capacity // block - 1
    table, blocks, count, stride, crc = layout(header, block, last)
    if (len(entries) != count * stride or zlib.crc32(entries) != crc
            or crc != int(measured["entryArrayCrc32"], 16)
            or struct.unpack_from("<I", header, 16)[0] != int(measured["primaryHeaderCrc32"], 16)):
        raise ValueError("Unexpected primary GPT")
    hits = [(i + 1, *struct.unpack_from("<QQ", entries, i * stride + 32))
            for i in range(count) if entries[i * stride:i * stride + 16] != bytes(16)
            and entries[i * stride + 56:i * stride + 70] == "splash\0".encode("utf-16-le")]
    start, end = measured["firstLba"], measured["lastLbaInclusive"]
    if (hits != [(measured["gptEntry"], start, end)] or (start, end) != (live["start"], live["end"])
            or len(source) != (end - start + 1) * block):
        raise ValueError("Unexpected splash extent")
    backup = bytearray(header)
    struct.pack_into("<QQ", backup, 24, last, 1)
    struct.pack_into("<Q", backup, 72, last - blocks)
    struct.pack_into("<I", backup, 16, 0)
    struct.pack_into("<I", backup, 16, zlib.crc32(backup[:struct.unpack_from("<I", backup, 12)[0]]))
    mbr = bytearray(512)
    struct.pack_into("<B3sB3sII", mbr, 446, 0, b"\0\2\0", 0xee, b"\xff" * 3, 1, min(last, 0xffffffff))
    mbr[510:] = b"\x55\xaa"
    with path.open("xb") as f:
        f.truncate(capacity)
        for lba, blob in [(0, mbr), (1, header), (table, entries), (start, source),
                          (last - blocks, entries), (last, backup)]:
            f.seek(lba * block)
            f.write(blob)
    return {"lun": measured["lun"], "capacityBytes": capacity, "lastLba": last,
            "blockBytes": block, "gptEntry": hits[0][0], "firstSplashLba": start,
            "lastSplashLbaInclusive": end, "entryCount": count}
