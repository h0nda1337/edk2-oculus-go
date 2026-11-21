"""Recover the stock LK boot-header read workspace from the verified private ELF.
Only hashes, addresses and geometry are emitted. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from audit_lk_ufs_dma import audit, require
from collect_ufs_layout import layout

ROOT = Path(__file__).resolve().parents[1]


def inspect(elf, boot_a, boot_b, gpt):
    lk = audit(elf)
    segment = lk["ptLoad"]
    start = int(segment["va"],16)
    file_base = int(segment["fileOffset"],16)
    def span(first, end):
        require(start <= first < end <= start+int(segment["fileBytes"],16), "ELF range")
        return elf[file_base+first-start:file_base+end-start]
    def word(va):
        return int.from_bytes(span(va,va+4),"little")
    def mov_pair(lo, hi, reg):
        def imm(addr, opcode):
            w=word(addr)
            require(w & 0xfff0f000 == opcode | reg<<12, "unexpected ARM MOVW/MOVT")
            return ((w>>4)&0xf000) | (w&0xfff)
        return imm(lo,0xe3000000) | imm(hi,0xe3400000)<<16
    def branch(pc):
        op=word(pc)
        require(op>>24==0xeb, "not ARM BL")
        disp=((op&0xffffff)^0x800000)-0x800000
        return pc+8+4*disp
    base = mov_pair(0x9183ae94,0x9183ae9c,4)
    size_word = mov_pair(0x9183ae90,0x9183ae98,5)
    next_field = mov_pair(0x9183ff30,0x9183ff38,2)
    require((base,size_word,next_field)==(0x918d7e80,0x918e18d4,0x918d8e84) and
            branch(0x9183aeb4)==branch(0x918385a0)==branch(0x91839200)==0x91810e5c and
            word(0x9183aea8)==0xe5953000 and word(0x9183aeac)==0xe1a02004 and
            word(0x9183ff44)==0xe5820000 and span(0x91881224,0x9188122c)==b"ANDROID!",
            "stock header pointer, size argument, reader or comparison changed")
    require(branch(0x9183ff0c)==0x91811454 and branch(0x91811498)==0x9182b740 and
            branch(0x9183ff2c)==0x91810bcc and branch(0x91810bf4)==0x9182b740 and
            word(0x9182b754)==0xe5900010 and word(0x9183ff24)==0xe5880000,
            "UFS length accessor or saved page size changed")
    size = 4096
    require(start+int(segment["fileBytes"],16)<=base and base+size<=next_field and
            size_word+4<=start+int(segment["memoryBytes"],16), "outside LK BSS")
    capacity=json.loads((ROOT/"docs/evidence/ufs-splash-physical-layout-20261120.json").read_bytes())
    originals=json.loads((ROOT/"docs/evidence/ufs-bounce-transfer-20261121.json").read_bytes())["recovery"]["matchedBeforeAndOriginals"]
    boot_pages={}
    for key, image in (("boot_a",boot_a),("boot_b",boot_b)):
        require(hashlib.sha256(image).hexdigest()==originals[key] and image[:8]==b"ANDROID!" and
                struct.unpack_from("<I",image,36)[0]==size, "stock boot image or page size")
        boot_pages[key]=f"{zlib.crc32(image[:size]):08x}"
    require(boot_pages=={"boot_a":"90c8cea7","boot_b":"890f078c"}, "stock header fingerprints")
    table, blocks, count, stride, entries_crc=layout(gpt,size,capacity["lunBytes"]//size-1)
    hdr_crc=struct.unpack_from("<I",gpt,16)[0]
    require(f"{hdr_crc:08x}"==capacity["primaryHeaderCrc32"] and
            f"{entries_crc:08x}"==capacity["entryArrayCrc32"], "backup mismatch")
    ranges=[(0x9183ae90,0x9183aed4),(0x91838588,0x918385c4),(0x918391d4,0x91839208),
            (0x9183ff0c,0x9183ff4c),(0x91810e78,0x91810ee4),(0x91811008,0x91811044),
            (0x9182b860,0x9182b89c),(0x9182c240,0x9182c29c),(0x91811454,0x918114a0),
            (0x91810bcc,0x91810c1c),(0x9182b740,0x9182b774)]
    return dict(stockElfSha256=lk["stockAbootSha256"],cpuBuffer=hex(base),endExclusive=hex(base+size),
                pageSizeWord=hex(size_word),nearbyBlockSizeWord=hex(next_field),bytes=size,
                pages=[dict(base=hex(base&-size),bytes=size-base%size),
                       dict(base=hex((base&-size)+size),bytes=base%size)],
                oldHeaderCrc32=boot_pages,retainedBusOnPacific="UNKNOWN",
                ranges=[dict(first=hex(a),endExclusive=hex(b),sha256=hashlib.sha256(span(a,b)).hexdigest()) for a,b in ranges],
                gpt=dict(lun=4,lba=1,blockSize=size,sha256=hashlib.sha256(gpt).hexdigest(),
                         headerCrc32=f"{hdr_crc:08x}",sectorCrc32=f"{zlib.crc32(gpt):08x}",
                         tableLba=table,tableBlocks=blocks,entries=count,entryBytes=stride))

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ("aboot","boot-a","boot-b","gpt-header","report"):
        ap.add_argument("--"+key,required=True,type=Path)
    args=ap.parse_args()
    result=inspect(args.aboot.read_bytes(),args.boot_a.read_bytes(),args.boot_b.read_bytes(),args.gpt_header.read_bytes())
    args.report.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8",newline="\n")
