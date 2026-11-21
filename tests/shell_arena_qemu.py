"""Check the actual NORMAL image before any GIC access, including dirty arena data.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import hashlib
import json
import socket
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sec_mem_qemu import BASE, Remote, require, symbols, until, verify
from verify_fd import SHELL_FD_SIZE, SIZE

END = BASE + SHELL_FD_SIZE
POOL = BASE + SIZE
CASES = {
    "clean": None,
    "first-marker": POOL,
    "middle": POOL + 0x800000,
    "last-marker": END - 4096,
    "last-word": END - 8,
    "overlapping-dtb": None,
}


def check(fd, image, addr, el, case):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(12)
        port = listener.getsockname()[1]
        command = [
            "qemu-system-aarch64",
            "-machine",
            "virt,gic-version=3,secure=off,virtualization=" + ("on" if el == 2 else "off"),
            "-cpu",
            "cortex-a57",
            "-m",
            "1536",
            "-smp",
            "1",
            "-nodefaults",
            "-display",
            "none",
            "-serial",
            "none",
            "-S",
            "-chardev",
            f"socket,id=probe,host=127.0.0.1,port={port},server=off",
            "-gdb",
            "chardev:probe",
            "-device",
            f"loader,file={fd.resolve()},addr={BASE:#x},cpu-num=0,force-raw=on",
        ]
        child = subprocess.Popen(command)
        try:
            sock, _ = listener.accept()
            with sock:
                g = Remote(sock)
                for cmd in (
                    "qSupported:qXfer:features:read+",
                    "qXfer:features:read:target.xml:0,fff",
                    "Hg0",
                    "?",
                ):
                    g.command(cmd)
                sp = 0x90010000
                g.set_register(31, sp)
                g.set_register(0, POOL if case == "overlapping-dtb" else 0x82000000)
                require(
                    g.register(32) == BASE and (g.register(33) >> 2) & 3 == el,
                    "Unexpected initial CPU state",
                )
                dirty = CASES[case]
                if dirty is not None:
                    g.write(dirty, bytes([image[dirty - BASE] ^ 1]))
                witness = g.read(END - 96, 96)
                target = "ArmEnableVFP" if case == "clean" else "EntryRejected"
                until(g, addr[target])
                if case == "clean":
                    require(
                        g.register(31) == END - 96
                        and g.read(END - 88, 8) == struct.pack("<Q", 0x82000000),
                        "Normal stack did not preserve incoming DTB",
                    )
                else:
                    require(
                        g.register(31) == sp and g.read(END - 96, 96) == witness,
                        "Rejected input changed the stack",
                    )
                return {
                    "el": el,
                    "case": case,
                    "stoppedAt": target,
                    "pc": hex(g.register(32)),
                    "sp": hex(g.register(31)),
                }
        finally:
            child.terminate()
            child.wait(timeout=8)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("fd", type=Path)
    p.add_argument("sec_elf", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    data = args.fd.read_bytes()
    info = verify(data)
    require(len(data) == SHELL_FD_SIZE, "Expected the normal console arena")
    offsets = symbols(args.sec_elf)
    bias = int(info["secEntryAddress"], 16) - offsets["_ModuleEntryPoint"]
    addresses = {k: bias + v for k, v in offsets.items()}
    cases = [(el, c) for el in (1, 2) for c in CASES]
    with ThreadPoolExecutor(max_workers=2) as workers:
        checks = list(workers.map(lambda item: check(args.fd, data, addresses, *item), cases))
    args.output.write_text(
        json.dumps({"fdSha256": hashlib.sha256(data).hexdigest(), "cases": checks}, indent=2) + "\n"
    )
    print(f"{len(checks)} SEC entry cases passed")
