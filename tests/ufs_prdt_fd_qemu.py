"""Boot the passive native PRDT inspection with retained and stale descriptors.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from sec_mem_qemu import FB_BASE, RAM_START, ROOT, RUNTIME_SHA, SURFACE_BYTES, require
from ufs_data_fd_qemu import TM, TR, board_guest
from ufs_data_qemu import CAPACITY
from ufs_handoff_qemu import screen_oracle
from ufs_header_fd_qemu import profile
from ufs_nop11_bus import BAR, PAGE, WINDOW
from ufs_nop11_fd_qemu import run_cpu

GUID = "7445d27c-1a27-4630-813f-09c91572c3fe"
UCD = 0x918fdf00
DATA = WINDOW+PAGE
# Keep the actual preceding DMA out of the FD so the SEC cleanliness check
# still describes the original FD on guest entry. Deltas in archived metadata
# for the READ(10) cases are fixtures, never SCSI requests to the medium.
ARCHIVE = 0x91940000
CASES = {"capacity":"PRDT:OUTSIDE", "other-backing":"PRDT:OUTSIDE", "native-read":"PRDT:COVERS",
         "native-read16":"PRDT:COVERS", "partial":"PRDT:PARTIAL", "short-read":"STOP:BLOCKS", "two-prds":"PRDT:COVERS",
         "gap":"STOP:ENTRY", "zero-prd":"PRDT:NO DATA", "moved":"STOP:UCD MOVED",
         "bounds":"STOP:DESCRIPTOR", "changed":"STOP:CHANGED", "stale-tag":"STOP:UPIU", "bad-ocs":"STOP:DESCRIPTOR"}


def one(tmp, fd, entry, dt, regs, pc, el, name):
    physical = ARCHIVE+2*PAGE if name=="other-backing" else ARCHIVE
    leaves = [(UCD & -PAGE, UCD & -PAGE), (ARCHIVE, physical)]
    with board_guest(tmp, fd, entry, dt, regs, el, leaves=leaves) as (g,ram,bus,trace):
        req = bytearray(32)
        req[:4] = bytes([1,0x40,4,0x9d])
        req[12:16] = (8).to_bytes(4,"big")
        req[16] = 0x25
        table = UCD+128
        desc = [0x05000000,0,15,0,UCD,0,(8<<16)|8,(32<<16)|1]
        bus.write(UCD,req)
        bus.write(table,struct.pack("<4I",ARCHIVE,0,0,7))
        bus.write(physical,bytes([0xa5])*8)
        for attempt in range(2):
            bus.write(UCD+32,bytes([0xa5])*64)
            bus.write(TR,struct.pack("<8I",*desc))
            bus.write32(BAR+0x58,1)
            bus.wait_bits(BAR+0x58,1,0)
            response = bus.read(UCD+32,32)
            require(bus.read32(TR+8)==0 and response[0]==0x21 and response[3]==0x9d and
                    response[7]==(2 if attempt==0 else 0), "preceding command failed")
        require(bus.read(physical,8)==CAPACITY, "virtual UFS did not transfer capacity")
        if physical!=ARCHIVE:
            require(bus.read(ARCHIVE,8)!=CAPACITY, "numeric alias updated")
        op, first, total, count = 0x25, ARCHIVE, 8, 1
        if name in ("native-read","native-read16","partial","short-read","two-prds","gap"):
            op=0x88 if name=="native-read16" else 0x28
            count=2 if name in ("two-prds","gap") else 1
            first=DATA-0x40000 if count==2 else DATA+4 if name=="partial" else DATA
            total=0x41000 if count==2 else PAGE
            req[12:16]=total.to_bytes(4,"big")
            req[16]=op
            blocks=2 if name=="short-read" else total//PAGE
            if op==0x88:
                req[26:30]=blocks.to_bytes(4,"big")
            else:
                req[23:25]=blocks.to_bytes(2,"big")
            bus.write(UCD,req)
            bus.write(table,struct.pack("<4I",first,0,0,0x3ffff if count==2 else PAGE-1))
            if count==2:
                bus.write(table+16,struct.pack("<4I",DATA+(4 if name=="gap" else 0),0,0,PAGE-1))
            bus.write32(TR+28,(32<<16)|count)
        if name=="moved":
            bus.write32(TR+16,UCD+128)
        if name=="zero-prd":
            bus.write32(TR+28,0)
            count=0
        if name=="bounds":
            bus.write32(TR+28,(60<<16)|2)
            count=2
        if name=="bad-ocs":
            bus.write32(TR+8,15)
        if name=="stale-tag":
            bus.write(UCD+35,b"\x01")
        change = (table,lambda device: device.write32(UCD+16,0)) if name=="changed" else None
        before = bus.read(UCD,256)
        slot = bus.read(TR,32)
        def no_ring(*args):
            raise ValueError("passive SEC issued UFS command")
        require(run_cpu(g,bus,pc,el,no_ring,on_first_read=change)==0,"firmware submitted UFS")
        expected = bytearray(before)
        if change:
            expected[16:20]=bytes(4)
        require(bus.read(TR,32)==slot and bus.read(UCD,256)==expected,"metadata was modified")
        state,label = CASES[name].split(":")
        lines=[("UFS "+state).ljust(14)+label, f"UCD   {UCD+(128 if name=='moved' else 0):08X}",
               "", "", "", "", "", "CPU ONLY"]
        if name!="moved":
            lines[2]=f"NPRD  {count:08X}"
        if name not in ("moved","zero-prd","bounds","bad-ocs","changed"):
            lines[3:5]=[f"OP    {op:08X}","LUN   00000004"]
        if state=="PRDT" and count:
            lines[5:7]=[f"FIRST {first:08X}",f"LAST  {first+total-1:08X}"]
        screen_oracle(os.pread(ram,SURFACE_BYTES,FB_BASE-RAM_START),lines)
    events=trace.read_text().splitlines()
    require(events==["ufs_exec_nop_cmd UTRLDBR slot 0"]+["ufs_exec_scsi_cmd slot 0, lun 0x4, opcode 0x25"]*2,
            "unexpected device trace: "+str(events))
    return dict(case=name,el=el,panel=lines,fixtureCapacityBus=hex(ARCHIVE),fixtureCapacityCpu=hex(physical),
                firmwareDoorbells=0,mediaReads=0,mediaWrites=0)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("fd","sec-elf","runtime-fdt","report","static-report"):
        ap.add_argument("--"+name,type=Path,required=True)
    args=ap.parse_args()
    pc,static=profile(args.fd,args.sec_elf,True,GUID)
    dt=args.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest()==RUNTIME_SHA,"wrong runtime DT")
    args.static_report.write_text(json.dumps(static,indent=2)+"\n")
    panel=json.loads((ROOT/"docs/evidence/ufs-handoff-transfer-20261121.json").read_bytes())["physicalPanel"]
    regs={k:int(v,16) for k,v in panel["registersHex"].items()} | dict(CAP=0x0107001f,TRL=TR,TRH=0,TML=TM,TMH=0)
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory)
        obj,entry=base/"entry.o",base/"entry.bin"
        subprocess.run(["aarch64-linux-gnu-gcc","-c",ROOT/"tests/entry_harness.S","-o",obj],check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy","-O","binary",obj,entry],check=True)
        def job(pair):
            el,name=pair
            tmp=base/f"{name}-{el}"
            tmp.mkdir()
            row=one(tmp,args.fd,entry,dt,regs,pc,el,name)
            print(el,name,row["panel"][0],flush=True)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            cases=list(pool.map(job,[(1,n) for n in CASES]+[(2,"capacity")]))
    args.report.write_text(json.dumps(dict(outcome="PASS-QEMU-PRDT",fdSha256=static["fdSha256"],
        physicalFdBus="UNKNOWN",cases=cases),indent=2)+"\n")


if __name__=="__main__":
    main()
