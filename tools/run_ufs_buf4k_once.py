"""Offline verification or one attended RAM boot of the passive LK-buffer inspection.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_lk_map_once import ROOT, SEC as MAP_SEC, REQUIRED as MAP_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-buf4k-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-bounce-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-buf4k-20261121.json"
SEC = MAP_SEC | {"OculusGoPkg/SecMem/UfsHeaderBuffer.c", "OculusGoPkg/SecMem/UfsHeaderBuffer.h"}
REQUIRED = (MAP_INPUTS - {"OculusGoPkg/SecMem/UfsLkMap.inf"}) | SEC | {
    "OculusGoPkg/SecMem/UfsBuf4k.inf", "tools/run_ufs_buf4k_once.py", "tools/audit_lk_header_buffer.py",
    "tools/collect_ufs_layout.py", "tests/ufs_header_fd_qemu.py", "tests/ufs_data_fd_qemu.py",
    "tests/ufs_nop11_fd_qemu.py", "tests/ufs_nop11_bus.py", "tests/ufs_data_qemu.py",
}
GUID = "1c8b508f-0679-471f-9036-91f6186a04af"


def verify_reports(model, static, digest):
    require((static["status"], static["secOnly"], static["vectorsVerified"], static["transportLinked"])
            == ("PASS-STATIC", GUID, 16, False), "unexpected SEC transport or vectors")
    require(model["fdSha256"] == static["fdSha256"] == digest and model["outcome"] == "PASS-QEMU-BUF4K" and
            model["physicalGptRead"] == "UNKNOWN" and (model["candidate"], model["bytes"]) == ("0x918d7e80", 4096),
            "unexpected candidate or report")
    rows = model["cases"]
    require(len(rows) == 4 and {(r["el"],r["case"]) for r in rows} ==
            {(1,"valid"),(2,"valid"),(1,"unknown"),(1,"wrong-size")}, "missing passive trials")
    for row in rows:
        panel = row["panel"]
        heading = "UFS STOP      LKPG" if row["case"] == "wrong-size" else "UFS BUF4K     DONE"
        require(row["restored"] and row["firmwareDoorbells"] == row["mediaWrites"] == 0 and
                all(row[k] == [] for k in ("transfers","readExtents","mappedCandidateLeaves","gptSectorSha256")),
                "passive image used UFS")
        require(panel[0] == heading and panel[1] == "BUF  918D7E80" and panel[-1] == "CPU ONLY",
                "unexpected passive panel")


def reviewed(root, record):
    image, unit = verify_terminal_inputs(root, record, scope="terminal-ufs-buf4k",
        build_prefix="DEBUG-UFS_BUF4K-", sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS,
        validate_reports=verify_reports)
    path, raw = checked_file(root, record["containerManifest"], ("local",))
    manifest = json.loads(raw)
    require(path == image.with_suffix(".json") and manifest["imageSha256"] == record["image"]["sha256"]
            and manifest["fdSha256"] == record["fd"]["sha256"] and manifest["stockBootSha256"] == STOCK_SHA
            and manifest["dtbSha256"] == DTB_SHA and manifest["verification"]["roundtrip"] == "PASS",
            "different container")
    _, raw = checked_file(root, record["stockAudit"], ("docs",))
    stock = json.loads(raw)
    original = json.loads((root/PREVIOUS).read_bytes())["recovery"]["matchedBeforeAndOriginals"]
    require(stock["stockElfSha256"] == original["aboot_a"] and stock["cpuBuffer"] == "0x918d7e80"
            and stock["pageSizeWord"] == "0x918e18d4" and stock["endExclusive"] == "0x918d8e80"
            and stock["retainedBusOnPacific"] == "UNKNOWN", "missing stock provenance")
    _, published = checked_file(root, record["publishedModel"], ("docs",))
    _, local = checked_file(root, record["model"], ("build",))
    require(local == published, "different public evidence")
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-buf4k", measure)
