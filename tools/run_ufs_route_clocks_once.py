"""Verify the AGGRE2 clock panel or perform its attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_handoff_once import ROOT, REQUIRED as HANDOFF_INPUTS, SEC as HANDOFF_SEC
from terminal_review import verify_terminal_inputs


REVIEW = "docs/evidence/ufs-route-clocks-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-prdt-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-route-clocks-20261121.json"
STOCK = "docs/evidence/ufs-route-clocks-stock-20261121.json"
PUBLISHED = "docs/evidence/ufs-route-clocks-fd-qemu-20261121.json"
GUID = "8c0a0ea3-c44c-4076-bbfd-ee061713e160"
SEC = HANDOFF_SEC | {"OculusGoPkg/SecMem/UfsRouteClocks.c", "OculusGoPkg/SecMem/UfsPanel.h"}
REQUIRED = (HANDOFF_INPUTS - {"OculusGoPkg/SecMem/UfsHandoff.inf"}) | SEC | {
    "OculusGoPkg/SecMem/UfsRouteClocks.inf", "scripts/build-edk2.ps1",
    "tests/ufs_route_clocks_fd_qemu.py", "tools/verify_sec_visual_data.py",
    "tools/audit_ufs_route_clocks.py", "tools/run_ufs_route_clocks_once.py",
}
LABELS = ["DOM", "NAX", "NAH", "SAX", "SAH"]
ADDRESSES = ["0x383004", "0x383008", "0x38300c", "0x38301c", "0x383020"]
CASES = {
    "active": 5, "domain-off": 1, "collapse-request": 1, "branches-off": 5,
    **{f"invalid-{name.lower()}": i for i, name in enumerate(LABELS, 1)},
    "load-abort": 4, "wrong-board": 0,
}


def verify_reports(model, static, digest):
    require(model["fdSha256"] == static["fdSha256"] == digest and
            model["outcome"] == "PASS-QEMU-ROUTE-CLOCKS" and model["physicalBus"] == "UNKNOWN",
            "wrong clock model")
    require(static["status"] == "PASS-STATIC" and static["secOnly"] == GUID and
            static["vectorsVerified"] == 16 and static["mmioLoad"] == "LDR W2,[X0]" and
            static["registerAddresses"] == ADDRESSES, "unexpected load inventory in SEC")
    require(model["watchedRangesEndExclusive"] ==
            [["0x300000", "0x390000"], ["0x624000", "0x626500"], ["0x1680000", "0x16a0000"]],
            "unexpected GCC, UFS or SMMU watch range")
    rows = model["cases"]
    wanted = {(el, case) for el in (1, 2) for case in CASES}
    require(len(rows) == len(wanted) and {(r["el"], r["case"]) for r in rows} == wanted,
            "missing or duplicate clock cases")
    for row in rows:
        require(row["registerLoads"] == LABELS[:CASES[row["case"]]] and
                row["peripheralStores"] == 0 and row["expectedScreenVerified"] is True,
                "unexpected peripheral access sequence or incomplete display evidence")


def reviewed(root, record):
    image, serial = verify_terminal_inputs(
        root, record, scope="terminal-ufs-route-clocks", build_prefix="DEBUG-UFS_ROUTE_CLOCKS-",
        sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS, validate_reports=verify_reports)
    path, content = checked_file(root, record["containerManifest"], ("local",))
    manifest = json.loads(content)
    require(path == image.with_suffix(".json") and manifest["imageSha256"] == record["image"]["sha256"]
            and manifest["fdSha256"] == record["fd"]["sha256"] and manifest["stockBootSha256"] == STOCK_SHA
            and manifest["dtbSha256"] == DTB_SHA and manifest["verification"]["roundtrip"] == "PASS",
            "unexpected Android container manifest")
    require(record["stockAudit"]["file"] == STOCK and record["publishedModel"]["file"] == PUBLISHED,
            "unexpected published evidence path")
    _, content = checked_file(root, record["stockAudit"], ("docs",))
    audit = json.loads(content)
    inventory = json.loads((root / "docs/evidence/partitions.json").read_bytes())
    stock_rpm, = [p for p in inventory["partitions"] if p["name"] == "rpm_a"]
    domains = [row["physicalAddress"] for row in audit["domains"] if row["name"] == "VDD_AGGRE2_NOC"]
    require(audit["stockRpmSha256"] == stock_rpm["sha256"] and
            domains + [r["physicalAddress"] for r in audit["aggre2Branches"]] == ADDRESSES and
            audit["physicalUfsStreamId"] == audit["busAddressForCpuPage80441000"] == "UNKNOWN",
            "unexpected stock RPM register evidence")
    _, published = checked_file(root, record["publishedModel"], ("docs",))
    _, local = checked_file(root, record["model"], ("build",))
    require(published == local, "published QEMU report differs from local build")
    return image, serial


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-route-clocks", measure)
