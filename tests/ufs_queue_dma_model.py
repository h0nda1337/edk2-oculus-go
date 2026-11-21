"""Host-only DMA witness on QEMU virt PCI UFS. No disk, target machine or USB APIs.
The Pacific FD contains none of this code. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import select
import struct
import subprocess
import tempfile
import time

WINDOW, LENGTH = 0x80440000, 0x4000
MACHINE = ["qemu-system-aarch64", "-machine", "virt,highmem=off", "-accel", "tcg",
           "-cpu", "cortex-a57", "-m", "1280M", "-nodefaults", "-display", "none",
           "-monitor", "none", "-serial", "none"]


class Bus:
    def __init__(self, process):
        self.proc = process

    def command(self, cmd):
        self.proc.stdin.write((cmd + "\n").encode())
        self.proc.stdin.flush()
        if not select.select([self.proc.stdout], [], [], 5)[0]:
            raise TimeoutError(cmd.split()[0])
        line = self.proc.stdout.readline().decode().strip().split()
        if line[:1] != ["OK"]:
            raise RuntimeError((cmd[:80], line))
        return line[1:]

    def read32(self, addr):
        return int(self.command(f"readl {addr:#x}")[0], 16)

    def write32(self, addr, val):
        self.command(f"writel {addr:#x} {val:#x}")

    def write(self, addr, data):
        self.command(f"write {addr:#x} {len(data):#x} 0x{data.hex()}")

    def read(self, addr, size):
        return bytes.fromhex(self.command(f"read {addr:#x} {size:#x}")[0][2:])

    def wait_bits(self, addr, mask, expected):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            value = self.read32(addr)
            if value & mask == expected:
                return value
            time.sleep(0.005)
        raise RuntimeError(f"register {addr:#x} ended {value:#x}, expected {expected:#x} with {mask:#x}")


@contextmanager
def controller(tmp, ecam, bar, *, machine=MACHINE, extra=()):
    events, trace = tmp / "events", tmp / "ufs.trace"
    events.write_text("ufs_exec_nop_cmd\nufs_exec_scsi_cmd\nufs_exec_query_cmd\n")
    # No virtual LUN or block backend is attached. PCI function 1 is explicit.
    cmd = machine + [*extra, "-S", "-device", "ufs,addr=1.0,mcq=off", "-qtest", "stdio",
                     "-qtest-log", "/dev/null", "-trace", f"events={events},file={trace}"]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
        try:
            bus = Bus(proc)
            cfg = ecam + (1 << 15)
            if bus.read32(cfg + 8) >> 8 != 0x010901:
                raise RuntimeError("wrong PCI UFS class")
            bus.write32(cfg + 0x10, bar)
            bus.write32(cfg + 0x14, 0)
            bus.command(f"writew {cfg + 4:#x} 6")   # virtual memory decoding and PCI bus mastering
            if bus.read32(cfg + 0x10) & ~15 != bar:
                raise RuntimeError("BAR assignment failed")
            bus.write32(bar + 0x34, 1)
            bus.wait_bits(bar + 0x30, 8, 8)
            bus.write32(bar + 0x90, 0x16)            # virtual DME_LINK_STARTUP
            bus.wait_bits(bar + 0x30, 0xf, 0xf)
            yield bus
        finally:
            proc.terminate()
            proc.wait(timeout=5)


def one_page(bus, bar, page):
    # Exercise each page as a UCD; UTRDL and UTMRDL occupy two different pages.
    ucd = WINDOW + page * 4096
    tr = WINDOW + ((page + 1) % 4) * 4096
    tm = WINDOW + ((page + 2) % 4) * 4096
    tag = 0x50 + page
    rsp = ucd + 512
    baseline = bytearray(b"\xa5" * LENGTH)
    baseline[ucd-WINDOW:ucd-WINDOW+32] = bytes([0, 0, 0, tag]) + bytes(28)
    struct.pack_into("<IIIIIIHHHH", baseline, tr - WINDOW, 0x11000000, 0, 15, 0,
                     ucd, 0, 8, 128, 0, 0)
    bus.write(WINDOW, baseline)
    if bus.read(WINDOW, LENGTH) != baseline:
        raise RuntimeError("virtual RAM seed failed")
    for off, value in [(0x50, tr), (0x54, 0), (0x70, tm), (0x74, 0), (0x60, 1), (0x80, 1)]:
        bus.write32(bar + off, value)
    bus.write32(bar + 0x58, 1)
    bus.wait_bits(bar + 0x58, 1, 0)
    result = bus.read(WINDOW, LENGTH)
    response = result[rsp-WINDOW:rsp-WINDOW+32]
    if struct.unpack_from("<I", result, tr-WINDOW+8)[0] != 0 or response[:1] != b"\x20" or response[3] != tag or response[6] != 0:
        raise RuntimeError(f"missing NOP IN / OCS success: {response.hex()}, OCS={result[tr-WINDOW+8]:#x}")
    allowed = {tr-WINDOW+8, *range(rsp-WINDOW, rsp-WINDOW+32)}
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(baseline, result))):
        raise RuntimeError("unexpected DMA difference inside the 16 KiB window")
    bus.write32(bar + 0x60, 0)
    bus.write32(bar + 0x80, 0)
    return {"ucd": hex(ucd), "utrdl": hex(tr), "response": hex(rsp), "tag": tag,
            "responseType": "NOP IN", "ocs": 0}


def run():
    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        dtb = tmp / "virt.dtb"
        subprocess.run(MACHINE + ["-machine", f"dumpdtb={dtb}"], check=True, capture_output=True)
        def cells(prop):
            return [int(n, 16) for n in subprocess.check_output(
                ["fdtget", "-tx", dtb, "/pcie@10000000", prop], text=True).split()]
        reg, ranges = cells("reg"), cells("ranges")
        if reg[:2] != [0, 0x3f000000] or [0x2000000, 0, 0x10000000, 0, 0x10000000] != ranges[7:12]:
            raise RuntimeError("unexpected QEMU virt PCI geometry")
        with controller(tmp, reg[1], ranges[9]) as bus:
            pages = [one_page(bus, ranges[9], page) for page in range(4)]
        trace = (tmp / "ufs.trace").read_bytes()
        if trace.count(b"ufs_exec_nop_cmd") != 4 or b"ufs_exec_scsi_cmd" in trace or b"ufs_exec_query_cmd" in trace:
            raise RuntimeError("unexpected virtual UFS command trace")
    return {"outcome": "PASS-QEMU-PCI-DMA", "qemu": subprocess.check_output(
            ["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
            "windowCpuPa": hex(WINDOW), "bytes": LENGTH, "model": "PCI DMA identity, no IOMMU, stopped guest CPU",
            "diskBackends": 0, "scsiCommands": 0, "ufsQueries": 0, "nopTransfers": pages,
            "traceSha256": hashlib.sha256(trace).hexdigest(), "pacificDmaMapping": "UNKNOWN"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    args.report.write_text(json.dumps(run(), indent=2) + "\n")
