"""Run the packaged Pacific SEC on QEMU, checking each retained-LK load.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from sec_mem_qemu import (ROOT, BASE, FDT, FB_BASE, RAM_START, RUNTIME_SHA, SURFACE_BYTES,
                          guest, require, symbols, until, verify, watch)
from ufs_handoff_qemu import RANGES, screen_oracle
from ufs_queues_qemu import ADDR, SEQ
from ufs_handoff_static import inspect
from ufs_queues_qemu import REGS, QUEUE, FINAL, WINDOW, WINDOW_SIZE

GUID = "64982274-3dc2-429a-ae32-238e3b72362a"
HBA, L1, TR, TM = 0x918e3230, 0x918e4010, 0x918ee400, 0x918eec00
CONTEXT = [HBA + off for off in (4, 0x178, 0x17c, 0x1b8, 0x1bc)]
HCI = [0x624050, 0x624054, 0x624070, 0x624074]
CASES = {
    "identity-5000": ("LK MAP", "MATCH"), "identity-6000": ("LK MAP", "MATCH"),
    "identity-7000": ("LK MAP", "MATCH"), "changed-context": ("MISMATCH", "HBA"),
    "high-queue": ("MISMATCH", "HBA"), "foreign-table": ("UNKNOWN", "L1"),
    "foreign-table-high": ("UNKNOWN", "L1"), "empty-leaf": ("UNKNOWN", "FD MAP"),
    "fd-alias": ("UNKNOWN", "FD MAP"), "heap-alias": ("UNKNOWN", "LK MAP"),
    "above-4g": ("UNKNOWN", "FD MAP"), "unstable-leaf": ("CHANGED", "LK"),
    "changed-hci": ("CHANGED", "HCI"), "busy-before-map": ("BUSY", "TRD"),
    "cpu-window-dirty": ("DIRTY", "FD")
}


def inspect_fd(fd, elf):
    result = inspect(fd, elf, GUID, {"mSamples": REGS, "mQueueRegs": QUEUE,
                     "mFinalRegs": [(ADDR[k], k, 0) for k in FINAL]})
    require(fd[WINDOW-BASE:WINDOW-BASE+WINDOW_SIZE] == b"\xff" * WINDOW_SIZE,
            "candidate not entirely in blank FD")
    return result | {"windowCpuPa": hex(WINDOW), "windowBytes": WINDOW_SIZE}


def exercise(fd, harness, flash, dt, pc, el, case, regs):
    table = {"identity-6000": 0x918e6000, "identity-7000": 0x918e7000}.get(case, 0x918e5000)
    # Test data is synthetic. Only stock code and a physical run can identify
    # the actual allocator choice, table attributes and retained context.
    words = [0x624000, TR, 0, TM, 0, table | 3, 0, 0x80400451, 0x00400000, 0x91800451, 0]
    edits = {"changed-context": (1, TR+1024), "high-queue": (4, 1),
             "foreign-table": (5, 0x90500003), "foreign-table-high": (6, 1),
             "empty-leaf": (7, 0), "fd-alias": (7, 0x80600451),
             "above-4g": (8, 0x00400001), "heap-alias": (9, 0x91a00451)}
    if case in edits:
        index, value = edits[case]
        words[index] = value
    fields = CONTEXT + [L1, L1+4, table+16, table+20, table+0x460, table+0x464]
    regs = dict(regs)
    if case == "busy-before-map":
        regs["TRD"] = 1
    with flash.open("wb") as io:
        io.truncate(64 << 20)
        for k, v in regs.items():
            io.seek(ADDR[k])
            io.write(struct.pack("<I", v))
    before = [ADDR[k] for k in SEQ]
    seq = before + fields*2 + HCI
    if case in ("changed-context", "high-queue"):
        seq = before + fields[:5]
    elif case.startswith("foreign-table"):
        seq = before + fields[:7]
    elif case == "unstable-leaf":
        seq = before + fields*2
    elif case == "cpu-window-dirty":
        seq = before
    elif case == "busy-before-map":
        seq = before[:SEQ.index("TRD")+1]
    with guest(fd, harness, el, BASE,
               ["-drive", f"if=pflash,index=0,file={flash},format=raw,readonly=on"]) as (g, ram):
        for cmd in ("qSupported:qXfer:features:read+", "qXfer:features:read:target.xml:0,fff", "Hg0", "?"):
            g.command(cmd)
        os.pwrite(ram, dt, FDT - RAM_START)
        for addr, word in zip(fields, words, strict=True):
            os.pwrite(ram, struct.pack("<I", word), addr-RAM_START)
        if case == "cpu-window-dirty":
            os.pwrite(ram, b"\0", WINDOW+WINDOW_SIZE-1-RAM_START)
        g.set_register(33, 0x3c9 if el == 2 else 0x3c5)
        g.set_register(0, FDT)
        g.set_register(18, 0)
        g.set_register(20, BASE)
        g.set_register(32, 0x41000000 + (64 if el == 2 else 0))
        until(g, pc["entry"])
        for lo, hi in [*RANGES, (RAM_START, 0x80470000), (0x8047f000, FB_BASE),
                       (FB_BASE+SURFACE_BYTES, RAM_START + (2 << 30))]:
            watch(g, 2, lo, hi)
        for lo, hi in [(TR & ~4095, (TR & ~4095) + 4096), (0x90500000, 0x90501000)]:
            watch(g, 3, lo, hi)
        for name in ("read", "stop"):
            require(g.command(f"Z1,{pc[name]:x},4") == "OK", "breakpoint")
        for index, addr in enumerate(seq):
            msg = g.command("c")
            require("watch:" not in msg and g.register(32) == pc["read"] and g.register(0) == addr,
                    f"{case} read {index}: expected {addr:#x}, got {g.register(0):#x}")
            if case == "unstable-leaf" and index == len(before)+len(fields)+7:
                os.pwrite(ram, struct.pack("<I", 0x80400455), addr-RAM_START)
            require(g.command(f"z1,{pc['read']:x},4") == "OK", "remove breakpoint")
            g.command("s")
            if case == "changed-hci" and index == len(seq)-4:
                g.set_register(2, TR+1024)
            require(g.command(f"Z1,{pc['read']:x},4") == "OK", "rearm breakpoint")
        end = g.command("c")
        require("watch:" not in end and g.register(32) == pc["stop"], f"{case}: unexpected access {end}")
        state, label = CASES[case]
        lines = [("UFS " + state).ljust(14) + label]
        if state == "LK MAP":
            lines.extend(["HBA 00624000", f"UTR 00000000 {TR:08X}", f"UTM 00000000 {TM:08X}",
                          f"L1  00000000 {table|3:08X}", "FD  00400000 80400451",
                          "LK  00000000 91800451", "DMA WINDOW UNTESTED"])
        screen_oracle(os.pread(ram, SURFACE_BYTES, FB_BASE-RAM_START), lines)
    return {"el": el, "case": case, "state": state, "label": label, "guardedLoads": len(seq),
            "controllerWrites": 0, "unapprovedRamWrites": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("fd", "sec-elf", "runtime-fdt", "report", "static-report"):
        parser.add_argument("--" + flag, type=Path, required=True)
    a = parser.parse_args()
    fd = a.fd.read_bytes()
    a.static_report.write_text(json.dumps(inspect_fd(fd, a.sec_elf), indent=2) + "\n")
    info = verify(fd)
    syms = symbols(a.sec_elf)
    entry = int(info["secEntryAddress"], 16)
    bias = entry - syms["_ModuleEntryPoint"]
    pc = {"entry": entry, "stop": bias + syms["UfsStop"], "read": bias + syms["GoUfsRead32"]}
    dt = a.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest() == RUNTIME_SHA, "runtime FDT changed")
    physical = json.loads((ROOT/"docs/evidence/ufs-handoff-transfer-20261121.json").read_bytes())
    regs = {k: int(v, 16) for k, v in physical["physicalPanel"]["registersHex"].items()}
    regs.update(CAP=0x0107001f, TRL=TR, TRH=0, TML=TM, TMH=0)
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        subprocess.run(["aarch64-linux-gnu-gcc", "-c", ROOT/"tests/entry_harness.S", "-o", tmp/"entry.o"], check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy", "-O", "binary", tmp/"entry.o", tmp/"entry.bin"], check=True)
        rows = []
        for el in (1, 2):
            for case in CASES:
                rows.append(exercise(a.fd, tmp/"entry.bin", tmp/"regs.rom", dt, pc, el, case, regs))
                print(el, case, flush=True)
    a.report.write_text(json.dumps({"outcome": "PASS-QEMU", "fdSha256": info["sha256"],
        "physicalDma": "UNKNOWN", "cases": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
