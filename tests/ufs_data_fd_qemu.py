"""Boot the packaged SEC binary and observe data written by the virtual UFS controller.
The translated case supplies QEMU's own map at the C ABI boundary in the debugger.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from contextlib import contextmanager
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

from sec_mem_qemu import (BASE, FDT, FB_BASE, RAM_START, ROOT, RUNTIME_SHA, SURFACE_BYTES,
                          guest, require, symbols, verify)
from ufs_data_qemu import CAPACITY, LUN_BYTES, unit_args
from ufs_handoff_qemu import screen_oracle
from ufs_lk_map_qemu import L1
from ufs_nop11_bus import BAR, IOVA, PAGE, TM, TR, WINDOW
from ufs_nop11_fd_qemu import inspect_fd, run_cpu, setup_bus
from ufs_queue_dma_model import Bus
from ufs_queues_qemu import ADDR

GUID = "28b403d4-daca-48ec-a821-683f1404c003"
CONTROL = TM + 640 + 256
OFFSETS = [0, 2*PAGE-8, 2*PAGE, 4*PAGE-8]

@contextmanager
def board_guest(tmp, fd, harness, dt, regs, el, lun_bytes=LUN_BYTES, leaves=None, readonly_disk=None):
    flash = tmp/"board"
    with flash.open("wb") as stream:
        stream.truncate(64 << 20)
        for name, value in regs.items():
            stream.seek(ADDR[name])
            stream.write(struct.pack("<I", value))
    trace, events, sock = tmp/"trace", tmp/"events", tmp/"qtest"
    events.write_text("ufs_exec_nop_cmd\nufs_exec_scsi_cmd\nufs_exec_query_cmd\n"
                      "scsi_disk_dma_command_READ\nscsi_disk_dma_command_WRITE\n")
    unit = unit_args(lun_bytes) if readonly_disk is None else [
        "-blockdev", f"driver=file,node-name=source,filename={readonly_disk},read-only=on",
        "-blockdev", "driver=raw,node-name=lun4,file=source,read-only=on",
        "-device", "ufs-lu,drive=lun4,lun=4"]
    extra = ["-machine", "highmem=off,iommu=smmuv3", "-drive",
             f"if=pflash,index=0,file={flash},format=raw,readonly=on", "-device", "ufs,addr=1.0,mcq=off",
             *unit, "-qtest", f"unix:{sock},server=on,wait=off", "-qtest-log", "/dev/null",
             "-trace", f"events={events},file={trace}"]
    with guest(fd, harness, el, BASE, extra) as (g, ram), socket.socket(socket.AF_UNIX) as conn:
        for _ in range(100):
            if sock.exists():
                break
            time.sleep(0.02)
        conn.connect(str(sock))
        with conn.makefile("rwb", buffering=0) as stream:
            bus = Bus(SimpleNamespace(stdin=stream, stdout=stream))
            setup_bus(bus, leaves)
            os.pwrite(ram, dt, FDT-RAM_START)
            for address, value in ((L1,0x918e5003),(L1+4,0),(0x918e5010,0x80400451),
                                   (0x918e5014,0x00400000),(0x918e5460,0x91800451),(0x918e5464,0)):
                bus.write32(address, value)
            yield g, ram, bus, trace

def check_trace(trace, rings):
    events = trace.read_text().splitlines()
    require(events.count("ufs_exec_nop_cmd slot 0")==1 or sum("ufs_exec_nop_cmd" in e for e in events)==1,
            "unexpected fixture NOP count")
    require(sum(e=="ufs_exec_scsi_cmd slot 1, lun 0x4, opcode 0x25" for e in events)==rings and
            len(events)==1+rings, f"unexpected UFS or disk operation: {events}")

def test_image(tmp, fd, harness, dt, regs, pc, el, translated):
    completions = []
    with board_guest(tmp, fd, harness, dt, regs, el) as (g,ram,bus,trace):
        old = bus.read(TR & -PAGE, PAGE)
        def map_entry(remote, device):
            require(remote.register(0) == 0, "Pacific supplied an unverified DMA address")
            if translated:
                # Host test fixture only. The same FD runs unchanged in both cases.
                addr = 0x40208000
                device.write(addr, struct.pack("<4Q", *(IOVA+p*PAGE for p in range(4))))
                remote.set_register(0, addr)

        def observe(device, count):
            require(count <= (6 if translated else 2), "unexpected submission")
            target = CONTROL if count <= 2 else WINDOW + OFFSETS[count-3]
            expected_bus = CONTROL if count <= 2 else IOVA + OFFSETS[count-3]
            descriptor = device.read32(TR+32)
            cdb = device.read(TM+640+16, 16)
            prd = struct.unpack("<QII", device.read(TM+640+208,16))
            require(descriptor == 0x05000000 and cdb == bytes([0x25])+bytes(15) and
                    prd == (expected_bus,0,7), "unexpected data-in request")
            require(device.read32(TR+32+8) == 0, "controller OCS")
            data = device.read(target,8)
            status = device.read(TM+640+128+7,1)[0]
            require((status,data)==((2,bytes([0xa5])*8) if count==1 else (0,CAPACITY)),
                    f"independent DMA observation {count} {status} {data.hex()}")
            completions.append(dict(cpu=hex(target),bus=hex(expected_bus),status=status,bytes=data.hex()))
        rings = run_cpu(g, bus, pc, el, observe, map_entry)
        require(rings==(6 if translated else 2), "missing completions")
        heading = "UFS FD DATA" if translated else "UFS LK DATA"
        lines = [heading.ljust(14)+"DONE","LUN4 READ CAPACITY",
                 "PAGE MASK "+("0000000F" if translated else "00000000"),
                 "OCS  00000000","SCSI 00000000","LAST 0011FFFF","SIZE 00001000",
                 "WINDOW RESTORED" if translated else "WINDOW DMA UNTESTED"]
        screen_oracle(os.pread(ram,SURFACE_BYTES,FB_BASE-RAM_START),lines)
        require(bus.read(TR & -PAGE,PAGE)==old and bus.read(WINDOW,4*PAGE)==b"\xff"*(4*PAGE),
                "queue allocation or FD window changed")
    check_trace(trace,rings)
    return dict(el=el,case="qemu-map" if translated else "pacific-entry",panel=lines,
                completions=completions,restored=True)

def main(guid=GUID, checkpoint="GoUfsDataWindow", cases=(False,True), test=test_image, outcome="PASS-QEMU-FD-DATA"):
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("fd","sec-elf","runtime-fdt","report","static-report"):
        ap.add_argument("--"+flag, type=Path, required=True)
    args = ap.parse_args()
    data = args.fd.read_bytes()
    audit = inspect_fd(data,args.sec_elf,guid)
    args.static_report.write_text(json.dumps(audit,indent=2)+"\n")
    entry = int(verify(data)["secEntryAddress"],16)
    sym = symbols(args.sec_elf)
    bias = entry - sym["_ModuleEntryPoint"]
    pc = dict(entry=entry,stop=bias+sym["UfsStop"],ring=bias+sym["GoUfsRingNopSlot"]+12,
              load=bias+sym["GoUfsRead32"],window=bias+sym[checkpoint])
    dt = args.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest()==RUNTIME_SHA, "wrong runtime DT")
    panel = json.loads((ROOT/"docs/evidence/ufs-handoff-transfer-20261121.json").read_bytes())["physicalPanel"]
    regs = {k:int(v,16) for k,v in panel["registersHex"].items()} | dict(CAP=0x0107001f,TRL=TR,TRH=0,TML=TM,TMH=0)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        subprocess.run(["aarch64-linux-gnu-gcc","-c",ROOT/"tests/entry_harness.S","-o",tmp/"entry.o"],check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy","-O","binary",tmp/"entry.o",tmp/"entry.bin"],check=True)
        rows = []
        for el in (1,2):
            for mapped in cases:
                folder=tmp/f"{el}-{mapped}"
                folder.mkdir()
                rows.append(test(folder,args.fd,tmp/"entry.bin",dt,regs,pc,el,mapped))
                print(el,rows[-1]["case"],rows[-1]["panel"][0],flush=True)
    args.report.write_text(json.dumps(dict(outcome=outcome,fdSha256=hashlib.sha256(data).hexdigest(),
          qemu=subprocess.check_output(["qemu-system-aarch64","--version"],text=True).splitlines()[0],
          physicalWindowDma="UNKNOWN",mediaReads=0,mediaWrites=0,cases=rows),indent=2)+"\n")

if __name__=="__main__":
    main()
