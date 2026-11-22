"""Boot the SEC-only AGGRE2 clock panel at EL1/EL2 using synthetic MMIO.

SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from sec_mem_qemu import ROOT, RUNTIME_SHA, require, symbols, verify
from ufs_handoff_qemu import RANGES, exercise
from ufs_handoff_static import inspect


GUID = "8c0a0ea3-c44c-4076-bbfd-ee061713e160"
# Independent register inventory for the AGGRE2 route in the original RPM.
REGS = [(0x383004, "DOM", 0xa0222000), (0x383008, "NAX", 0x20000001),
        (0x38300c, "NAH", 0x00000001), (0x38301c, "SAX", 0x00004221),
        (0x383020, "SAH", 0x20008001)]
# ANOC2 range from the captured DT: /soc/arm,smmu-anoc2@1680000 reg.
WATCHED = [*RANGES, (0x1680000, 0x16a0000)]
CASES = [
    ("active", 5, {}, "CLOCKS"),
    ("domain-off", 1, {0: 0}, "STOP"),
    ("collapse-request", 1, {0: 0x80000001}, "STOP"),
    ("branches-off", 5, {i: 0x80000000 for i in range(1, 5)}, "CLOCKS"),
    *[(f"invalid-{label.lower()}", i + 1, {i: 0xffffffff}, "INVALID")
      for i, (_, label, _) in enumerate(REGS)],
    ("load-abort", 4, {}, "FAULT"),
    ("wrong-board", 0, {}, ""),
]


def route_panel(regs, count, state, values):
    label = "SAMPLED" if state == "CLOCKS" else regs[count - 1][1]
    lines = [("UFS " + state).ljust(14) + label] + [""] * 6 + ["FD BUS UNKNOWN"]
    for i in range(count - (state == "FAULT")):
        lines[i + 1] = f"{regs[i][1]:4}{values[i]:08X}"
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("fd", "sec-elf", "runtime-fdt", "report", "static-report"):
        ap.add_argument("--" + name, type=Path, required=True)
    args = ap.parse_args()
    dt = args.runtime_fdt.read_bytes()
    require(hashlib.sha256(dt).hexdigest() == RUNTIME_SHA, "wrong runtime DT")
    fd = args.fd.read_bytes()
    static = inspect(fd, args.sec_elf, GUID, {"mRouteSamples": REGS})
    entry = int(verify(fd)["secEntryAddress"], 16)
    names = symbols(args.sec_elf)
    bias = entry - names["_ModuleEntryPoint"]
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        obj, harness = tmp / "entry.o", tmp / "entry.bin"
        subprocess.run(["aarch64-linux-gnu-gcc", "-c", ROOT / "tests/entry_harness.S", "-o", obj], check=True)
        subprocess.run(["aarch64-linux-gnu-objcopy", "-O", "binary", obj, harness], check=True)
        for el in (1, 2):
            for case in CASES:
                rows.append(exercise(args.fd, harness, tmp / "registers.rom", dt, el, case,
                                     entry, bias + names["UfsStop"], bias + names["GoUfsRead32"],
                                     regs=REGS, ranges=WATCHED, panel=route_panel))
                print(el, case[0], "PASS", flush=True)
    result = {"outcome": "PASS-QEMU-ROUTE-CLOCKS", "fdSha256": static["fdSha256"],
              "qemu": subprocess.check_output(["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
              "model": "GCC, UFS HBA and ANOC2 ranges watched; synthetic register values",
              "watchedRangesEndExclusive": [[hex(lo), hex(hi)] for lo, hi in WATCHED],
              "physicalBus": "UNKNOWN", "cases": rows}
    args.static_report.write_text(json.dumps(static, indent=2) + "\n")
    args.report.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
