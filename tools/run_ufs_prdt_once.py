"""Verify, or perform one attended RAM boot of the CPU-only native PRDT observer.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_lk_map_once import ROOT, SEC as MAP_SEC, REQUIRED as MAP_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-prdt-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-heap4k-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-prdt-20261121.json"
GUID = "7445d27c-1a27-4630-813f-09c91572c3fe"
SEC = MAP_SEC | {"OculusGoPkg/SecMem/UfsPrdt.c"}
REQUIRED = (MAP_INPUTS - {"OculusGoPkg/SecMem/UfsLkMap.inf"}) | SEC | {
    "OculusGoPkg/SecMem/UfsPrdt.inf", "tools/run_ufs_prdt_once.py", "tools/audit_lk_prdt.py",
    "tests/ufs_prdt_fd_qemu.py", "tests/ufs_header_fd_qemu.py", "tests/ufs_data_fd_qemu.py",
    "tests/ufs_data_qemu.py", "tests/ufs_nop11_fd_qemu.py", "tests/ufs_nop11_bus.py",
}
CASES = {"capacity","other-backing","native-read","native-read16","partial","short-read","two-prds","gap",
         "zero-prd","moved","bounds","changed","stale-tag","bad-ocs"}


def verify_reports(model, static, digest):
    require((static["status"],static["secOnly"],static["vectorsVerified"],static["transportLinked"])
            == ("PASS-STATIC",GUID,16,False), "different SEC")
    require(model["fdSha256"]==static["fdSha256"]==digest and model["outcome"]=="PASS-QEMU-PRDT"
            and model["physicalFdBus"]=="UNKNOWN", "different QEMU report")
    rows = {(x["el"],x["case"]):x for x in model["cases"]}
    require(len(model["cases"])==len(rows) and rows.keys()=={(1,c) for c in CASES}|{(2,"capacity")},
            "incomplete model")
    for row in rows.values():
        require(row["firmwareDoorbells"]==row["mediaReads"]==row["mediaWrites"]==0
                and row["panel"][7]=="CPU ONLY", "unexpected firmware activity")
    identity, alias = rows[1,"capacity"], rows[1,"other-backing"]
    require(identity["panel"]==alias["panel"] and identity["fixtureCapacityCpu"]==identity["fixtureCapacityBus"]
            ==alias["fixtureCapacityBus"] and alias["fixtureCapacityBus"]!=alias["fixtureCapacityCpu"],
            "missing alias test")


def reviewed(root, record):
    image, unit = verify_terminal_inputs(root,record,scope="terminal-ufs-prdt",build_prefix="DEBUG-UFS_PRDT-",
        sec_sources=SEC,required=REQUIRED,previous_record=PREVIOUS,validate_reports=verify_reports)
    path, raw = checked_file(root,record["containerManifest"],("local",))
    manifest=json.loads(raw)
    require(path==image.with_suffix(".json") and manifest["imageSha256"]==record["image"]["sha256"]
            and manifest["fdSha256"]==record["fd"]["sha256"] and manifest["stockBootSha256"]==STOCK_SHA
            and manifest["dtbSha256"]==DTB_SHA and manifest["verification"]["roundtrip"]=="PASS","wrong image")
    _, raw = checked_file(root,record["stockAudit"],("docs",))
    audit=json.loads(raw)
    prev=json.loads((root/PREVIOUS).read_bytes())
    require(audit["stockElfSha256"]==prev["recovery"]["matchedBeforeAndOriginals"]["aboot_a"]
            and audit["observedUcd"]==prev["observation"]["ucdBusFromUtrd"]=="0x918fdf00"
            and audit["probeCpuLimitExclusive"]=="0x918fe000" and audit["directFdBus"]=="UNKNOWN",
            "wrong native evidence")
    _, published=checked_file(root,record["publishedModel"],("docs",))
    _, local=checked_file(root,record["model"],("build",))
    require(published==local,"published result differs")
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root,LEDGER,image,tool,serial,preflight,report,output)


if __name__=="__main__":
    attended_main(ROOT,REVIEW,LEDGER,reviewed,"ufs-prdt",measure)
