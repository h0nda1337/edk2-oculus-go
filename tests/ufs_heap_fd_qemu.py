"""Run the CPU-only LK allocator probe, including an indistinguishable UFS IOVA alias.
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
from ufs_handoff_qemu import screen_oracle
from ufs_header_fd_qemu import profile
from ufs_nop11_bus import BAR, PAGE
from ufs_nop11_fd_qemu import run_cpu

GUID = "c4813517-f568-49eb-bb60-d8db839c96d2"
HEAD = 0x918e3170
BUS_PAGE = 0x91908000
NODE = BUS_PAGE-0x400
CASES = {"free":"HEAP:CANDIDATE", "alias":"HEAP:CANDIDATE", "short":"HEAP:NO PAGE",
         "metadata":"HEAP:NO PAGE", "empty":"HEAP:NO PAGE", "queue":"SHARED:QUEUE PAGE",
         "outside":"STOP:HEAP LIST", "loop":"STOP:HEAP LIST", "changing":"STOP:HEAP LIST",
         "queue-listed-free":"STOP:HEAP LIST", "stale-ocs":"STOP:SLOT", "wrong-offset":"STOP:SLOT"}


def run_case(tmp, fd, harness, dt, regs, pc, el, name):
    page = TR & -PAGE if name == "queue" else BUS_PAGE
    physical = 0x91960000 if name == "alias" else page
    leaves = [] if name == "queue" else [(page, physical)]
    node = page if name == "metadata" else NODE
    size = 0x900 if name == "short" else 0x2000
    base = page + 128
    with board_guest(tmp, fd, harness, dt, regs, el, leaves=leaves) as (g,ram,bus,trace):
        # The virtual host fetches the request and writes a real NOP IN. Only
        # the UTRD is retained by the observer, independently of later heap use.
        bus.write(physical+128, bytes(32)+bytes([0xa5])*32)
        bus.write(TR, struct.pack("<8I",0x21000000,0,15,0,base,0,(8<<16)|8,0))
        bus.write32(BAR+0x58,1)
        bus.wait_bits(BAR+0x58,1,0)
        require(bus.read32(TR+8)==0 and bus.read(physical+160,1)==b"\x20","NOP IN missing")
        if name == "alias":
            require(bus.read(page+160,1)!=b"\x20","alias also updated identity RAM")
        if name == "stale-ocs":
            bus.write32(TR+8,15)
        if name == "wrong-offset":
            bus.write32(TR+24,(32<<16)|8)
        if name == "empty":
            bus.write(HEAD,struct.pack("<II",HEAD,HEAD))
        elif name == "outside":
            bus.write(HEAD,struct.pack("<II",node,0x624000))
        else:
            if name == "queue-listed-free":
                node = TR-0x100
            bus.write(HEAD,struct.pack("<II",node,node))
            bus.write(node,struct.pack("<III",HEAD,node if name=="loop" else HEAD,size))
        queues = bus.read(TR & -PAGE,PAGE)
        area = bus.read(node,12)
        start_head = bus.read(HEAD,8)
        def mutate(device):
            device.write32(HEAD, HEAD)
        change = (node+8,mutate) if name=="changing" else None
        def unexpected(*args):
            raise ValueError("passive image submitted UFS")
        rings = run_cpu(g,bus,pc,el,unexpected,on_first_read=change)
        expected_head = struct.pack("<II",HEAD,node) if change else start_head
        require(rings==0 and bus.read(TR & -PAGE,PAGE)==queues and bus.read(node,12)==area
                and bus.read(HEAD,8)==expected_head, "queue or allocator modified")
        state,label=CASES[name].split(":")
        lines=[("UFS "+state).ljust(14)+label,"","","","","","","CPU ONLY"]
        if label!="SLOT":
            lines[1:4]=[f"UCD  {base:08X}",f"RSP  {base+32:08X}",f"PAGE {page:08X}"]
        if state in ("HEAP","SHARED"):
            lines[4]=f"NODES {0 if name=='empty' else 1:08X}"
        if label=="CANDIDATE":
            lines[5:7]=[f"FREE {node:08X}", f"END  {node+size:08X}"]
        screen_oracle(os.pread(ram,SURFACE_BYTES,FB_BASE-RAM_START),lines)
    events=trace.read_text().splitlines()
    require(events==["ufs_exec_nop_cmd UTRLDBR slot 0"]*2,"unexpected SCSI or disk access: "+str(events))
    return dict(case=name,el=el,panel=lines,fixtureResponseBus=hex(base+32),
                fixtureResponseCpu=hex(physical+160),probeDoorbells=rings,mediaCommands=0)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ("fd","sec-elf","runtime-fdt","report","static-report"):
        ap.add_argument("--"+key,type=Path,required=True)
    args=ap.parse_args()
    pc,static=profile(args.fd,args.sec_elf,True,GUID)
    dt=args.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest()==RUNTIME_SHA,"unknown FDT")
    args.static_report.write_text(json.dumps(static,indent=2)+"\n")
    capture=json.loads((ROOT/"docs/evidence/ufs-handoff-transfer-20261121.json").read_bytes())
    regs={key:int(value,16) for key,value in capture["physicalPanel"]["registersHex"].items()}
    regs.update(CAP=0x0107001f,TRL=TR,TRH=0,TML=TM,TMH=0)
    with tempfile.TemporaryDirectory() as work:
        tmp=Path(work)
        elf,setup=tmp/"entry.o",tmp/"entry.bin"
        subprocess.run(["aarch64-linux-gnu-gcc","-c",ROOT/"tests/entry_harness.S","-o",elf],check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy","-O","binary",elf,setup],check=True)
        def one(pair):
            el,name=pair
            directory=tmp/f"{name}-{el}"
            directory.mkdir()
            row=run_case(directory,args.fd,setup,dt,regs,pc,el,name)
            print(el,name,row["panel"][0],flush=True)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(one, [(1,name) for name in CASES]+[(2,"free")]))
    args.report.write_text(json.dumps(dict(outcome="PASS-QEMU-HEAP4K",fdSha256=static["fdSha256"],
        physicalFdBus="UNKNOWN",qemu=subprocess.check_output(["qemu-system-aarch64","--version"],
        text=True).splitlines()[0],cases=rows),indent=2)+"\n")


if __name__=="__main__":
    main()
