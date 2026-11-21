"""Exercise the passive queue probe with captured LK prerequisites and synthetic queue registers.
Run in Debian/WSL; all accesses are inside QEMU. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from sec_mem_qemu import (ROOT, BASE, FDT, FB_BASE, RAM_START, RUNTIME_SHA, SURFACE_BYTES,
                          guest, require, symbols, until, verify, watch)
from ufs_handoff_qemu import REGS, RANGES, screen_oracle

WINDOW = 0x80440000
WINDOW_SIZE = 0x4000
QUEUE = [(0x624000, "CAP", 0x0007001f), (0x624050, "TRL", 0x81000000),
         (0x624054, "TRH", 0), (0x624070, "TML", 0x81200000), (0x624074, "TMH", 0)]
FINAL = ["HCE", "HCS", "TRR", "TRD", "TMR", "TMD"]
GATES = [label for _, label, _ in REGS]
FIELDS = [label for _, label, _ in QUEUE]
SEQ = GATES + FIELDS * 2 + FINAL
ADDR = {label: addr for addr, label, _ in REGS + QUEUE}


@dataclass
class Case:
    name: str
    state: str = "QUEUES"
    label: str = "DONE"
    changes: dict = field(default_factory=dict)
    reads: int = len(SEQ)
    transition: int | None = None


CASES = [
    Case("stable32"), Case("one-slot", changes={"CAP": 0}),
    Case("stable64", changes={"CAP": 0x0107001f, "TRH": 1, "TMH": 2}),
    Case("last-32-bit-block", changes={"TRL": 0xfffffc00}),
    Case("adjacent-lists", changes={"TML": 0x81000400}),
    Case("window-boundary", changes={"TRL": WINDOW - 1024, "TML": WINDOW + WINDOW_SIZE}),
    Case("gated", "GATED", "PWR", {"PWR": 0}, 1),
    Case("hce-off", "DISABLED", "HCE", {"HCE": 0}, 8),
    Case("unsupported-version", "VERSION", "VER", {"VER": 0x00020000}, 7),
    Case("host-error", "NOT READY", "HCS", {"HCS": 0x1f}, 9),
    Case("list-stopped", "NOT READY", "TRR", {"TRR": 0}, 10),
    Case("busy", "BUSY", "TMD", {"TMD": 2}, 13),
    Case("base-changed", "CHANGED", "TRH", reads=21, transition=3),
    Case("door-changed", "CHANGED", "TRD", reads=27, transition=1),
    Case("bad-cap", "INVALID", "CAP", {"CAP": 0xffffffff}),
    Case("zero-base", "INVALID", "UTR", {"TRL": 0}),
    Case("alignment", "INVALID", "UTM", {"TML": 0x81200004}),
    Case("32-bit-high", "INVALID", "UTR", {"TRH": 1}),
    Case("end-overflow", "INVALID", "UTR", {"CAP": 0x0107001f, "TRH": 0xffffffff, "TRL": 0xfffffc00}),
    Case("overlap", "OVERLAP", "LISTS", {"TML": 0x81000000}),
    Case("fd-alias", "OVERLAP", "FD", {"TRL": WINDOW}),
    Case("reserved-node", "CONFLICT", "FDT"), Case("reservation-block", "CONFLICT", "FDT"),
    Case("last-word-dirty", "DIRTY", "FD"),
    Case("load-abort", "FAULT", "TML", reads=17),
    Case("wrong-board", "", "", reads=0),
]


def model_dt(original, case, tmp):
    if case == "wrong-board":
        return original.replace(b"Oculus Pacific EVT\0", b"Oculus Pacific XXX\0")
    if case == "reserved-node":
        path = tmp / "conflict.dtb"
        path.write_bytes(original)
        subprocess.run(["fdtput", "-c", path, "/reserved-memory/queue-test"], check=True)
        subprocess.run(["fdtput", "-t", "x", path, "/reserved-memory/queue-test", "reg",
                        "0", f"{WINDOW + WINDOW_SIZE - 1:x}", "0", "1"], check=True)
        return path.read_bytes()
    if case == "reservation-block":
        data = bytearray(original)
        reserve, = struct.unpack_from(">I", data, 16)
        data[reserve:reserve] = struct.pack(">QQ", WINDOW, 1)
        for off in (4, 8, 12):
            struct.pack_into(">I", data, off, struct.unpack_from(">I", data, off)[0] + 16)
        return data
    return original


def load_rows(case, values):
    lines = [("UFS " + case.state).ljust(14) + case.label]
    if case.reads <= len(GATES):
        return lines
    n = min(len(FIELDS), case.reads - len(GATES) - (case.state == "FAULT"))
    fields = {label: f"{values[label]:08X}" for label in FIELDS[:n]}
    cap = values["CAP"]
    geometry = case.reads == len(SEQ) and case.name != "bad-cap"
    candidate = geometry and case.state != "INVALID" and case.label != "LISTS"
    def base_row(prefix, high, low):
        row = prefix
        if high in fields:
            row = row.ljust(4) + fields[high]
        if low in fields:
            row = row.ljust(13) + fields[low]
        return row
    caps = ("CAP " + fields.get("CAP", "")).rstrip()
    if geometry:
        caps = caps.ljust(15) + ("ADDR 64" if cap & (1 << 24) else "ADDR 32")
    lengths = f"LEN {((cap & 31) + 1) * 32:08X} {(((cap >> 16) & 7) + 1) * 80:08X}"
    lines.extend([caps, base_row("UTR", "TRH", "TRL"), base_row("UTM", "TMH", "TML"),
                  lengths if geometry else "", "FD  80440000 00004000" if candidate else "",
                  "CPU WINDOW CLEAN" if case.state == "QUEUES" else "", "DMA MAP UNKNOWN"])
    return lines


def exercise(fd, harness, flash, dt, entry, read, stop, el, case, values):
    with flash.open("wb") as f:
        f.truncate(64 << 20)
        for label, addr in ADDR.items():
            f.seek(addr)
            f.write(struct.pack("<I", values[label]))
    extra = ["-drive", f"if=pflash,index=0,file={flash},format=raw,readonly=on"]
    with guest(fd, harness, el, BASE, extra) as (g, ram):
        for cmd in ("qSupported:qXfer:features:read+", "qXfer:features:read:target.xml:0,fff", "Hg0", "?"):
            g.command(cmd)
        os.pwrite(ram, dt, FDT - RAM_START)
        if case.name == "last-word-dirty":
            os.pwrite(ram, b"\x42", WINDOW + WINDOW_SIZE - 1 - RAM_START)
        g.set_register(33, 0x3c9 if el == 2 else 0x3c5)
        g.set_register(0, FDT)
        g.set_register(18, 0)
        g.set_register(20, BASE)
        setup = 0x41000000 + (64 if el == 2 else 0)
        g.set_register(32, setup)
        until(g, entry)
        for lo, hi in RANGES:
            watch(g, 4, lo, hi)
        # Allow CPU stores only to the top 60 KiB of private stack and the scanout.
        for lo, hi in ((RAM_START, 0x80470000), (0x8047f000, FB_BASE),
                       (FB_BASE + SURFACE_BYTES, RAM_START + (2 << 30))):
            watch(g, 2, lo, hi)
        # A queue address is not a CPU pointer. Cover both test queues, including
        # their high aliases and the model's "just outside candidate" boundaries.
        for pre in ("TR", "TM"):
            addr = values[pre + "L"] | (values[pre + "H"] << 32)
            if addr and addr < (1 << 64) - 1024 and not (WINDOW <= addr < WINDOW + WINDOW_SIZE):
                watch(g, 3, addr, addr + (32 if pre == "TR" else 80))
        if case.state not in ("QUEUES", "DIRTY"):
            watch(g, 3, WINDOW, WINDOW + WINDOW_SIZE)
        require(g.command(f"Z1,{stop:x},4") == "OK", "cannot watch terminal state")
        for idx, label in enumerate(SEQ[:case.reads]):
            msg = g.command("c")
            addr = ADDR[label]
            require("watch:" in msg and g.register(32) == read and g.register(0) == addr,
                    f"{case.name} unexpected access at {g.register(32):#x}, expected {label}")
            lo, hi = next((a, b) for a, b in RANGES if a <= addr < b)
            watch(g, 4, lo, hi, False)
            fault = case.name == "load-abort" and idx == case.reads - 1
            if fault:
                saved = [g.register(n) for n in range(17, 21)]
                g.set_register(18, 2)
                g.set_register(20, read)
                g.set_register(32, setup)
                until(g, read)
                for n, v in enumerate(saved, 17):
                    g.set_register(n, v)
                g.set_register(0, addr + 1)
            g.command("s")
            if not fault:
                require(g.register(32) == read + 4 and g.register(2) == values[label],
                        "unexpected register load result")
                if case.transition is not None and idx == case.reads - 1:
                    # Inject a changed second sample at the load result; FD is unmodified.
                    g.set_register(2, case.transition)
            watch(g, 4, lo, hi)
        msg = g.command("c")
        require("watch:" not in msg and g.register(32) == stop, f"{case.name}: extra access {msg}")
        fb = os.pread(ram, SURFACE_BYTES, FB_BASE - RAM_START)
        if case.reads:
            screen_oracle(fb, load_rows(case, values))
        else:
            require(not any(fb), "wrong board touched display")
    return {"el": el, "case": case.name, "loads": case.reads, "state": case.state,
            "label": case.label, "writesToController": 0, "unapprovedRamStores": 0}


def run(args):
    evidence = json.loads((ROOT / "docs/evidence/ufs-handoff-transfer-20261121.json").read_bytes())
    real = {k: int(v, 16) for k, v in evidence["physicalPanel"]["registersHex"].items()}
    require(set(real) == set(GATES), "incomplete physical prerequisite sample")
    dt = args.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest() == RUNTIME_SHA, "wrong local runtime DT")
    info = verify(args.fd.read_bytes())
    syms = symbols(args.sec_elf)
    entry = int(info["secEntryAddress"], 16)
    bias = entry - syms["_ModuleEntryPoint"]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        subprocess.run(["aarch64-linux-gnu-gcc", "-c", ROOT / "tests/entry_harness.S", "-o", p / "entry.o"], check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy", "-O", "binary", p / "entry.o", p / "entry.bin"], check=True)
        for el in (1, 2):
            for case in CASES:
                vals = {**real, **{k: v for _, k, v in QUEUE}, **case.changes}
                rows.append(exercise(args.fd, p / "entry.bin", p / "regs.rom", model_dt(dt, case.name, p),
                                     entry, bias + syms["GoUfsRead32"], bias + syms["UfsStop"], el, case, vals))
                print(el, case.name, "PASS", flush=True)
    return {"outcome": "PASS-QEMU", "qemu": subprocess.check_output(["qemu-system-aarch64", "--version"],
            text=True).splitlines()[0], "fdSha256": info["sha256"], "windowCpuPa": hex(WINDOW),
            "windowBytes": WINDOW_SIZE, "pacificDmaMapping": "UNKNOWN", "cases": rows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ["fd", "sec-elf", "runtime-fdt", "report"]:
        ap.add_argument("--" + flag, type=Path, required=True)
    args = ap.parse_args()
    args.report.write_text(json.dumps(run(args), indent=2) + "\n")
