"""Verify the stock boot exit and the storage-specific cleanup branch on Pacific.

This offline audit reads the pinned slot-A ELF and the recorded entry panel.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_lk_ufs_dma import audit, require

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "docs/evidence/ufs-handoff-transfer-20261121.json"


def inspect(data, panel_bytes):
    stock = audit(data)
    segment = stock["ptLoad"]
    base, offset, size = (int(segment[key], 16) for key in ("va", "fileOffset", "fileBytes"))

    def read(address, length):
        require(base <= address <= base + size - length, "outside file-backed LK segment")
        pos = offset + address - base
        return data[pos:pos + length]

    def word(pc):
        return struct.unpack("<I", read(pc, 4))[0]

    def branch(pc, opcode, expected):
        # ARM-state PC-relative B/BL: the signed displacement is relative to PC + 8.
        instruction = word(pc)
        require(instruction >> 24 == opcode, f"unexpected branch kind at {pc:#x}")
        displacement = instruction & 0xffffff
        if displacement & 0x800000:
            displacement -= 0x1000000
        require(pc + 8 + displacement * 4 == expected, f"branch target at {pc:#x}")

    def mov_pair(lo, hi, register):
        result = 0
        for pc, opcode, shift in ((lo, 0xe3000000, 0), (hi, 0xe3400000, 16)):
            w = word(pc)
            require((w & 0xfff0f000) == (opcode | register << 12), f"unexpected MOVW/T at {pc:#x}")
            result |= (((w >> 4) & 0xf000) | (w & 0xfff)) << shift
        return result

    def instructions(pc, expected):
        require(all(word(pc + i * 4) == value for i, value in enumerate(expected)),
                f"unexpected instruction sequence at {pc:#x}")

    # Two image-header call sites and the registered temporary-boot handler
    # converge on one coordinator. Classify the storage callbacks by the
    # enclosing branches, not merely by an embedded function-name string.
    require(read(word(0x91880f48), 5) == b"boot\0" and word(0x91880f4c) == 0x9183cd7c,
            "unexpected boot command record")
    common = 0x9183a9e4
    callers = (0x9183b4f8, 0x9183bc14, 0x9183d1bc)
    for site in callers:
        branch(site, 0xeb, common)
    branch(0x9183aabc, 0xeb, 0x918002b8)

    selector = 0x9182da78
    for call in (0x91800ec4, 0x91810ed8, 0x918002d4):
        branch(call, 0xeb, selector)
        require(word(call + 4) == 0xe3500000, f"expected CMP R0,#0 after {call:#x}")
    branch(0x91800ecc, 0x1a, 0x91800dd8)  # nonzero skips UFS init
    require(mov_pair(0x91800ed0, 0x91800ed4, 3) == int(stock["ufsHbaVa"], 16)
            and word(0x91800ed8) == 0xe3a02901 and word(0x91800edc) == 0xe3402062
            and word(0x91800ee4) == 0xe5832004, "controller initialization resource")
    branch(0x91800ee8, 0xeb, 0x9182b9e4)
    branch(0x91810ee0, 0x0a, 0x91811008)  # zero takes the reviewed UFS read path

    # Only the nonzero selection enters the sleep block; on the zero path
    # the next instruction calls the common teardown code for the board.
    branch(0x918002dc, 0x1a, 0x9180032c)
    branch(0x918002e0, 0xeb, 0x9180c58c)
    branch(0x918002e8, 0x1a, 0x91800348)
    branch(0x91800338, 0xeb, 0x918107f0)
    branch(0x9180033c, 0xeb, 0x9180c58c)
    branch(0x91800344, 0x0a, 0x918002ec)
    function_name = b"mmc_put_card_to_sleep\0"
    require(read(mov_pair(0x91810864, 0x9181086c, 1), len(function_name)) == function_name,
            "storage sleep routine identity")
    require(read(mov_pair(0x918003a8, 0x918003ac, 0), 19) == b"RPMB uninit failed\n",
            "separate RPMB teardown diagnostic")

    # The LK initializer starts both lists. The board-level teardown test
    # above does not stop them on the UFS selection via the MMC helper.
    require(word(0x9182bac4) == 0xe3a03001 and word(0x9182baf4) == 0xe5962004
            and word(0x9182bafc) == 0xe5962004 and word(0x9182baf8) == 0xe5823080
            and word(0x9182bb00) == 0xe5823060, "both list run/stop writes")

    # Separate CPU cache/MMU cleanup from the storage callbacks. The final
    # wrapper has an external firmware dependency whose behavior this ELF
    # cannot certify. Record the handoff scope without inferring DMA policy.
    branch(0x9183aad8, 0x0a, 0x9183abdc)
    branch(0x9183abe0, 0xea, 0x9183aadc)
    branch(0x9183aadc, 0xeb, 0x918041a0)
    branch(0x9183aae4, 0xeb, 0x91834564)
    branch(0x9183aae8, 0xeb, 0x918351fc)
    # ARM SCTLR is CP15 c1,c0,0. Cache routine clears C and I; the MMU
    # routine clears M through separate read/write wrappers.
    require(word(0x9183aae0) == 0xe3a00003 and word(0x9183457c) == 0xee110f10
            and word(0x91834588) == 0xe3c00004 and word(0x91834590) == 0xee010f10,
            "SCTLR data cache enable")
    instructions(0x918345a8, [0xee110f10, 0xe3c00a01, 0xee010f10])
    branch(0x91835218, 0xeb, 0x91834880)
    branch(0x91835220, 0xeb, 0x91834888)
    require(word(0x91834880) == 0xee110f10 and word(0x9183521c) == 0xe3c00001
            and word(0x91834888) == 0xee010f10, "SCTLR MMU enable")
    require(word(0x9183aaf4) == 0xe5962038 and mov_pair(0x9183aaf8, 0x9183aafc, 3) == 0x644d5241
            and word(0x9183ab00) == 0xe1520003, "ARM64 Image header selection")
    branch(0x9183ab04, 0x0a, 0x9183abb8)
    branch(0x9183abd8, 0xea, 0x9181f788)
    require(mov_pair(0x9181f7e4, 0x9181f7e8, 3) == mov_pair(0x9181f7fc, 0x9181f800, 3)
            and word(0x9181f7ec) == 0xe1c300f0 and word(0x9181f804) == 0xe1c304f8,
            "ARM64 wrapper argument fields")
    branch(0x9183d18c, 0xeb, 0x91841968)
    require(word(0x91841984) == 0xe593300c and word(0x9184198c) == 0xe12fff33,
            "late callback before the shared coordinator")

    # Trace the selected Fastboot transport callback, which otherwise looks
    # like a generic shutdown. The board getter and comparison operand are
    # the same NUL-terminated name. Pin the registration and dispatch slot.
    branch(0x918416bc, 0xeb, 0x91800bf8)
    getter = mov_pair(0x91800c0c, 0x91800c10, 0)
    require(getter == mov_pair(0x918416c0, 0x918416c4, 1) and read(getter, 4) == b"dwc\0",
            "board USB controller selection")
    branch(0x918416c8, 0xeb, 0x9184dfd4)
    branch(0x918416d0, 0x0a, 0x918418b0)
    require(word(0x918416cc) == 0xe3500000
            and mov_pair(0x918418b4, 0x918418bc, 4) == mov_pair(0x91841974, 0x91841978, 3)
            and mov_pair(0x918418dc, 0x918418e4, 1) == 0x91832788
            and word(0x918418ec) == 0xe584100c, "DWC callback registration")
    require(word(0x918327a4) == 0xe3a01000, "request USB device STOP")
    branch(0x918327b4, 0xeb, 0x918303d0)
    require(word(0x918303dc) == 0xe30c2704, "DWC3 DCTL offset")
    instructions(0x918303f0, [0xe790c002, 0xe3ccc102, 0xe18c1f81, 0xe7801002])

    panel = json.loads(panel_bytes)
    require(panel["scope"] == "terminal-ufs-handoff" and panel["temporaryBootCommandIssued"] is True
            and panel["partitionWriteCommandIssued"] is False
            and panel["matchedOriginalsBefore"]["aboot_a"] == stock["stockAbootSha256"]
            and panel["bootloader"]["slot"] == "_a", "entry panel provenance")
    registers = {k: int(panel["physicalPanel"]["registersHex"][k], 16)
                 for k in ("VER", "HCE", "TRR", "TRD", "TMR", "TMD")}
    require(registers == {"VER": 0x10100, "HCE": 1, "TRR": 1, "TRD": 0, "TMR": 1, "TMD": 0},
            "unexpected observed UFS state")

    return {
        "scope": "Offline stock LK slot A and one prior read-only SEC observation on temporary boot",
        "stockAbootSha256": stock["stockAbootSha256"],
        "directHandoffsReviewed": [hex(pc) for pc in callers], "commonCoordinator": hex(common),
        "storageSelector": hex(selector),
        "ufsBranch": {"selectorResult": 0, "boardInitSite": "0x91800ec4",
                      "nativeReadSite": "0x91810ed8", "targetCleanupSite": "0x918002d4",
                      "callsMmcCardSleepViaThisBranch": False},
        "lateTemporaryBootCallback": {
            "transport": "dwc", "slotOffset": "0xc", "action": "clear DWC3 DCTL RUN_STOP",
            "meaning": "USB device controller stop on the statically selected Fastboot transport",
            "registerReference": "https://github.com/facebookincubator/oculus-linux-kernel/blob/"
                                 "9475755c1a328a7b873721897ef339a8ad35c86a/drivers/usb/dwc3/core.h#L266"
        },
        "otherStorageBranch": {"selectorResult": "nonzero", "directCallSite": "0x91800338",
                               "routineIdentity": "mmc_put_card_to_sleep"},
        "separateRpmbCleanup": "The board checks an RPMB uninit result; this does not describe the HCI queues.",
        "lateArm64Path": {"kernelMagicCheck": "0x9183aaf4", "wrapperBranch": "0x9183abd8",
                          "cpuCacheCleanupCall": "0x9183aae4", "cpuMmuCleanupCall": "0x9183aae8"},
        "existingPhysicalEvidence": {"file": PANEL.name, "sha256": hashlib.sha256(panel_bytes).hexdigest(),
                                     "registers": registers, "bothListsRunning": True,
                                     "bothDoorbellsClear": True},
        "conclusion": "No stopped-list handoff at the sampled SEC entry. Exclusive release to DXE is UNKNOWN.",
        "limits": ["This is the normal successful ARM64 exit, not every boot mode or every firmware image.",
                   "The USB callback was resolved from its static registration, not a runtime trace. Other board services "
                   "and the external ARM64 handoff are not a proof about all side effects.",
                   "The entry panel samples final state; it cannot exclude a prior stop and restart.",
                   "CPU cache/MMU teardown and the two image-handoff arguments do not supply a "
                   "UFS bus address for an allocation that is made later by DXE."]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aboot", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.aboot.read_bytes(), PANEL.read_bytes()), indent=2))
