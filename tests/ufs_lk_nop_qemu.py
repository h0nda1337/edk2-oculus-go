"""Run an AArch64 NOP handoff under TCG against the actual emulated PCI device.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import tempfile

from ufs_queue_dma_model import controller, MACHINE, WINDOW, LENGTH

HERE = Path(__file__).resolve().parent
BAR, TR, TM, BOX = 0x10000000, 0x918ee400, 0x918eec00, 0x40300000
CASES = [(f"page-{p}", p, 1) for p in range(4)] + [
    ("unknown-domain", 0, 2), ("stopped-transfer-list", 0, 3),
    ("different-inherited-base", 0, 3), ("dirty-window", 0, 4), ("smmu-denies-dma", 0, 6)]


def check(ok, message):
    if not ok:
        raise RuntimeError(message)


def start_cpu(path):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(5)
        sock.connect(str(path))
        with sock.makefile("rwb", buffering=0) as io:
            check("QMP" in json.loads(io.readline()), "QMP greeting")
            for command in ("qmp_capabilities", "cont"):
                io.write(json.dumps({"execute": command}).encode() + b"\n")
                reply = json.loads(io.readline())
                while "event" in reply:
                    reply = json.loads(io.readline())
                check("return" in reply, repr(reply))


def one(tmp, elf, name, page, expected):
    machine = ["1536M" if arg == "1280M" else arg for arg in MACHINE]
    denied = name == "smmu-denies-dma"
    with_smmu = denied or name == "page-0"
    if with_smmu:
        machine = [arg + ",iommu=smmuv3" if arg.startswith("virt,") else arg for arg in machine]
    extra = ["-device", f"loader,file={elf},cpu-num=0",
             "-qmp", f"unix:{tmp / 'control'},server=on,wait=off"]
    # Seed the observed LK base pair on a real emulated HCI, then start the CPU.
    with controller(tmp, 0x3f000000, BAR, machine=machine, extra=extra) as bus:
        if with_smmu:
            # DTB supplied by this QEMU machine, never an address on Pacific.
            dtb = tmp / "model.dtb"
            subprocess.run(machine + ["-machine", f"dumpdtb={dtb}"], check=True, capture_output=True)
            def prop(node, key):
                return [int(x, 16) for x in subprocess.check_output(["fdtget", "-tx", dtb, node, key], text=True).split()]
            node = "/smmuv3@9050000"
            reg = prop(node, "reg")
            check(prop("/pcie@10000000", "iommu-map") == [0, *prop(node, "phandle"), 0, 0x10000], "virtual stream routing")
            check(reg == [0, 0x9050000, 0, 0x20000] and bus.read32(reg[1]+0x20) == 0, "virtual SMMU at reset")
            policy = (1 << 20) if denied else 0
            bus.write32(reg[1] + 0x44, (1 << 31) | policy)  # GBPA.UPDATE plus selected policy
            check(bus.read32(reg[1] + 0x44) == policy, "virtual SMMU policy did not latch")
        inherited = bytes((i * 31 + 19) & 255 for i in range(4096))
        bus.write(TR & ~4095, inherited)
        start = bytearray([0xa5]) * LENGTH
        if name == "dirty-window":
            start[-1] = 0
        bus.write(WINDOW, start)
        guard = bytes([0x3c]) * 4096
        for addr in (WINDOW - 4096, WINDOW + LENGTH):
            bus.write(addr, guard)
        for off, value in [(0x50, TR if name != "different-inherited-base" else TR + 1024),
                           (0x54, 0), (0x70, TM), (0x74, 0), (0x80, 1),
                           (0x60, int(name != "stopped-transfer-list"))]:
            bus.write32(BAR + off, value)
        registers = [0x34, 0x50, 0x54, 0x58, 0x60, 0x70, 0x74, 0x78, 0x80]
        is_before, ie_before = bus.read32(BAR + 0x20), bus.read32(BAR + 0x24)
        before = [bus.read32(BAR + off) for off in registers]
        bus.write(BOX, struct.pack("<4I", page, int(name != "unknown-domain"), 0, 0))
        start_cpu(tmp / "control")
        bus.wait_bits(BOX + 12, 0xffffffff, 0x444f4e45)
        result = bus.read32(BOX + 8)
        check(result == expected, f"{name}: guest returned {result}")
        result_window = bus.read(WINDOW, LENGTH)
        check(bus.read(TR & ~4095, 4096) == inherited, "LK page changed")
        is_after = bus.read32(BAR + 0x20)
        check(bus.read32(BAR + 0x24) == ie_before and not (is_before & ~is_after),
              "interrupt enable changed or pending status acknowledged")
        after = [bus.read32(BAR + off) for off in registers]
        if denied:
            pending = before.copy()
            pending[1], pending[3] = WINDOW + 4096, 1
            check(after == pending, f"pending queue was repointed or changed: {after}")
        else:
            check(after == before, "HCI handoff differs")
        check(all(bus.read(a, 4096) == guard for a in (WINDOW-4096, WINDOW+LENGTH)), "guard changed")
        row = {"interruptStatusBefore": hex(is_before), "interruptStatusAfter": hex(is_after),
               "case": name, "guestStatus": result, "inheritedPageIntact": True,
               "baseAndRunRestored": not denied, "outsideGuardsIntact": True}
        if with_smmu:
            row["smmu"] = "GBPA.ABORT" if denied else "GBPA default bypass"
        if expected == 1 or denied:
            tag = 0x71 + page
            tr = ((page + 1) % 4) * 4096
            req = page * 4096 + 0xc00
            rsp = req + 0x3e0
            start[req:req+32] = bytes([0, 0, 0, tag]) + bytes(28)
            struct.pack_into("<8I", start, tr, 0x11000000, 0, 15 if denied else 0, 0, WINDOW + req, 0, 0x00f80008, 0)
            expected_rsp = bytes([0x20, 0, 0, tag]) + bytes(28)
            if denied:
                row.update(responseUntouched=True, pendingQueueRetained=True, ocs=15)
            else:
                check(result_window[rsp:rsp+32] == expected_rsp, "incorrect NOP IN")
                start[rsp:rsp+32] = expected_rsp
                row.update(tag=tag, response=hex(WINDOW+rsp), ocs=0)
        check(start == result_window, "unexpected bytes in the 16 KiB window")
        row["virtualTaskRunReadback"] = before[-1]
    trace = (tmp / "ufs.trace").read_text()
    nops = trace.count("ufs_exec_nop_cmd")
    check(nops == int(expected == 1) and "ufs_exec_scsi_cmd" not in trace and
          "ufs_exec_query_cmd" not in trace, "unexpected UFS command")
    return row | {"nopCount": nops}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        entry = tmp / "entry.S"
        entry.write_text(".text\n.global _start\n_start:\n ldr x0, =0x40210000\n mov sp,x0\n b run_guest\n")
        elf = tmp / "guest.elf"
        subprocess.run(["aarch64-linux-gnu-gcc", "-nostdlib", "-static", "-ffreestanding",
                        "-mgeneral-regs-only", "-fno-stack-protector", "-O2", "-Wall", "-Werror",
                        "-Wl,-Ttext=0x40200000,--build-id=none", str(entry),
                        str(HERE / "ufs_lk_nop_guest.c"), "-o", str(elf)], check=True)
        rows = []
        for name, page, expected in CASES:
            case = tmp / name
            case.mkdir()
            rows.append(one(case, elf, name, page, expected))
        report = {"outcome": "PASS-QEMU-TCG-NOP", "qemu": subprocess.check_output(
                  ["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
                  "guestSha256": hashlib.sha256(elf.read_bytes()).hexdigest(), "window": hex(WINDOW),
                  "bytes": LENGTH, "ordinaryLuns": 0, "scsiCommands": 0, "queryCommands": 0,
                  "dmaDomain": "QEMU virt PCI identity and SMMUv3 abort control", "pacificDma": "UNKNOWN", "cases": rows}
        args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
