"""Boot the exact Pacific FD at EL1/EL2. Replay board status, bridge DBR to PCI UFS.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace

from sec_mem_qemu import (ROOT, BASE, FDT, FB_BASE, RAM_START, RUNTIME_SHA, SURFACE_BYTES,
                          guest, require, symbols, until, verify, watch)
from ufs_handoff_qemu import screen_oracle
from ufs_handoff_static import inspect
from ufs_queues_qemu import ADDR, FINAL, QUEUE, REGS
from ufs_lk_map_qemu import L1
from ufs_nop11_bus import seed_lk, set_translation, HBA, TR, TM, WINDOW, PAGE, BAR
from ufs_queue_dma_model import Bus

GUID = "c965ead6-00b2-46b9-a899-324437c63682"
HCI = 0x624000
CASES = {"nop":("NOP IN","DONE"), "bad-tag":("BAD","RESPONSE"),
         "software-busy":("STOP","STATE"), "empty-prior":("STOP","NO PRIOR OCS"),
         "different-cpu-map":("UNKNOWN","FD MAP")}

def inspect_fd(fd, elf, guid=GUID):
    report = inspect(fd,elf,guid,{"mSamples":REGS,"mQueueRegs":QUEUE,
                    "mFinalRegs":[(ADDR[k],k,0) for k in FINAL]})
    sym = symbols(elf)
    entry = int(verify(fd)["secEntryAddress"],16)
    pos = entry - sym["_ModuleEntryPoint"] + sym["GoUfsRingNopSlot"] - BASE
    words = struct.unpack_from("<6I",fd,pos)
    require(words[0] & 0xff00001f == 0x58000000 and words[1:] ==
            (0x52800041,0xd5033f9f,0xb9000001,0xd5033f9f,0xd65f03c0),"doorbell store changed")
    require(struct.unpack_from("<Q",fd,pos+((words[0]>>5)&0x7ffff)*4)[0] == HCI+0x58,"doorbell literal")
    require("GoUfsModelWindowNop" not in sym and fd[WINDOW-BASE:WINDOW-BASE+4*PAGE] == b"\xff"*(4*PAGE),
            "window or hardware entry changed")
    return report | {"registerStore":"0x624058","value":2,**({"windowSubmission":False} if guid == GUID else {})}

def setup_bus(bus):
    cfg = 0x3f000000+(1<<15)
    require(bus.read32(cfg+8)>>8 == 0x010901,"PCI class")
    bus.write32(cfg+0x10,BAR)
    bus.write32(cfg+0x14,0)
    bus.command(f"writew {cfg+4:#x} 6")
    bus.write32(BAR+0x34,1)
    bus.wait_bits(BAR+0x30,8,8)
    bus.write32(BAR+0x90,0x16)
    bus.wait_bits(BAR+0x30,15,15)
    set_translation(bus)
    seed_lk(bus)

def run_cpu(g, bus, pc, el, after_ring, at_window=None):
    rings = 0
    for cmd in ("qSupported:qXfer:features:read+","qXfer:features:read:target.xml:0,fff","Hg0","?"):
        g.command(cmd)
    g.set_register(33,0x3c9 if el==2 else 0x3c5)
    g.set_register(0,FDT)
    g.set_register(18,0)
    g.set_register(20,BASE)
    g.set_register(32,0x41000000+(64 if el==2 else 0))
    until(g,pc["entry"])
    if at_window is not None:
        require(g.command(f"Z1,{pc['window']:x},4") == "OK", "window entry breakpoint")
    # Reads from physical clocks, CAP, VER, HCS and TMR use recorded board inputs.
    # Bridge other HCI words to the real PCI device. All guest peripheral writes trap.
    watch(g,2,0x300000,0x390000)
    watch(g,4,HCI,HCI+0x2500)
    require(g.command(f"Z1,{pc['stop']:x},4")=="OK","stop bp")
    while True:
        msg=g.command("c")
        addr,insn=g.register(0),g.register(32)
        if at_window is not None and insn == pc['window']:
            require(g.command(f"z1,{insn:x},4") == "OK", "remove window breakpoint")
            at_window(g, bus)
            continue
        if insn==pc["stop"]:
            break
        require("watch:" in msg and HCI<=addr<HCI+0x2500,"unreviewed board access")
        off=addr-HCI
        if insn==pc["ring"]:
            require(off==0x58 and g.register(1)==2,"unreviewed store")
            rings+=1
        else:
            require(insn==pc["load"],f"unknown MMIO PC {insn:#x}")
        watch(g,4,HCI,HCI+0x2500,False)
        if off not in (0,8,0x30,0x80):
            g.set_register(0,BAR+off)
        require(g.command("s").startswith(("S","T")),"single step")
        if insn==pc["ring"]:
            bus.wait_bits(BAR+0x58,2,0)
            after_ring(bus, rings)
        watch(g,4,HCI,HCI+0x2500)
    return rings

def run_case(tmp,fd,setup,dt,regs,pc,el,name):
    rom = tmp/"regs.rom"
    with rom.open("wb") as io:
        io.truncate(64<<20)
        for k,v in regs.items():
            io.seek(ADDR[k])
            io.write(struct.pack("<I",v))
    events,trace,sock = tmp/"events",tmp/"trace",tmp/"qtest"
    events.write_text("ufs_exec_nop_cmd\nufs_exec_scsi_cmd\nufs_exec_query_cmd\n")
    extra = ["-machine","highmem=off,iommu=smmuv3","-drive",f"if=pflash,index=0,file={rom},format=raw,readonly=on",
             "-device","ufs,addr=1.0,mcq=off","-qtest",f"unix:{sock},server=on,wait=off","-qtest-log","/dev/null",
             "-trace",f"events={events},file={trace}"]
    rings=0
    with guest(fd,setup,el,BASE,extra) as (g,ram), socket.socket(socket.AF_UNIX) as s:
        for _ in range(100):
            if sock.exists():
                break
            time.sleep(0.02)
        s.connect(str(sock))
        with s.makefile("rwb",buffering=0) as io:
            bus=Bus(SimpleNamespace(stdin=io,stdout=io))
            setup_bus(bus)
            os.pwrite(ram, dt, FDT-RAM_START)
            for addr,val in ((L1,0x918e5003),(L1+4,0),(0x918e5010,0x80600451 if name=="different-cpu-map" else 0x80400451),
                             (0x918e5014,0x00400000),(0x918e5460,0x91800451),(0x918e5464,0)):
                bus.write32(addr,val)
            if name=="software-busy":
                bus.write32(HBA+0x170,1)
            if name=="empty-prior":
                bus.write(TR,bytes(32))
            old=bus.read(TR & -PAGE,PAGE)
            def nop_complete(bus, count):
                require(count == 1 and bus.read32(TR+32+8) == 0 and
                        bus.read32(TM+640+128) == 0x01000020, "device NOP IN")
                if name == "bad-tag":
                    bus.write32(TM+640+128, 0x02000020)
            rings = run_cpu(g, bus, pc, el, nop_complete)
            state,label=CASES[name]
            lines=[("UFS "+state).ljust(14)+label]
            if name in ("nop","bad-tag"):
                lines+=["TAG 01  CT 02","UCD 918EEE80","UTR 918EE420","OCS 00000000",
                        "RSP "+("01000020" if name=="nop" else "02000020"),"RAM RESTORED","FD DMA UNTESTED"]
            screen_oracle(os.pread(ram,SURFACE_BYTES,FB_BASE-RAM_START),lines)
            require(rings==int(name in ("nop","bad-tag")),"ring count")
            require(bus.read(TR & -PAGE,PAGE)==old and bus.read(WINDOW,4*PAGE)==b"\xff"*(4*PAGE),"changed queues or FD")
            for off,value in ((0x50,TR),(0x54,0),(0x70,TM),(0x74,0),(0x60,1),(0x58,0),(0x78,0),(0x34,1)):
                require(bus.read32(BAR+off)==value,"HCI differs after NOP")
    log=trace.read_text()
    require(log.count("ufs_exec_nop_cmd")==rings+1 and "ufs_exec_scsi_cmd" not in log and
            "ufs_exec_query_cmd" not in log,"unexpected UFS transaction")
    return dict(el=el,case=name,state=state,label=label,guestDoorbells=rings,lkPageRestored=True,fdWindowUnchanged=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ("fd","sec-elf","runtime-fdt","report","static-report"):
        ap.add_argument("--"+key,required=True,type=Path)
    a=ap.parse_args()
    fd=a.fd.read_bytes()
    a.static_report.write_text(json.dumps(inspect_fd(fd,a.sec_elf),indent=2)+"\n")
    entry=int(verify(fd)["secEntryAddress"],16)
    sym=symbols(a.sec_elf)
    bias=entry-sym["_ModuleEntryPoint"]
    pc=dict(entry=entry,stop=bias+sym["UfsStop"],ring=bias+sym["GoUfsRingNopSlot"]+12,load=bias+sym["GoUfsRead32"])
    dt=a.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest()==RUNTIME_SHA,"wrong DT")
    recorded=json.loads((ROOT/"docs/evidence/ufs-handoff-transfer-20261121.json").read_bytes())["physicalPanel"]
    regs={k:int(v,16) for k,v in recorded["registersHex"].items()} | dict(CAP=0x0107001f,TRL=TR,TRH=0,TML=TM,TMH=0)
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        subprocess.run(["aarch64-linux-gnu-gcc","-c",ROOT/"tests/entry_harness.S","-o",tmp/"entry.o"],check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy","-O","binary",tmp/"entry.o",tmp/"entry.bin"],check=True)
        rows=[]
        for el in (1,2):
            for name in CASES:
                folder=tmp/f"{el}-{name}"
                folder.mkdir()
                rows.append(run_case(folder,a.fd,tmp/"entry.bin",dt,regs,pc,el,name))
                print(el,name,flush=True)
        a.report.write_text(json.dumps(dict(outcome="PASS-QEMU-FD-NOP11",fdSha256=hashlib.sha256(fd).hexdigest(),
            physicalWindowDma="UNKNOWN",qemu=subprocess.check_output(["qemu-system-aarch64","--version"],text=True).splitlines()[0],
            ordinaryLuns=0,scsiCommands=0,queryCommands=0,cases=rows),indent=2)+"\n")

if __name__=="__main__":
    main()
