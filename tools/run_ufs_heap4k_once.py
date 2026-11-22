"""Verify the passive UFS and LK heap inspection or perform its attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_lk_map_once import ROOT, SEC as MAP_SEC, REQUIRED as MAP_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-heap4k-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-zero4k-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-heap4k-20261121.json"
GUID = "c4813517-f568-49eb-bb60-d8db839c96d2"
SEC = MAP_SEC | {"OculusGoPkg/SecMem/UfsHeap.c"}
REQUIRED = (MAP_INPUTS - {"OculusGoPkg/SecMem/UfsLkMap.inf"}) | SEC | {
    "OculusGoPkg/SecMem/UfsHeap.inf", "tools/run_ufs_heap4k_once.py", "tools/audit_lk_response_heap.py",
    "tests/ufs_heap_fd_qemu.py", "tests/ufs_header_fd_qemu.py", "tests/ufs_data_fd_qemu.py",
    "tests/ufs_data_qemu.py", "tests/ufs_nop11_fd_qemu.py", "tests/ufs_nop11_bus.py",
}
CASES = {"free", "alias", "short", "metadata", "empty", "queue", "outside", "loop", "changing",
         "queue-listed-free", "stale-ocs", "wrong-offset"}


def verify_reports(model, static, digest):
    require(static["status"] == "PASS-STATIC" and static["secOnly"] == GUID and
            static["vectorsVerified"] == 16 and static["transportLinked"] is False, "unexpected SEC")
    require(model["fdSha256"] == static["fdSha256"] == digest and model["outcome"] == "PASS-QEMU-HEAP4K"
            and model["physicalFdBus"] == "UNKNOWN", "different model")
    rows = {(r["el"], r["case"]): r for r in model["cases"]}
    require(len(model["cases"]) == len(rows) and rows.keys() ==
            {(1, name) for name in CASES} | {(2, "free")}, "missing model cases")
    for row in rows.values():
        require(row["probeDoorbells"] == row["mediaCommands"] == 0 and row["panel"][-1] == "CPU ONLY",
                "probe issued a command")
    free, alias = rows[1, "free"], rows[1, "alias"]
    require(free["panel"] == alias["panel"] and free["panel"][0].endswith("CANDIDATE") and
            free["fixtureResponseCpu"] == free["fixtureResponseBus"] == alias["fixtureResponseBus"]
            and alias["fixtureResponseCpu"] != alias["fixtureResponseBus"], "missing nonidentity control")


def reviewed(root, record):
    image, unit = verify_terminal_inputs(root, record, scope="terminal-ufs-heap4k",
        build_prefix="DEBUG-UFS_HEAP4K-", sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS,
        validate_reports=verify_reports)
    path, raw = checked_file(root, record["containerManifest"], ("local",))
    manifest = json.loads(raw)
    require(path == image.with_suffix(".json") and manifest["imageSha256"] == record["image"]["sha256"]
            and manifest["fdSha256"] == record["fd"]["sha256"] and manifest["stockBootSha256"] == STOCK_SHA
            and manifest["dtbSha256"] == DTB_SHA and manifest["verification"]["roundtrip"] == "PASS",
            "different container")
    _, raw = checked_file(root, record["stockAudit"], ("docs",))
    stock = json.loads(raw)
    recovery = json.loads((root/PREVIOUS).read_bytes())["recovery"]["matchedBeforeAndOriginals"]
    require(stock["stockElfSha256"] == recovery["aboot_a"] and stock["responseOffsetBytes"] == 32 and
            stock["freeListHead"] == "0x918e3170" and stock["retainedBusOfFdPage"] == "UNKNOWN",
            "different LK evidence")
    _, published = checked_file(root, record["publishedModel"], ("docs",))
    _, local = checked_file(root, record["model"], ("build",))
    require(local == published, "different public evidence")
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-heap4k", measure)
