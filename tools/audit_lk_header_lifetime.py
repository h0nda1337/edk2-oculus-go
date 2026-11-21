"""Verify where stock LK initializes and uses the 4 KiB header workspace.
Only addresses and classifications from the pinned ELF leave the host.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct

from audit_lk_ufs_dma import audit, require

BUFFER = 0x918d7e80
SIZE = 4096
# MOVW/MOVT pairs reviewed in the boot/storage and filesystem-info paths.
# Some are separated by branches or a register spill/reload.
BASE_PAIRS = (
    (0x91838588, 0x91838590), (0x918390d0, 0x918390d8), (0x918391f8, 0x918391fc),
    (0x9183ae94, 0x9183ae9c), (0x9183b0c8, 0x9183b0cc), (0x9183b284, 0x9183b2ac),
    (0x9183b318, 0x9183b320), (0x9183b4b4, 0x9183b4b8), (0x9183b71c, 0x9183b724),
    (0x9183bc74, 0x9183bc78), (0x9183bf40, 0x9183bfdc),
)


def inspect(data, iomem):
    lk = audit(data)
    segment = lk["ptLoad"]
    base, offset, size, mem = (int(segment[k], 16) for k in ("va", "fileOffset", "fileBytes", "memoryBytes"))
    def word(address):
        require(base <= address <= base + size - 4 and address % 4 == 0, "file-backed word")
        return struct.unpack_from("<I", data, offset + address - base)[0]

    def pair(lo, hi):
        a, b = word(lo), word(hi)
        require(a & 0xfff00000 == 0xe3000000 and b & 0xfff00000 == 0xe3400000
                and (a ^ b) & 0xf000 == 0, "unexpected MOVW/MOVT")
        def imm(w):
            return (w >> 4 & 0xf000) | (w & 0xfff)
        return imm(a) | imm(b) << 16

    def literal(pc):
        insn = word(pc)
        require(insn & 0xffff0000 == 0xe59f0000, "unexpected ARM PC-relative LDR")
        return word(pc + 8 + (insn & 0xfff))

    require(all(pair(*sites) == BUFFER for sites in BASE_PAIRS), "workspace references changed")
    first, end = literal(0x918000e8), literal(0x918000ec)
    require((first, end) == (base + size, base + mem) and first <= BUFFER < BUFFER + SIZE <= end
            and [word(i) for i in range(0x918000f0, 0x91800100, 4)] ==
            [0xe3a02000, 0xe1500001, 0xb4802004, 0xbafffffc], "BSS zeroing loop")
    heap = pair(0x9184cbc0, 0x9184cbc8), pair(0x9184cbcc, 0x9184cbd4)
    require(heap == (end, 0x91c00000) and word(0x9184cbe4) == 0xe0601001
            and word(0x9184cbf0) == 0xe8831003, "initial arena base and length")
    aliases = [literal(0x9183926c), literal(0x91839284)]
    require(aliases == [BUFFER + 0x478, BUFFER + 0x488], "interior references")
    handler = word(0x91880f4c)
    name = offset + word(0x91880f48) - base
    require(data[name:name+5] == b"boot\0" and handler == 0x9183cd7c
            and word(0x9183cda4) == 0xe1a05001 and word(0x9183ce08) == 0xe5951024
            and word(0x9183d190) == 0xe595700c and word(0x9183d1a0) == 0xe2852040
            and word(0x9183d1bc) == 0xebfff608, "RAM boot header argument and handoff")
    require(word(0x9183aaf4) == 0xe5962038 and pair(0x9183aaf8, 0x9183aafc) == 0x644d5241
            and word(0x9183ab04) == 0x0a00002b and word(0x9183abd8) == 0xeaff92ea
            and pair(0x9181f7e4, 0x9181f7e8) == 0x918d3000
            and word(0x9181f7ec) == 0xe1c300f0 and word(0x9181f804) == 0xe1c304f8,
            "ARM64 handoff argument block")
    inventory = json.loads((Path(__file__).resolve().parents[1] /
                            "docs/evidence/ufs-bus-pages-20261121.json").read_bytes())
    iomem_sha = hashlib.sha256(iomem).hexdigest()
    require(iomem_sha == inventory["androidIomemSha256"], "unexpected Android iomem capture")
    overlaps = [(int(a,16), int(b,16), label.strip()) for a,b,label in
                re.findall(r"^\s*([0-9a-f]+)-([0-9a-f]+)\s*:\s*(.+)$", iomem.decode("utf-8-sig"), re.M)
                if int(a,16) < BUFFER + SIZE and BUFFER <= int(b,16)]
    require(overlaps == [(0x91700000, 0x13eabffff, "System RAM")], "unexpected later Android resource")
    return dict(androidIomemSha256=iomem_sha, androidCoveringResourceInclusive=[
                    hex(overlaps[0][0]), hex(overlaps[0][1]), overlaps[0][2]], stockElfSha256=lk["stockAbootSha256"], cpuBuffer=hex(BUFFER),
                endExclusive=hex(BUFFER+SIZE), bssClearedAtEntry=[hex(first), hex(end)],
                allocatorInitialRange=list(map(hex,heap)), baseInstructionPairs=[
                    [hex(lo), hex(hi)] for lo, hi in BASE_PAIRS],
                filesystemInfoInteriorPointers=list(map(hex, aliases)), fastbootHandler=hex(handler),
                fastbootHeader="handler argument r1 saved in r5", arm64HandoffArgumentBlock="0x918d3000",
                endpointCpuRanges=[[hex(BUFFER),hex(BUFFER+8)], [hex(BUFFER+SIZE-8),hex(BUFFER+SIZE)]],
                exclusiveAfterHandoff="UNKNOWN", retainedEndpointDma="UNKNOWN",
                scope="Selected synchronous paths in the pinned ELF. Indirect calls, other masters and retained IOMMU mappings are not exhaustively covered.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aboot", required=True, type=Path)
    parser.add_argument("--iomem", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = inspect(args.aboot.read_bytes(), args.iomem.read_bytes())
    args.report.write_text(json.dumps(result, indent=2)+"\n", encoding="utf8", newline="\n")
