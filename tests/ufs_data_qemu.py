"""Run the ARM64 data-in probe with real PCI UFS, PRDT and SMMUv3 translations.
No disk contents or headset access. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from ufs_lk_nop_qemu import BAR, BOX, MACHINE, TR, check, controller, start_cpu
from ufs_nop11_bus import IOVA, PAGE, WINDOW, seed_lk, set_translation

ROOT = Path(__file__).resolve().parents[1]
LUN_BYTES = 4831838208
CAPACITY = bytes.fromhex("0011ffff00001000")
CASES = {
    "translated": ("FD DATA", "DONE", 15),
    "scattered": ("FD DATA", "DONE", 15),
    "aliased-target": ("HOLD", "FD GUARD", 3),
    "last-page-denied": ("STOP", "CAPACITY", 7),
    "no-window-map": ("LK DATA", "DONE", 0),
    "alias-list": ("STOP", "DMA ALIAS", 0),
    "partial-map": ("STOP", "DMA MAP", 0),
    "dirty-window": ("STOP", "FD DIRTY", 0),
    "wrong-geometry": ("STOP", "CAPACITY", 0),
    "wrong-iova": ("STOP", "CAPACITY", 0),
}

def unit_args(size):
    return ["-blockdev", f"driver=null-co,node-name=capacity,size={size},read-only=on",
            "-device", "ufs-lu,drive=capacity,lun=4"]

def compile_guest(tmp):
    entry = tmp / "entry.S"
    entry.write_text(".text\n.global _start\n_start:\n ldr x0, =0x40210000\n mov sp,x0\n b run_guest\n")
    sec = ROOT / "OculusGoPkg/SecMem"
    inc = ROOT / "edk2/MdePkg/Include"
    elf = tmp / "guest.elf"
    subprocess.run(["aarch64-linux-gnu-gcc", "-nostdlib", "-static", "-ffreestanding", "-fshort-wchar",
                    "-mgeneral-regs-only", "-mstrict-align", "-fno-stack-protector", "-O2", "-Werror",
                    "-DGO_UFS_DATA", "-DGO_UFS_QUEUES", "-I", inc, "-I", inc/"AArch64",
                    "-Wl,-Ttext=0x40200000,--build-id=none,--strip-all", entry,
                    ROOT/"tests/ufs_data_guest.c", sec/"UfsData.c", sec/"UfsNop11.c", "-o", elf], check=True)
    return elf

def run_case(tmp, elf, name):
    machine = [arg.replace("1280M","1536M").replace("virt,highmem=off","virt,highmem=off,iommu=smmuv3")
               for arg in MACHINE]
    extra = ["-device", f"loader,file={elf},cpu-num=0","-qmp", f"unix:{tmp/'ctl'},server=on,wait=off"]
    size = LUN_BYTES - PAGE if name == "wrong-geometry" else LUN_BYTES
    guards = bytes([0x36]) * PAGE
    with controller(tmp, 0x3f000000, BAR, machine=machine, extra=extra, units=unit_args(size)) as bus:
        pages = [IOVA+i*(2 if name=="scattered" else 1)*PAGE for i in range(4)]
        leaves = [(address, WINDOW+i*PAGE) for i,address in enumerate(pages)]
        if name == "aliased-target": leaves[2] = (pages[2], WINDOW)
        if name == "last-page-denied": leaves.pop()
        set_translation(bus, leaves)
        seed_lk(bus)
        original = bus.read(TR & -PAGE, PAGE)
        for i in range(-1, 5):
            bus.write(WINDOW+i*PAGE, guards if i in (-1,4) else b"\xff"*PAGE)
            bus.write(IOVA+i*PAGE, guards)
        if name == "dirty-window":
            bus.write(WINDOW+4*PAGE-1,b"\x00")
        if name == "alias-list": pages[2] = pages[1]
        if name == "partial-map": pages[3] = 0
        if name == "wrong-iova": pages[0] = WINDOW
        bus.write(BOX, struct.pack("<28I", int(name != "no-window-map"), *([0]*23), *pages))
        start_cpu(tmp/"ctl")
        bus.wait_bits(BOX+4, 0xffffffff, 0x444f4e45)
        box = bus.read(BOX,112)
        state, label = [piece.split(b"\0")[0].decode() for piece in (box[64:80],box[80:96])]
        words = struct.unpack("<28I",box)
        expected = CASES[name]
        if name == "wrong-iova":
            check((state,label) in {("STOP","CAPACITY"),("HOLD","TIMEOUT")} and words[6]==0,
                  f"unmapped IOVA appeared to work: {state} {label}")
        else:
            check((state,label,words[6]) == expected, f"{name}: {state} {label} {words[2:11]} {bus.read(BOX+128,64).hex()}")
        if label != "TIMEOUT":
            check(bus.read(TR & -PAGE, PAGE) == original, "LK allocation changed")
        check(all(bus.read(IOVA+i*PAGE,PAGE)==guards for i in range(-1,5)),"numeric alias modified")
        check(all(bus.read(WINDOW+i*PAGE,PAGE)==guards for i in (-1,4)),"outside guards modified")
        if state != "HOLD":
            target = bytearray([255])*(4*PAGE)
            if name=="dirty-window": target[-1]=0
            check(bus.read(WINDOW,len(target))==target, "window differs on return")
        if name == "aliased-target":
            check(bus.read(WINDOW,8)==CAPACITY and bus.read(WINDOW+2*PAGE,8)==bytes([0xa5])*8,
                  "aliased page did not receive the device payload")
        count = words[2]
        records = list(struct.iter_unpack("<5I", bus.read(BOX+192,20*count)))
        check(count <= 8 and all((hi,length,descriptor,cdb)==(0,7,0x05000000,0x25)
                                 for _,hi,length,descriptor,cdb in records), "unexpected PRDT or command")
        destinations=[lo for lo,_,_,_,_ in records]
        control = 0x918eee80 + 256
        check(destinations[:2] == [control]*2, "expected unit attention and one control retry")
        window_destinations = [addr + (PAGE-8 if i%2 else 0) for i,addr in enumerate(pages)]
        check(destinations[2:] == window_destinations[:count-2],"unreviewed data destination")
        check(bus.read32(BAR+0x50)==TR and bus.read32(BAR+0x60)==1, "queue moved or stopped")
    trace = (tmp/"ufs.trace").read_text()
    commands=re.findall(r"ufs_exec_scsi_cmd[^\n]+",trace)
    check(len(commands)==words[2] and all(line == "ufs_exec_scsi_cmd slot 1, lun 0x4, opcode 0x25" for line in commands),repr(commands))
    check("ufs_exec_query_cmd" not in trace and "scsi_disk_dma_command_READ" not in trace and
          "scsi_disk_dma_command_WRITE" not in trace,"unexpected management command or media I/O")
    return dict(case=name,state=state,label=label,pageMask=words[6],submissions=words[2],
                ocs=words[7],scsiStatus=words[8],lastLba=words[9],blockSize=words[10],
                prdtBusAddresses=[hex(a) for a in destinations])

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        elf=compile_guest(tmp)
        rows=[]
        for name in CASES:
            folder=tmp/name
            folder.mkdir()
            rows.append(run_case(folder,elf,name))
            print(rows[-1],flush=True)
        a.report.write_text(json.dumps(dict(outcome="PASS-QEMU-DATA-IN",cpuWindow=hex(WINDOW),
             virtualBusBase=hex(IOVA),windowBytes=4*PAGE,probeBytesPerPage=8,
             virtualGuestSha256=hashlib.sha256(elf.read_bytes()).hexdigest(),lun=4,mediaReads=0,
             mediaWrites=0,physicalWindowDma="UNKNOWN",cases=rows),indent=2)+"\n")

if __name__ == "__main__":
    main()
