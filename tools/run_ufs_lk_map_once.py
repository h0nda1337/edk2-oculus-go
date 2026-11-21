"""Inspect the passive LK map image offline or submit its reviewed attended trial.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_queues_once import ROOT, SEC as QUEUE_SEC, REQUIRED as QUEUE_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-lk-map-review-20261121.json"
LEDGER = "local/physical-attempts/ufs-lk-map-20261121.json"
PREVIOUS = "docs/evidence/ufs-queues-transfer-20261121.json"
SEC = QUEUE_SEC | {"OculusGoPkg/SecMem/UfsLkMap.c"}
REQUIRED = (QUEUE_INPUTS - {"OculusGoPkg/SecMem/UfsQueues.inf"}) | SEC | {
    "OculusGoPkg/SecMem/UfsLkMap.inf", "scripts/build-edk2.ps1", "tests/ufs_lk_map_qemu.py",
    "tests/ufs_lk_nop_qemu.py", "tests/ufs_lk_nop_guest.c", "tools/audit_lk_ufs_dma.py",
    "tools/run_ufs_lk_map_once.py"}
GUID = "64982274-3dc2-429a-ae32-238e3b72362a"


def verify_reports(model, static, digest):
    require(model["outcome"] == "PASS-QEMU" and static["status"] == "PASS-STATIC" and
            model["fdSha256"] == static["fdSha256"] == digest and model["physicalDma"] == "UNKNOWN" and
            static["secOnly"] == GUID and static["vectorsVerified"] == 16 and
            static["windowCpuPa"] == "0x80440000" and static["windowBytes"] == 16384, "unreviewed FD")
    cases = {"identity-5000", "identity-6000", "identity-7000", "changed-context", "high-queue",
             "foreign-table", "foreign-table-high", "empty-leaf", "fd-alias", "heap-alias", "above-4g",
             "unstable-leaf", "changed-hci", "busy-before-map", "cpu-window-dirty"}
    rows = model["cases"]
    require(len(rows) == len(cases)*2 and {(r["el"], r["case"]) for r in rows} ==
            {(el, name) for el in (1, 2) for name in cases} and
            all((r["state"] == "LK MAP" and r["label"] == "MATCH") == r["case"].startswith("identity-")
                and r["controllerWrites"] == r["unapprovedRamWrites"] == 0 for r in rows), "missing FD tests")


def reviewed(root, record):
    image, unit = verify_terminal_inputs(root, record, scope="terminal-ufs-lk-map",
                  build_prefix="DEBUG-UFS_LK_MAP-", sec_sources=SEC, required=REQUIRED,
                  previous_record=PREVIOUS, validate_reports=verify_reports)
    _, raw = checked_file(root, record["stockAudit"], ("docs",))
    stock = json.loads(raw)
    recovered = json.loads((root/PREVIOUS).read_bytes())["recovery"]["matchedBeforeAndOriginals"]
    require(stock["stockAbootSha256"] == recovered["aboot_a"] and stock["ufsHbaVa"] == "0x918e3230"
            and stock["cpuTtbr0"] == "0x918e4000" and stock["cpuTablePoolPages"] == 3, "wrong LK analysis")
    _, raw = checked_file(root, record["virtualDma"], ("docs",))
    model = json.loads(raw)
    require(model["outcome"] == "PASS-QEMU-TCG-NOP" and model["pacificDma"] == "UNKNOWN" and
            model["ordinaryLuns"] == model["scsiCommands"] == model["queryCommands"] == 0 and
            sum(row["nopCount"] for row in model["cases"]) == 4 and
            {row["response"] for row in model["cases"] if row.get("ocs") == 0} ==
            {hex(0x80440fe0 + p*4096) for p in range(4)} and
            any(row.get("pendingQueueRetained") and row.get("responseUntouched") and
                row["smmu"] == "GBPA.ABORT" for row in model["cases"]), "virtual NOP evidence")
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-lk-map", measure)
