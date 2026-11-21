"""Boot the terminal handoff FD at EL1/EL2. Private runtime DT, synthetic registers.
Run in WSL/Debian. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from sec_mem_qemu import (ROOT, BASE, FDT, FB_BASE, RAM_START, RUNTIME_SHA, SURFACE_BYTES,
                          guest, require, symbols, until, verify, watch)

# Independent physical-address and display oracle, from the source ledger.
REGS = [(0x375004, "PWR", 0x80000000), (0x375000, "RST", 0),
        (0x37500c, "AHB", 1), (0x375008, "AXI", 1), (0x375038, "NOC", 0x20000001),
        (0x383014, "AGG", 1), (0x624008, "VER", 0x110), (0x624034, "HCE", 1),
        (0x624030, "HCS", 0x0f), (0x624060, "TRR", 1), (0x624058, "TRD", 4),
        (0x624080, "TMR", 1), (0x624078, "TMD", 0)]
# Each case expects exactly this prefix of the ordered whitelist.
CASES = [
    ("active", 13, {}, "DONE"),
    ("power-off", 1, {0: 0}, "GATED"), ("collapse-request", 1, {0: 0x80000001}, "GATED"),
    ("reset", 2, {1: 1}, "GATED"), ("ahb-off", 3, {2: 0x80000000}, "GATED"),
    ("axi-transition", 4, {3: 0x10000001}, "GATED"), ("noc-off", 5, {4: 0x80000000}, "GATED"),
    ("aggre-off", 6, {5: 0x80000000}, "GATED"), ("bad-version", 7, {6: 0}, "INVALID"),
    ("bus-ones", 1, {0: 0xffffffff}, "INVALID"), ("hce-off", 8, {7: 0}, "DISABLED"),
    ("load-abort", 7, {}, "FAULT"), ("wrong-board", 0, {}, "")]
RANGES = [(0x300000, 0x390000), (0x624000, 0x624000 + 0x2500)]


def screen_oracle(fb, lines):
    header = (ROOT / "OculusGoPkg/Include/third-party/edk2/ConsoleFont.h").read_text()
    glyphs = {chr(int(code, 16)): bytes.fromhex(" ".join(re.findall(r"0x([\da-fA-F]{2})", row)))
              for row, code in re.findall(r"\{ ([^{}\n]+) \},\s*// U\+([0-9a-fA-F]{4})", header)}
    for eye in range(2):
        for r, text in enumerate(lines):
            for c, char in enumerate(text.ljust(29)):
                glyph = glyphs[char]
                for y, bits in enumerate(glyph):
                    for x in range(8):
                        val = 255 if bits & (128 >> x) else 0
                        native_x = 1439 - (568 + r * 38 + y * 2)
                        native_y = eye * 1280 + 408 + c * 16 + x * 2
                        pos = native_y * 4320 + native_x * 3
                        if fb[pos:pos + 3] != bytes([val]) * 3:
                            raise AssertionError(("scanout", eye, r, c, char, x, y))


def exercise(fd, harness, flash, dt, el, case, entry, stop, read):
    name, count, overrides, state = case
    vals = [overrides.get(i, v) for i, (_, _, v) in enumerate(REGS)]
    with flash.open("wb") as f:
        f.truncate(64 << 20)
        for (addr, _, _), val in zip(REGS, vals):
            f.seek(addr)
            f.write(struct.pack("<I", val))
    extra = ["-drive", f"if=pflash,index=0,file={flash},format=raw,readonly=on"]
    if name == "wrong-board":
        require(dt.count(b"Oculus Pacific EVT\0") == 1, "unexpected board identity")
        dt = dt.replace(b"Oculus Pacific EVT\0", b"Oculus Pacific XXX\0")
    with guest(fd, harness, el, BASE, extra) as (g, ram):
        g.command("qSupported:qXfer:features:read+")
        g.command("qXfer:features:read:target.xml:0,fff")
        g.command("Hg0")
        g.command("?")
        require(os.pwrite(ram, dt, FDT - RAM_START) == len(dt), "DT fixture failed")
        g.set_register(33, 0x3c9 if el == 2 else 0x3c5)
        g.set_register(0, FDT)
        g.set_register(18, 0)
        g.set_register(20, BASE)
        setup = 0x41000000 + (64 if el == 2 else 0)
        g.set_register(32, setup)
        until(g, entry)
        require(g.read(read, 4) == bytes.fromhex("020040b9"), "expected LDR W2,[X0]")
        for lo, hi in RANGES:
            watch(g, 4, lo, hi)  # trap both reads and stores
        require(g.command(f"Z1,{stop:x},4") == "OK", "cannot observe terminal state")
        visits = []
        for i in range(count):
            addr, label, _ = REGS[i]
            msg = g.command("c")
            require("watch:" in msg and g.register(32) == read and g.register(0) == addr,
                    f"{name} unexpected access at PC {g.register(32):#x} (wanted {addr:#x}): {msg}")
            visits.append(label)
            lo, hi = next((a, b) for a, b in RANGES if a <= addr < b)
            watch(g, 4, lo, hi, False)
            if name == "load-abort" and i == count - 1:
                # Deliberately cause a real same-EL alignment fault on the one
                # watched LDR. Never modify the guest FD or its vector table.
                saved = [g.register(n) for n in range(17, 21)]
                g.set_register(18, 2)
                g.set_register(20, read)
                g.set_register(32, setup)
                until(g, read)
                for n, val in enumerate(saved, 17):
                    g.set_register(n, val)
                g.set_register(0, addr + 1)
            msg = g.command("s")
            require(msg.startswith(("T", "S")), "single-step failed")
            if not (name == "load-abort" and i == count - 1):
                require(g.register(32) == read + 4 and g.register(2) == vals[i],
                        f"{name}/{label}: wrong register value")
            watch(g, 4, lo, hi)
        msg = g.command("c")
        require("watch:" not in msg and g.register(32) == stop, f"{name}: unexpected trailing access")
        fb = os.pread(ram, SURFACE_BYTES, FB_BASE - RAM_START)
        if count == 0:
            require(not any(fb), "unrecognized FDT touched the framebuffer")
        else:
            last = "" if state == "DONE" else REGS[count - 1][1]
            lines = [("UFS " + state).ljust(14) + last] + [""] * 7
            for i in range(count - (state == "FAULT")):
                r = 1 + i // 2
                lines[r] = lines[r].ljust((i % 2) * 15) + f"{REGS[i][1]} {vals[i]:08X}"
            screen_oracle(fb, lines)
    return {"el": el, "case": name, "registerLoads": visits, "peripheralStores": 0,
            "expectedScreenVerified": True, "heading": lines[0].strip() if count else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ["fd", "sec-elf", "runtime-fdt", "report"]:
        ap.add_argument("--" + arg, type=Path, required=True)
    a = ap.parse_args()
    dt = a.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest() == RUNTIME_SHA, "wrong private runtime DT")
    info = verify(a.fd.read_bytes())
    entry = int(info["secEntryAddress"], 16)
    sym = symbols(a.sec_elf)
    bias = entry - sym["_ModuleEntryPoint"]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        obj, harness = p / "entry.o", p / "entry.bin"
        subprocess.run(["aarch64-linux-gnu-gcc", "-c", ROOT / "tests/entry_harness.S", "-o", obj], check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy", "-O", "binary", obj, harness], check=True)
        for el in (1, 2):
            for case in CASES:
                rows.append(exercise(a.fd, harness, p / "registers.rom", dt, el, case, entry,
                                     bias + sym["UfsStop"], bias + sym["GoUfsRead32"]))
                print(el, case[0], "PASS", flush=True)
    doc = {"outcome": "PASS-QEMU", "model": "synthetic read-only register values, captured runtime DT",
           "qemu": subprocess.check_output(["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
           "fdSha256": info["sha256"], "physicalState": "UNKNOWN", "cases": rows}
    a.report.write_text(json.dumps(doc, indent=2) + "\n")


if __name__ == "__main__":
    main()
