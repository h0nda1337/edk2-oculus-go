"""Offline inspection by default, one attended Pacific queue-register boot on request.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_handoff_once import ROOT, SEC as HANDOFF_SEC, REQUIRED as HANDOFF_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-queues-review-20261121.json"
LEDGER = "local/physical-attempts/ufs-queues-20261121.json"
PREVIOUS = "docs/evidence/ufs-handoff-transfer-20261121.json"
SEC = HANDOFF_SEC | {"OculusGoPkg/SecMem/UfsQueues.c", "OculusGoPkg/SecMem/UfsPanel.h"}
REQUIRED = SEC | (HANDOFF_INPUTS - {"OculusGoPkg/SecMem/UfsHandoff.inf"}) | {
    "OculusGoPkg/SecMem/UfsQueues.inf", "tests/ufs_queues_qemu.py", "tests/ufs_queue_dma_model.py",
    "tests/ufs_queues_static.py", "tools/run_ufs_queues_once.py"}


def verify_reports(model, static, digest):
    require(model["fdSha256"] == static["fdSha256"] == digest and model["outcome"] == "PASS-QEMU"
            and model["pacificDmaMapping"] == "UNKNOWN" and static["status"] == "PASS-STATIC"
            and static["secOnly"] == "e78bfd70-a2cc-465a-9908-4ea1c9e72426"
            and static["registerAddresses"][13:18] == ["0x624000", "0x624050", "0x624054", "0x624070", "0x624074"]
            and static["windowStart"] == model["windowCpuPa"] == "0x80440000"
            and static["initialWindowBytesVerified"] == model["windowBytes"] == 16384,
            "Queue probe build or register inventory differs")
    expected = {"stable32", "one-slot", "stable64", "last-32-bit-block", "adjacent-lists", "window-boundary",
                "gated", "hce-off", "unsupported-version", "host-error", "list-stopped", "busy",
                "base-changed", "door-changed", "bad-cap", "zero-base", "alignment", "32-bit-high",
                "end-overflow", "overlap", "fd-alias", "reserved-node", "reservation-block",
                "last-word-dirty", "load-abort", "wrong-board"}
    rows = model["cases"]
    require(len(rows) == 2 * len(expected) and {(r["el"], r["case"]) for r in rows} ==
            {(el, case) for el in (1, 2) for case in expected}
            and all(r["writesToController"] == r["unapprovedRamStores"] == 0 for r in rows),
            "Incomplete QEMU queue-probe evidence")


def reviewed(root, record):
    image, unit = verify_terminal_inputs(root, record, scope="terminal-ufs-queues", build_prefix="DEBUG-UFS_QUEUES-",
                                         sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS,
                                         validate_reports=verify_reports)
    _, raw = checked_file(root, record["virtualDma"], ("docs",))
    model = json.loads(raw)
    require(model["outcome"] == "PASS-QEMU-PCI-DMA" and model["diskBackends"] == model["scsiCommands"] == 0
            and model["ufsQueries"] == 0 and model["pacificDmaMapping"] == "UNKNOWN"
            and {n["ucd"] for n in model["nopTransfers"]} == {hex(0x80440000 + i * 4096) for i in range(4)}
            and all(n["ocs"] == 0 and n["responseType"] == "NOP IN" for n in model["nopTransfers"]),
            "Unexpected host-only DMA experiment")
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-queues", measure)
