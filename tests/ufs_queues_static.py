"""Verify queue probe bytes in the packaged FD. SPDX-License-Identifier: BSD-2-Clause-Patent"""
import argparse
import json
from pathlib import Path

from sec_mem_qemu import BASE, require
from ufs_handoff_static import inspect
from ufs_queues_qemu import ADDR, FINAL, QUEUE, REGS, WINDOW, WINDOW_SIZE

GUID = "e78bfd70-a2cc-465a-9908-4ea1c9e72426"


def audit(fd, elf):
    result = inspect(fd, elf, GUID, {"mSamples": REGS, "mQueueRegs": QUEUE,
                                     "mFinalRegs": [(ADDR[k], k, 0) for k in FINAL]})
    off = WINDOW - BASE
    require(off % 4096 == 0 and 0x3be000 + 4096 <= off < off + WINDOW_SIZE <= 0x3f0000
            and fd[off:off + WINDOW_SIZE] == bytes([255]) * WINDOW_SIZE,
            "window outside owned FD tail or not entirely blank")
    result.update(windowStart=hex(WINDOW), windowEndExclusive=hex(WINDOW + WINDOW_SIZE),
                  initialWindowBytesVerified=WINDOW_SIZE)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ["fd", "sec-elf", "report"]:
        ap.add_argument("--" + flag, type=Path, required=True)
    args = ap.parse_args()
    args.report.write_text(json.dumps(audit(args.fd.read_bytes(), args.sec_elf), indent=2) + "\n")
