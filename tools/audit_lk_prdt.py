"""Trace the original UFS PRD builder and identify the named ANOC2 records.
Only offsets, file hashes and observations leave the backup directory.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_lk_ufs_dma import audit, require

ROOT = Path(__file__).resolve().parents[1]


def inspect(folder):
    inventory = json.loads((ROOT/"docs/evidence/partitions.json").read_bytes())
    known = {row["name"]:row["sha256"] for row in inventory["partitions"]}
    aboot = (folder/"aboot_a.img").read_bytes()
    stock = audit(aboot)
    segment = stock["ptLoad"]
    base, offset, size = (int(segment[key],16) for key in ("va","fileOffset","fileBytes"))
    def at(address, expected):
        require(base <= address <= base+size-4*len(expected), "outside LK text")
        actual = struct.unpack_from("<"+"I"*len(expected),aboot,offset+address-base)
        require(actual==tuple(expected), f"unexpected LK instructions at {address:#x}")
    # Copy the CDB to request +16. Store the native command's data pointer
    # unchanged in PRD0; subsequent native PRDs advance it by 256 KiB.
    at(0x9182bf34,[0xe3a01001,0xe2870f5d])
    at(0x9182bf68,[0xeb002227,0xe5c60003])
    at(0x9183480c,[0xe190cf9f,0xe08c2001,0xe1803f92,0xe3530000,0x1afffffa,0xe1a0000c,0xe12fff1e])
    at(0x9182c1f4,[0xe2860010,0xe3a02010,0xeb008694])
    at(0x9182bfa4,[0xe28a3020,0xe58d301c])
    at(0x9182c0f4,[0x11a0212e,0x11c321be])
    at(0x9182c240,[0xe1c521d8,0xe595e008,0xe1921003,0xe3a01000,0xe1a0000e,0xe1cd01f0])
    at(0x9182c27c,[0xe786e001,0xe2400001,0xe3a01000,0xe58c000c,0xe5cc1004,0xe5cc1005,0xe5cc1006,0xe5cc1007])
    at(0x9182c2bc,[0xe58c0000,0x83a0e701,0xe2900701,0xe58c1004,0xe2a11000])
    marker = struct.pack("<I",0x01680000)+b"ANOC2\0"
    records = {}
    for name in ("hyp_a","tz_a"):
        data = (folder/(name+".img")).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        require(digest==known[name], "wrong "+name)
        indices = []
        pos = data.find(marker)
        while pos >= 0:
            indices.append(hex(pos))
            pos = data.find(marker,pos+len(marker))
        require(len(indices)==2,"unexpected record count")
        records[name] = dict(sha256=digest, namedBaseOffsets=indices)
    prior = json.loads((ROOT/"docs/evidence/ufs-heap4k-transfer-20261121.json").read_bytes())
    observed = prior["observation"]
    require(observed["ucdBusFromUtrd"]=="0x918fdf00" and observed["responseBusFromDescriptor"]=="0x918fdf20",
            "different prior slot")
    return dict(stockElfSha256=stock["stockAbootSha256"], firstDataPointer="native command +8",
                taskTag="previous counter at HBA+0x174, low byte", taskTagStore="0x9182bf6c",
                firstPrdStore="0x9182c27c", prdtOffsetStore="0x9182c0f8",
                fullSegmentBytes=262144, nextPrdIncrement="0x9182c2c4",
                namedAnoc2Base="0x01680000", namedRecords=records, physicalUfsStreamId="UNKNOWN",
                observedUcd=observed["ucdBusFromUtrd"], probeCpuLimitExclusive="0x918fe000",
                directFdBusCandidate="0x80441000", directFdBus="UNKNOWN")


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backup-directory",type=Path,required=True)
    ap.add_argument("--report",type=Path,required=True)
    args=ap.parse_args()
    args.report.write_text(json.dumps(inspect(args.backup_directory),indent=2)+"\n",encoding="utf8",newline="\n")
