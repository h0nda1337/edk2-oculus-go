"""Exercise the production NOP engine using nonidentity DMA on a real virtual SMMU.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from ufs_lk_nop_qemu import start_cpu, check, MACHINE, controller, TR, BAR, BOX
from ufs_nop11_bus import WINDOW, IOVA, PAGE, set_translation, seed_lk

ROOT = Path(__file__).resolve().parents[1]

def run_case(tmp, elf, case, page):
    machine = [v.replace("1280M", "1536M").replace("virt,highmem=off","virt,highmem=off,iommu=smmuv3")
               for v in MACHINE]
    extra = ["-device", f"loader,file={elf},cpu-num=0", "-qmp", f"unix:{tmp/'ctl'},server=on,wait=off"]
    with controller(tmp, 0x3f000000, BAR, machine=machine, extra=extra) as bus:
        set_translation(bus)
        seed_lk(bus)
        old = bus.read(TR & -PAGE, PAGE)
        pattern = bytes((i*17+123)&255 for i in range(PAGE))
        for at in range(-1,5):
            bus.write(WINDOW+at*PAGE, pattern)
            bus.write(IOVA+at*PAGE, pattern[::-1])
        va = {"missing-map":0, "wrong-identity":WINDOW}.get(case, IOVA)
        bus.write(BOX, struct.pack("<10I", va,4*PAGE,page,*([0]*7)))
        start_cpu(tmp/"ctl")
        try:
            bus.wait_bits(BOX+12, 0xffffffff, 0x444f4e45)
        except RuntimeError as exc:
            import socket
            with socket.socket(socket.AF_UNIX) as sock:
                sock.connect(str(tmp/"ctl"))
                with sock.makefile("rwb",buffering=0) as io:
                    io.readline()
                    for msg in [{"execute":"qmp_capabilities"},{"execute":"human-monitor-command","arguments":{"command-line":"info registers"}}]:
                        io.write(json.dumps(msg).encode()+b"\n")
                        print(io.readline().decode(),flush=True)
            raise RuntimeError(f"guest mailbox {bus.read(BOX,40).hex()}, DBR {bus.read32(BAR+0x58):#x}, trace {(tmp/'ufs.trace').read_text()[-250:]}") from exc
        status = struct.unpack("<10I", bus.read(BOX,40))
        final = chr(status[4]) + chr(status[5])
        real_tag = 0x01000020
        if case == "translated":
            check(final == "ND" and status[6:] == (1,0,real_tag,1), f"positive: {status}")
        elif case == "missing-map":
            check(final == "SD" and not any(status[6:]), f"missing map: {status}")
        else:
            # The model can retire the slot with error or hold it pending.
            check(final in ("BR","HT") and status[6]==1 and status[8]!=real_tag, f"denied: {status}")
        check(all(bus.read(IOVA+n*PAGE,PAGE)==pattern[::-1] for n in range(-1,5)), "numeric alias modified")
        for n in range(-1,5):
            observed = bus.read(WINDOW+n*PAGE,PAGE)
            if case == "wrong-identity" and final == "HT" and n == page:
                wanted = bytearray(pattern)
                wanted[-256:-224] = bytes([0,0,0,1])+bytes(28)
                wanted[-128:-96] = bytes([0xa5])*32
                check(observed == wanted,"denied buffer outside expected image")
            else:
                check(observed == pattern,"window/guard mismatch")
        if final != "HT":
            check(bus.read(TR & -PAGE,PAGE)==old,"queues differ after restore")
        else:
            check(bus.read32(BAR+0x58)==2,"pending queue lost")
    trace=(tmp/"ufs.trace").read_text()
    count=trace.count("ufs_exec_nop_cmd")
    check("ufs_exec_scsi_cmd" not in trace and "ufs_exec_query_cmd" not in trace, "unexpected command")
    if case != "wrong-identity":
        check(count == (2 if case=="translated" else 1),"unexpected NOP count")
    return dict(case=case,page=page,descriptorDma=hex(va+page*PAGE+PAGE-256) if va else None,
                cpuResponse=hex(WINDOW+page*PAGE+PAGE-128),doorbells=status[6],result=final,
                ocs=status[7] if status[9] else None,response=hex(status[8]) if status[9] else None,
                restored=bool(status[9]),nopsIncludingSeed=count)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report",type=Path,required=True)
    a=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        elf=tmp/"guest.elf"
        entry=tmp/"entry.S"
        entry.write_text(".text\n.global _start\n_start:\n ldr x0, =0x40210000\n mov sp,x0\n b run_guest\n")
        inc=ROOT/"edk2/MdePkg/Include"
        subprocess.run(["aarch64-linux-gnu-gcc","-nostdlib","-static","-ffreestanding","-mgeneral-regs-only","-mstrict-align",
                        "-fno-stack-protector","-fshort-wchar","-O2","-Werror","-DGO_UFS11_VIRTUAL_MAP","-DGO_UFS_QUEUES",
                        "-I",inc,"-I",inc/"AArch64","-Wl,-Ttext=0x40200000,--build-id=none",entry,
                        ROOT/"tests/ufs_nop11_window_guest.c",ROOT/"OculusGoPkg/SecMem/UfsNop11.c","-o",elf],check=True)
        rows=[]
        for case,page in [("translated",n) for n in range(4)]+[("wrong-identity",0),("missing-map",0)]:
            folder=tmp/f"{case}-{page}"
            folder.mkdir()
            rows.append(run_case(folder,elf,case,page))
            print(case,page,rows[-1]["result"],flush=True)
        a.report.write_text(json.dumps(dict(outcome="PASS-QEMU-TRANSLATED-NOP11",ordinaryLuns=0,
                guestSha256=hashlib.sha256(elf.read_bytes()).hexdigest(),pacificWindowDma="UNKNOWN",
                modelIova=hex(IOVA),cpuPa=hex(WINDOW),bytes=4*PAGE,cases=rows),indent=2)+"\n")

if __name__ == "__main__":
    main()
