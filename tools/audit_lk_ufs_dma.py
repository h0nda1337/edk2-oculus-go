"""Reproduce the address provenance in the privately backed-up stock Go ELF.
This host-side reader emits annotations and hashes only. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

STOCK = "6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74"
# Half-open ARM instruction ranges. They can be inspected independently with
# an ARM disassembler using the ELF program headers, irrespective of symbols.
RANGES = {
    "board fills HBA context": (0x91800ed0, 0x91800eec),
    "CPU dynamic mapping arguments and fixed table loop": (0x9180422c, 0x91804284),
    "3 GiB reported DRAM case chooses low identity mapping": (0x91804304, 0x91804328),
    "transfer allocation saved at HBA+0x178": (0x9182ba08, 0x9182ba70),
    "both lists programmed and enabled": (0x9182bac0, 0x9182bb04),
    "allocation of transfer list": (0x9182cee4, 0x9182cf4c),
    "allocation of task list": (0x9182cf4c, 0x9182cfa8),
    "allocate, maintain cache, return same pointer": (0x9184daa0, 0x9184daf0),
    "use same allocation for CPU-side transfer slot": (0x9182c054, 0x9182c088),
    "UCD address bytes in UTRD": (0x9182c0c4, 0x9182c0ec),
    "boot image staging base accessor": (0x91801468, 0x918014a0),
    "boot selects that staging base": (0x9183b0c0, 0x9183b0d8),
    "boot reads image body into staging plus header": (0x9183b190, 0x9183b1b0),
    "UFS block read receives caller buffer": (0x91811008, 0x91811064),
    "first PRD address, high half, length": (0x9182c240, 0x9182c29c),
    "submission barriers": (0x9182c12c, 0x9182c13c),
    "cache operations with 128-byte steps": (0x9183476c, 0x918347b8),
    "CPU TTBR0 and TTBCR arguments": (0x91835194, 0x918351c8),
    "CPU L2 table pool and 2 MiB leaf builder": (0x91834ec8, 0x91835004)
}


def require(ok, label):
    if not ok:
        raise ValueError(label)


def audit(data):
    digest = hashlib.sha256(data).hexdigest()
    require(digest == STOCK, "unexpected stock aboot_a digest")
    require(data[:6] == b"\x7fELF\x01\x01" and struct.unpack_from("<H", data, 18)[0] == 40,
            "expected 32-bit little-endian ARM ELF")
    phoff, = struct.unpack_from("<I", data, 28)
    entsize, count = struct.unpack_from("<HH", data, 42)
    loads = [struct.unpack_from("<8I", data, phoff+i*entsize) for i in range(count)]
    segment, = [h for h in loads if h[0] == 1 and h[2] == 0x91800000]
    _, offset, base, physical, size, memsz, _, _ = segment
    require(physical == base and offset+size <= len(data), "ELF segment")
    def read(va, n):
        i = va-base
        require(0 <= i <= size-n, "outside file-backed ELF bytes")
        return data[offset+i:offset+i+n]
    def u32(va):
        return int.from_bytes(read(va, 4), "little")
    def imm16(va, upper, reg):
        op = u32(va)
        require(op & 0xfff0f000 == (0xe3400000 if upper else 0xe3000000) | reg << 12, "ARM MOVW/T")
        return ((op >> 4) & 0xf000) | (op & 0xfff)
    hba = imm16(0x91800ed0, False, 3) | (imm16(0x91800ed4, True, 3) << 16)
    root = imm16(0x91835198, False, 0) | (imm16(0x9183519c, True, 0) << 16)
    pool, pages = struct.unpack("<IQ", read(0x9189cea0, 12))
    require(hba == 0x918e3230 and root == 0x918e4000 and pool == 0x918e5000 and pages == 3 and
            base+size <= hba < root < pool and pool+pages*4096 <= base+memsz, "objects outside LK BSS")
    fixed = []
    for pos in range(0x91898d18, 0x91898e30, 40):
        pa, va, kind, mib, attrs = struct.unpack("<QQB7xQQ", read(pos, 40))
        require(kind == 3 and va == pa, "unexpected fixed CPU range")
        fixed.append({"va": hex(va), "pa": hex(pa), "lengthMiB": mib, "attributes": hex(attrs)})
    return {"scope": "stock-LK-static-analysis", "stockAbootSha256": digest,
            "ptLoad": {"va": hex(base), "pa": hex(physical), "fileOffset": hex(offset),
                       "fileBytes": hex(size), "memoryBytes": hex(memsz)},
            "ufsHbaVa": hex(hba), "cpuTtbr0": hex(root), "cpuTablePool": hex(pool),
            "cpuTablePoolPages": pages, "fixedCpuMappings": fixed,
            "reviewedCode": [{"meaning": meaning, "firstVa": hex(start), "endExclusiveVa": hex(end),
                              "sha256": hashlib.sha256(read(start, end-start)).hexdigest()}
                             for meaning, (start, end) in RANGES.items()],
            "physicalUfsAccessTo80440000": "UNKNOWN"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aboot", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args()
    args.report.write_text(json.dumps(audit(args.aboot.read_bytes()), indent=2) + "\n",
                           encoding="utf-8", newline="\n")
