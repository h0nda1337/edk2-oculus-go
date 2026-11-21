"""Validate the data-in control image or run one attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_nop11_once import ROOT, SEC as NOP_SEC, REQUIRED as NOP_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-data-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-nop11-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-data-20261121.json"
SEC = NOP_SEC | {"OculusGoPkg/SecMem/UfsData.c", "OculusGoPkg/SecMem/UfsData.h"}
REQUIRED = (NOP_INPUTS - {"OculusGoPkg/SecMem/UfsNop11.inf"}) | SEC | {
    "OculusGoPkg/SecMem/UfsData.inf", "tests/ufs_data_guest.c", "tests/ufs_data_fd_qemu.py",
    "tests/ufs_data_qemu.py", "tools/run_ufs_data_once.py",
}

def verify_reports(model, static, digest):
    require(model["outcome"] == "PASS-QEMU-FD-DATA" and static["status"] == "PASS-STATIC"
            and model["fdSha256"] == static["fdSha256"] == digest, "FD report mismatch")
    require(static["secOnly"] == "28b403d4-daca-48ec-a821-683f1404c003" and
            (static["vectorsVerified"],static["registerStore"],static["value"]) == (16,"0x624058",2),
            "unexpected SEC module or register store")
    require(model["physicalWindowDma"] == "UNKNOWN" and model["mediaReads"] == model["mediaWrites"] == 0,
            "unexpected physical claim or media access")
    rows = model["cases"]
    require(len(rows) == 4 and {(r["el"],r["case"]) for r in rows} ==
            {(el,name) for el in (1,2) for name in ("pacific-entry","qemu-map")}, "missing entry tests")
    for row in rows:
        mapped = row["case"] == "qemu-map"
        control = "0x918eef80"
        targets = [(control,control)] * 2
        if mapped:
            targets.extend((hex(0x80440000+i),hex(0x88000000+i)) for i in (0,0x1ff8,0x2000,0x3ff8))
        completions = row["completions"]
        require([(r["cpu"],r["bus"]) for r in completions] == targets and
                [(r["status"],r["bytes"]) for r in completions] ==
                [(2,"a5"*8)]+[(0,"0011ffff00001000")]*(len(targets)-1), "unexpected DMA completion")
        require(row["restored"] is True and row["panel"][-1] ==
                ("WINDOW RESTORED" if mapped else "WINDOW DMA UNTESTED"), "unexpected terminal panel")

def reviewed(root, record):
    image, unit = verify_terminal_inputs(root,record,scope="terminal-ufs-data",
        build_prefix="DEBUG-UFS_DATA-",sec_sources=SEC,required=REQUIRED,previous_record=PREVIOUS,
        validate_reports=verify_reports)
    path, raw = checked_file(root, record["containerManifest"], ("local",))
    manifest = json.loads(raw)
    require(path == image.with_suffix(".json") and manifest["imageSha256"] == record["image"]["sha256"]
            and manifest["fdSha256"] == record["fd"]["sha256"] and manifest["dtbSha256"] == DTB_SHA
            and manifest["stockBootSha256"] == STOCK_SHA and manifest["verification"]["roundtrip"]=="PASS",
            "container manifest mismatch")
    _, raw = checked_file(root, record["priorNop"], ("docs",))
    prior = json.loads(raw)
    require(record["priorNop"]["file"] == PREVIOUS and prior["physicalLkQueueNop"] == "CONFIRMED" and
            prior["physicalPanel"]["descriptorAddress"] == "0x918EE420" and
            prior["physicalPanel"]["commandAddress"] == "0x918EEE80", "physical NOP evidence mismatch")
    _, published = checked_file(root, record["publishedModel"], ("docs",))
    _, local_model = checked_file(root, record["model"], ("build",))
    require(published == local_model, "published FD test differs from local result")
    _, raw = checked_file(root, record["virtualDma"], ("docs",))
    model = json.loads(raw)
    require(model["outcome"] == "PASS-QEMU-DATA-IN" and model["physicalWindowDma"] == "UNKNOWN" and
            model["mediaReads"] == model["mediaWrites"] == 0 and model["cpuWindow"]=="0x80440000" and
            model["windowBytes"] == 16384 and model["probeBytesPerPage"] == 8, "invalid window report")
    require(len(model["cases"]) == 10 and {r["case"]: r["pageMask"] for r in model["cases"]} ==
            dict(translated=15, scattered=15, **{"aliased-target":3, "last-page-denied":7,
                "no-window-map":0, "alias-list":0, "partial-map":0, "dirty-window":0,
                "wrong-geometry":0, "wrong-iova":0}), "missing map coverage")
    return image, unit

def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)

if __name__=="__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-data", measure)
