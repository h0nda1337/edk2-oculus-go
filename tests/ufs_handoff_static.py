"""Inspect the delivered UFS diagnostic firmware volume and its load instruction.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
from pathlib import Path
import struct

from sec_dxe_static import BASE, files, require, symbols, verify
from ufs_handoff_qemu import REGS

SEC_GUID = "5bc15fed-b682-4b88-b6a2-5d4c84c3a90e"


def inspect(fd, elf, sec_guid=SEC_GUID, inventories=None):
    info = verify(fd)
    names = symbols(elf)
    bias = int(info["secEntryAddress"], 16) - names["_ModuleEntryPoint"]
    def offset(name):
        return bias + names[name] - BASE
    volume = fd[0x1000:0x3be000]
    modules = [(kind, str(guid)) for kind, guid, _ in files(volume) if kind != 0xf0]
    require(modules == [(3, sec_guid)], f"Unexpected volume contents: {modules}")
    pos = offset("GoUfsRead32")
    require(struct.unpack_from("<4I", fd, pos) == (0xb9400002, 0xb9000022, 0x52800020, 0xd65f03c0),
            "Peripheral load wrapper differs from LDR W2,[X0]; STR W2,[X1]; return TRUE")
    vec = offset("UfsVectors")
    require((BASE + vec) % 2048 == 0, "Misaligned VBAR")
    for slot in range(16):
        pc = vec + 128 * slot
        word, = struct.unpack_from("<I", fd, pc)
        disp = ((word & 0x03ffffff) ^ 0x02000000) - 0x02000000
        require(word >> 26 == 5 and pc + disp * 4 == offset("UfsSync" if slot == 4 else "UfsStop"),
                "Unexpected vector target")
    lists = {"mSamples": REGS} if inventories is None else inventories
    for name, regs in lists.items():
        for i, (addr, label, _) in enumerate(regs):
            ptr, actual = struct.unpack_from("<QI", fd, offset(name) + i * 16)
            label_bytes = label.encode() + b"\0"
            require(actual == addr and BASE <= ptr < BASE + len(fd)
                    and fd[ptr - BASE:ptr - BASE + len(label_bytes)] == label_bytes,
                    f"Physical register inventory differs from review in {name}")
    return {"status": "PASS-STATIC", "fdSha256": info["sha256"], "secOnly": sec_guid,
            "mmioLoad": "LDR W2,[X0]", "vectorsVerified": 16,
            "registerAddresses": [hex(reg[0]) for regs in lists.values() for reg in regs]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ["fd", "sec-elf", "report"]:
        ap.add_argument("--" + flag, type=Path, required=True)
    a = ap.parse_args()
    a.report.write_text(json.dumps(inspect(a.fd.read_bytes(), a.sec_elf), indent=2) + "\n")
