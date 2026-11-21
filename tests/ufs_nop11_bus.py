"""QEMU PCI UFS and SMMUv3 fixtures. No Pacific MMIO or storage access.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import struct
from ufs_lk_nop_qemu import BAR, TR, TM, check

WINDOW, IOVA, PAGE, HBA = 0x80440000, 0x88000000, 4096, 0x918e3230
HBA_WORDS = {4: 0x624000, 0x178: TR, 0x17c: 0, 0x1b8: TM, 0x1bc: 0,
             0x168: HBA+0x168, 0x16c: HBA+0x168, 0x170: 0,
             0x1a8: HBA+0x1a8, 0x1ac: HBA+0x1a8, 0x1b0: 0}

def set_translation(bus):
    # virt PCI requester 00:01.0 -> SID 8. Map only five 4 KiB leaves.
    smmu, ste, root = 0x9050000, 0x40500000, 0x40510000
    check((bus.read32(smmu) & 1) == 1, "SMMUv3 stage 2 absent")
    tables = {}
    def link(table, index):
        key = (table, index)
        if key not in tables:
            dest = root + PAGE * (1 + len(tables))
            tables[key] = dest
            bus.write(table + 8 * index, struct.pack("<Q", dest | 3))
        return tables[key]
    for va, pa in [(TR & -PAGE, TR & -PAGE)] + [(IOVA+n*PAGE, WINDOW+n*PAGE) for n in range(4)]:
        mid = link(root, (va >> 30) & 511)
        leaf = link(mid, (va >> 21) & 511)
        bus.write(leaf + 8*((va >> 12) & 511), struct.pack("<Q", pa | 0x4ff))
    bus.write(ste + 8*64, struct.pack("<16I", 13, 0, 0, 0, 1, 32 | (1<<6) | (2<<16) | (1<<19),
                                      root, 0, *([0]*8)))
    bus.command(f"writeq {smmu+0x80:#x} {ste:#x}")
    bus.write32(smmu+0x88, 5)
    bus.write32(smmu+0x20, 1)
    bus.wait_bits(smmu+0x24, 1, 1)

def seed_lk(bus):
    for off, value in HBA_WORDS.items():
        bus.write32(HBA+off, value)
    page = TR & -PAGE
    bus.write(page, bytes((i*29+13) & 255 for i in range(PAGE)))
    for off, value in ((0x50,TR),(0x54,0),(0x70,TM),(0x74,0),(0x60,1),(0x80,1)):
        bus.write32(BAR+off, value)
    # Complete a real control transfer on slot zero before booting SEC.
    bus.write(page, bytes(32))
    bus.write(TR, struct.pack("<8I", 0x21000000,0,15,0,page,0,0x200008,0))
    bus.write32(BAR+0x58, 1)
    bus.wait_bits(BAR+0x58, 1, 0)
    check(bus.read32(TR+8) == 0 and bus.read32(page+128) == 0x20, "inherited NOP did not complete")
