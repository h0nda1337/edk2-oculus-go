"""Boot the Pacific LK bounce probe with *only* the LK page in the UFS DMA domain.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import os
import struct

from sec_mem_qemu import FB_BASE, RAM_START, SURFACE_BYTES, require
from ufs_data_fd_qemu import CAPACITY, CONTROL, LUN_BYTES, PAGE, TM, TR, WINDOW, board_guest, check_trace, main
from ufs_handoff_qemu import screen_oracle
from ufs_nop11_fd_qemu import run_cpu

GUID = "2eb661f1-f41a-41b8-b5d1-39b61bc1d720"

def expected_window(copied):
    pattern = bytearray((0x5a ^ (i >> 12) ^ i) & 255 for i in range(4*PAGE))
    for p in range(copied):
        pattern[p*PAGE:p*PAGE+8] = CAPACITY
    return bytes(pattern)

def bounce(tmp, fd, harness, dt, regs, pc, el, name):
    positive = name == "lk-only"
    size = LUN_BYTES if positive else LUN_BYTES-PAGE
    geometry = struct.pack(">II",size//PAGE-1,PAGE)
    samples = []
    snapshots = []
    with board_guest(tmp,fd,harness,dt,regs,el,lun_bytes=size,leaves=[]) as (g,ram,bus,trace):
        old = bus.read(TR & -PAGE,PAGE)
        def on_completion(device,count):
            require(count <= (5 if positive else 2), "excess DMA transactions")
            require(struct.unpack("<QII",device.read(TM+640+208,16))==(CONTROL,0,7) and
                    device.read(TM+640+16,16)==bytes([0x25])+bytes(15) and
                    device.read32(TR+32)==0x05000000 and device.read32(TR+32+8)==0,
                    "unexpected UTRD/PRDT/CDB/OCS")
            data = device.read(CONTROL,8)
            status = device.read(TM+640+128+7,1)[0]
            require((status,data)==((2,bytes([0xa5])*8) if count==1 else (0,geometry)),
                    "wrong device payload")
            # The CPU is halted just after the store to the doorbell. This page's
            # copy cannot have taken place yet, including when the device succeeded.
            already = max(0,count-2)
            require(device.read(WINDOW,4*PAGE)==expected_window(already), "private window changed during DMA")
            samples.append(dict(bus=hex(CONTROL),status=status,bytes=data.hex(),copiedBeforeCpuResumed=already))
        def before_restore(remote,device):
            count = 4 if positive else 0
            require(device.read(WINDOW,4*PAGE)==expected_window(count), "copy or guard mismatch")
            snapshots.append(count)
        rings = run_cpu(g,bus,pc,el,on_completion,before_restore)
        require(rings==(5 if positive else 2) and snapshots==[4 if positive else 0], "incomplete probe")
        top = ("UFS LK COPY".ljust(14)+"DONE") if positive else ("UFS STOP".ljust(14)+"CAPACITY")
        lines = [top,"LUN4 READ CAPACITY","COPY MASK "+("0000000F" if positive else "00000000"),
                 "OCS  00000000","SCSI 00000000","LAST "+geometry[:4].hex().upper(),
                 "SIZE 00001000","FD DIRECT UNTESTED"]
        screen_oracle(os.pread(ram,SURFACE_BYTES,FB_BASE-RAM_START),lines)
        require(bus.read(TR & -PAGE,PAGE)==old and bus.read(WINDOW,4*PAGE)==b"\xff"*(4*PAGE),
                "queue or window differs after restoration")
    check_trace(trace,rings)
    return dict(el=el,case=name,panel=lines,completions=samples,dmaPages=[hex(TR & -PAGE)],
                directWindowMappings=0,cpuCopies=snapshots[0],restored=True)

if __name__=="__main__":
    main(guid=GUID,checkpoint="RestoreBounceWindow",cases=("lk-only","wrong-geometry"),
         test=bounce,outcome="PASS-QEMU-FD-BOUNCE")
