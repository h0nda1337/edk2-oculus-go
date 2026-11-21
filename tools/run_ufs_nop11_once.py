"""Verify the Pacific NOP package offline or run the attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_lk_map_once import ROOT, SEC as MAP_SEC, REQUIRED as MAP_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-nop11-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-lk-map-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-nop11-20261121.json"
SEC = MAP_SEC | {"OculusGoPkg/SecMem/UfsNop11.c", "OculusGoPkg/SecMem/UfsNop11Ring.S"}
REQUIRED = SEC | (MAP_INPUTS - {"OculusGoPkg/SecMem/UfsLkMap.inf"}) | {
    "OculusGoPkg/SecMem/UfsNop11.inf", "tests/ufs_nop11_bus.py", "tests/ufs_nop11_fd_qemu.py",
    "tests/ufs_nop11_window_guest.c", "tests/ufs_nop11_window_qemu.py", "tools/run_ufs_nop11_once.py",
}
GUID = "c965ead6-00b2-46b9-a899-324437c63682"
EXPECTED = {
    "nop": ("NOP IN", "DONE", 1), "bad-tag": ("BAD", "RESPONSE", 1),
    "software-busy": ("STOP", "STATE", 0), "empty-prior": ("STOP", "NO PRIOR OCS", 0),
    "different-cpu-map": ("UNKNOWN", "FD MAP", 0),
}


def verify_reports(model, static, digest):
    require(model["outcome"] == "PASS-QEMU-FD-NOP11" and static["status"] == "PASS-STATIC"
            and model["fdSha256"] == static["fdSha256"] == digest, "FD report mismatch")
    require(static["secOnly"] == GUID and static["vectorsVerified"] == 16 and
            (static["registerStore"], static["value"]) == ("0x624058", 2)
            and static["windowSubmission"] is False, "unexpected SEC module or submission")
    require(model["physicalWindowDma"] == "UNKNOWN" and
            model["ordinaryLuns"] == model["scsiCommands"] == model["queryCommands"] == 0,
            "unexpected model storage access")
    rows = model["cases"]
    require(len(rows) == 2 * len(EXPECTED) and {(r["el"], r["case"]) for r in rows} ==
            {(el, name) for el in (1, 2) for name in EXPECTED}, "missing FD cases")
    for row in rows:
        observed = (row["state"], row["label"], row["guestDoorbells"])
        require(observed == EXPECTED[row["case"]] and row["lkPageRestored"] is True and
                row["fdWindowUnchanged"] is True, "unexpected FD outcome")


def reviewed(root, record):
    image, unit = verify_terminal_inputs(
        root, record, scope="terminal-ufs-nop11", build_prefix="DEBUG-UFS_NOP11-",
        sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS, validate_reports=verify_reports)
    path, raw = checked_file(root, record["containerManifest"], ("local",))
    manifest = json.loads(raw)
    require(path == image.with_suffix(".json") and manifest["imageSha256"] == record["image"]["sha256"]
            and manifest["fdSha256"] == record["fd"]["sha256"] and manifest["dtbSha256"] == DTB_SHA
            and manifest["stockBootSha256"] == STOCK_SHA and manifest["verification"]["roundtrip"] == "PASS",
            "container manifest mismatch")
    _, raw = checked_file(root, record["lkHandoff"], ("docs",))
    prior = json.loads(raw)
    require(record["lkHandoff"]["file"] == PREVIOUS and prior["physicalPanel"]["transferList"] == "0x918EE400"
            and prior["physicalPanel"]["taskManagementList"] == "0x918EEC00" and
            prior["recovery"]["result"] == "PASS-READONLY", "incompatible handoff")
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-nop11", measure)
