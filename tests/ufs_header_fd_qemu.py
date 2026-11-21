"""Run the passive Pacific image or the GPT model against a real QEMU UFS device.
Private inputs stay in memory or a temporary read-only sparse LUN. No USB.
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
import zlib

from sec_mem_qemu import FB_BASE, RAM_START, ROOT, RUNTIME_SHA, SURFACE_BYTES, require, symbols, verify
from ufs_data_fd_qemu import CAPACITY, CONTROL, LUN_BYTES, PAGE, TM, TR, board_guest
from ufs_handoff_qemu import screen_oracle
from ufs_handoff_static import inspect
from ufs_nop11_fd_qemu import inspect_fd, run_cpu
from ufs_queues_qemu import ADDR, FINAL, QUEUE, REGS

BUF, SIZE_WORD = 0x918d7e80, 0x918e18d4
FIRST, SECOND = BUF & -PAGE, (BUF & -PAGE) + PAGE
SECTOR_SHA = "f8bfbc7cc9846c7f648f67e27f6d7552c05e00638dac852e18e9b310d6c88d50"
BOOT_SHA = "cde63f886a379f51d328d7c01a65884ead57bf3b295755f0303e19876ce754be"
PASSIVE_GUID = "1c8b508f-0679-471f-9036-91f6186a04af"
MODEL_GUID = "67abacac-0b70-444a-85da-cbf0aa919692"
PRDT = TM + 640 + 208
def sha(data):
    return hashlib.sha256(data).hexdigest()


def profile(fd, elf, passive):
    raw = fd.read_bytes()
    names = symbols(elf)
    bias = int(verify(raw)["secEntryAddress"], 16) - names["_ModuleEntryPoint"]
    pc = {key: bias + names[sym] for key, sym in
          (("entry","_ModuleEntryPoint"), ("load","GoUfsRead32"), ("stop","UfsStop"))}
    if passive:
        require(not ({"GoUfsRingNopSlot", "GoUfsModelReadPrimary", "GoUfsModelTransfer"} & names.keys()),
                "transport present in the passive SEC")
        audit = inspect(raw, elf, PASSIVE_GUID, {"mSamples":REGS, "mQueueRegs":QUEUE,
                        "mFinalRegs":[(ADDR[k],k,0) for k in FINAL]})
        audit["transportLinked"] = False
        pc["ring"] = -1
    else:
        audit = inspect_fd(raw, elf, MODEL_GUID)
        pc["ring"] = bias + names["GoUfsRingNopSlot"] + 12
    return pc, audit


def test_case(tmp, fd, setup, dt, regs, pc, passive, original, header, el, case):
    disk = None
    source = bytearray(header)
    if case == "bad-crc":
        source[16] ^= 1
    if case == "bad-geometry":
        struct.pack_into("<Q", source, 32, 0x11fffe)
        struct.pack_into("<I", source, 16, 0)
        struct.pack_into("<I", source, 16, zlib.crc32(source[:92]))
    if case == "bad-tail":
        source[-1] ^= 1
    if not passive:
        disk = tmp/"lun4.raw"
        with disk.open("xb") as stream:
            stream.truncate(LUN_BYTES)
            stream.seek(PAGE)
            stream.write(source)
        disk.chmod(0o400)
    if case == "unknown":
        original = bytes(PAGE)
    page_size = 2048 if case == "wrong-size" else PAGE
    prefix = bytes((i*17+11)&255 for i in range(BUF-FIRST))
    suffix = bytes((i*11+19)&255 for i in range(SECOND+PAGE-BUF-PAGE))
    initial = prefix + original + suffix
    transfers = []
    media = []
    leaves = [] if passive else [(FIRST,FIRST)]
    if not passive and case != "denied-second":
        leaves.append((SECOND,SECOND))

    with board_guest(tmp,fd,setup,dt,regs,el,leaves=leaves,readonly_disk=disk) as (g,ram,bus,trace):
        bus.write32(SIZE_WORD,page_size)
        bus.write(FIRST,initial)
        old_queue = bus.read(TR & -PAGE,PAGE)

        def completed(device, count):
            require(not passive, "passive SEC submitted an operation")
            cdb = device.read(TM+640+16,16)
            addr, reserved, length = struct.unpack("<QII", device.read(PRDT,16))
            status = device.read(TM+640+128+7,1)[0]
            ocs = device.read32(TR+32+8)
            require(reserved == 0 and device.read32(TR+32)==0x05000000, "unexpected data descriptor")
            event = dict(opcode=hex(cdb[0]), bus=hex(addr), bytes=length+1, ocs=ocs, scsi=status)
            block = cdb[0] == 0x28
            if block:
                require(cdb==bytes.fromhex("28000000000100000100")+bytes(6) and
                        (addr,length,status,ocs)==(BUF,PAGE-1,0,0), "unexpected READ(10)")
                data = device.read(BUF,PAGE)
                require(data == source, "full sector differs at DMA completion")
                require(device.read(FIRST,len(prefix))==prefix and device.read(BUF+PAGE,len(suffix))==suffix,
                        "DMA crossed block bounds")
                event["blockSha256"] = sha(data)
                media.append(event["blockSha256"])
            else:
                require(cdb==bytes([0x25])+bytes(15) and length==7 and
                        addr in (CONTROL,BUF,BUF+PAGE-8), "unexpected capacity request")
                sample = device.read(addr, 8)
                event["receivedHex"] = sample.hex()
                denied = case == "denied-second" and addr == BUF+PAGE-8
                if denied:
                    require(sample == bytes([0xa5])*8, "an unmapped page received data")
                elif status == 0 and ocs == 0:
                    require(sample == CAPACITY, "wrong capacity DMA")
            transfers.append(event)

        rings = run_cpu(g,bus,pc,el,completed)
        require(bus.read(FIRST,2*PAGE)==initial and bus.read(TR & -PAGE,PAGE)==old_queue,
                "LK workspace, guards or queues not restored")
        read_sector = not passive and case not in ("unknown","denied-second")
        if passive or case == "unknown":
            require(rings==0, "unexpected command")
        else:
            require([t["bus"] for t in transfers]==[hex(a) for a in
                    ([CONTROL,CONTROL,BUF,BUF+PAGE-8]+([BUF] if read_sector else []))],
                    f"unexpected DMA sequence {transfers}")
        require(len(media)==int(read_sector),"unexpected sector count")
        lines = ["","BUF  918D7E80",f"LKPG {page_size:08X}","OLD","","","","CPU ONLY"]
        if case == "wrong-size":
            state, label = "STOP","LKPG"
        else:
            lines[3] = f"OLD  {zlib.crc32(original):08X}"
            lines[4] = "OTHER" if case=="unknown" else "BOOT A"
            if passive:
                state,label = "BUF4K","DONE"
                lines[6] = "TWO SAMPLES MATCH"
            elif case=="unknown":
                state,label = "STOP","ORIGINAL"
            elif case=="denied-second":
                state,label = "STOP","CAPACITY"
                lines[4:] = ["ENDS 00000001","HCRC","FULL",""]
            else:
                calc = bytearray(source[:92]); calc[16:20]=bytes(4)
                state, label = {"valid":("GPT","DONE"),"bad-crc":("BAD GPT","CRC"),
                    "bad-geometry":("BAD GPT","GEOMETRY"),"bad-tail":("BAD GPT","BASELINE")}[case]
                lines[4:] = ["ENDS 00000003",f"HCRC {zlib.crc32(calc):08X}",
                             f"FULL {zlib.crc32(source):08X}","RAM RESTORED"]
        lines[0] = ("UFS "+state).ljust(14)+label
        screen_oracle(os.pread(ram,SURFACE_BYTES,FB_BASE-RAM_START),lines)
    events=trace.read_text().splitlines()
    expected=[f"ufs_exec_scsi_cmd slot 1, lun 0x4, opcode {t['opcode']}" for t in transfers]
    if media:
        expected.append("scsi_disk_dma_command_READ Read (sector 1, count 1)")
    require(len(events)==1+len(expected) and events[0].startswith("ufs_exec_nop_cmd ") and events[1:]==expected,
            f"unexpected UFS/SCSI/media access {events}")
    if disk:
        with disk.open("rb") as stream:
            stream.seek(PAGE)
            require(stream.read(PAGE)==source and disk.stat().st_size==LUN_BYTES,"backing changed")
    return dict(el=el,case=case,panel=lines,transfers=transfers,firmwareDoorbells=rings,
                gptSectorSha256=media,readExtents=[dict(lun=4,lba=1,blocks=1)] if media else [],
                mappedCandidateLeaves=[hex(a) for a,_ in leaves],mediaWrites=0,restored=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--passive",action="store_true")
    for name in ("fd","sec-elf","runtime-fdt","boot-a","gpt-header","report","static-report"):
        ap.add_argument("--"+name,type=Path,required=True)
    args=ap.parse_args()
    pc, audit=profile(args.fd,args.sec_elf,args.passive)
    args.static_report.write_text(json.dumps(audit,indent=2)+"\n")
    boot=args.boot_a.read_bytes()
    header=args.gpt_header.read_bytes()
    dt=args.runtime_fdt.read_bytes()
    require(sha(boot)==BOOT_SHA and sha(header)==SECTOR_SHA and len(header)==PAGE and sha(dt)==RUNTIME_SHA,
            "unexpected private evidence")
    capture=json.loads((ROOT/"docs/evidence/ufs-handoff-transfer-20261121.json").read_bytes())
    regs={k:int(v,16) for k,v in capture["physicalPanel"]["registersHex"].items()}
    regs.update(CAP=0x0107001f,TRL=TR,TRH=0,TML=TM,TMH=0)
    cases=[(1,"valid"),(2,"valid")]
    cases.extend((1,name) for name in (("unknown","wrong-size") if args.passive else
                                       ("unknown","bad-crc","bad-geometry","bad-tail","denied-second")))
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder)
        setup=tmp/"entry.bin"
        subprocess.run(["aarch64-linux-gnu-gcc","-c",ROOT/"tests/entry_harness.S","-o",tmp/"entry.o"],check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy","-O","binary",tmp/"entry.o",setup],check=True)
        def one(pair):
            el,name=pair
            case_dir=tmp/f"{el}-{name}"; case_dir.mkdir()
            row=test_case(case_dir,args.fd,setup,dt,regs,pc,args.passive,boot[:PAGE],header,el,name)
            print(el,name,row["panel"][0],flush=True)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(one,cases))
    report=dict(outcome="PASS-QEMU-BUF4K" if args.passive else "PASS-QEMU-GPT-READ",
                fdSha256=audit["fdSha256"],qemu=subprocess.check_output(["qemu-system-aarch64","--version"],
                text=True).splitlines()[0],capturedHeaderSha256=SECTOR_SHA,candidate=hex(BUF),
                bytes=PAGE,physicalGptRead="UNKNOWN",cases=rows)
    args.report.write_text(json.dumps(report,indent=2)+"\n")

if __name__=="__main__":
    main()
