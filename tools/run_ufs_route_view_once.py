"""Verify the passive ANOC2 view or submit its reviewed, attended RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_route_clocks_once import (
    ADDRESSES as CLOCK_ADDRESSES, LABELS as CLOCK_LABELS, ROOT, SEC, STOCK,
    REQUIRED as CLOCK_INPUTS,
)
from terminal_review import verify_terminal_inputs


REVIEW = "docs/evidence/ufs-route-view-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-route-clocks-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-route-view-20261121.json"
FDT_AUDIT = "docs/evidence/ufs-stream-topology-stock-20261121.json"
PUBLISHED = "docs/evidence/ufs-route-view-fd-qemu-20261121.json"
GUID = "561537ce-d1cf-4251-a732-23809d46b55f"
REQUIRED = (CLOCK_INPUTS - {"OculusGoPkg/SecMem/UfsRouteClocks.inf"}) | {
    "OculusGoPkg/SecMem/UfsRouteView.inf", "tests/ufs_route_view_fd_qemu.py",
    "tools/run_ufs_route_view_once.py", "tools/audit_ufs_stream_topology.py", "tools/audit_ufs_bus_pages.py",
}
LABELS = CLOCK_LABELS + ["ID0", "ID1", "ID2", "CR0"]
VIEW_OFFSETS = (0x20, 0x24, 0x28, 0)
VIEW_BASE = 0x1680000
ADDRESSES = CLOCK_ADDRESSES + [hex(VIEW_BASE + offset) for offset in VIEW_OFFSETS]
# Independent expectation of the terminal heading and how many registers were read.
CASES = {
    "active": (9, "ROUTE"), "clientpd-set": (9, "ROUTE"), "cr0-zero": (9, "ROUTE"),
    "dt-positive-rewrite": (9, "ROUTE"), "domain-off": (1, "STOP"), "collapse-request": (1, "STOP"),
    **{f"gated-{name.lower()}": (i, "STOP") for i, name in enumerate(CLOCK_LABELS[1:], 2)},
    "zero-clock": (5, "STOP"), "transition": (4, "STOP"),
    "no-stages": (6, "INVALID"), "no-banks": (7, "INVALID"), "invalid-bank-count": (7, "INVALID"),
    "invalid-id2": (8, "INVALID"), "invalid-cr0": (9, "INVALID"),
    "abort-id0": (6, "FAULT"), "abort-cr0": (9, "FAULT"),
    **{case: (0, "") for case in ("wrong-board", "wrong-reg", "wrong-compatible", "wrong-range",
                                   "disabled-node", "static-cb", "secure-alias", "missing-skip-init")},
}


def verify_reports(model, static, digest):
    require(model["outcome"] == "PASS-QEMU-ROUTE-VIEW" and model["physicalBus"] == "UNKNOWN"
            and model["fdSha256"] == static["fdSha256"] == digest, "unexpected FD or model")
    require(static["status"] == "PASS-STATIC" and static["secOnly"] == GUID and
            static["vectorsVerified"] == 16 and static["mmioLoad"] == "LDR W2,[X0]" and
            static["registerAddresses"] == ADDRESSES, "unexpected SEC or register addresses")
    require(model["watchedRangesEndExclusive"] ==
            [["0x300000", "0x390000"], ["0x624000", "0x626500"], ["0x1680000", "0x16a0000"]],
            "unexpected MMIO watch ranges")
    rows = model["cases"]
    expected = {(el, case) for el in (1, 2) for case in CASES}
    require(len(rows) == len(expected) and {(r["el"], r["case"]) for r in rows} == expected,
            "missing or duplicate route cases")
    for row in rows:
        count, state = CASES[row["case"]]
        heading = None
        if count:
            label = "SAMPLED" if state == "ROUTE" else LABELS[count - 1]
            heading = ("UFS " + state).ljust(14) + label
        require(row["registerLoads"] == LABELS[:count] and row["peripheralStores"] == 0 and
                row["expectedScreenVerified"] is True and row["heading"] == heading,
                "wrong route access, failed gate or incorrect panel")


def reviewed(root, record):
    image, serial = verify_terminal_inputs(
        root, record, scope="terminal-ufs-route-view", build_prefix="DEBUG-UFS_ROUTE_VIEW-",
        sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS, validate_reports=verify_reports)
    path, content = checked_file(root, record["containerManifest"], ("local",))
    manifest = json.loads(content)
    require(path == image.with_suffix(".json") and manifest["imageSha256"] == record["image"]["sha256"]
            and manifest["fdSha256"] == record["fd"]["sha256"] and manifest["stockBootSha256"] == STOCK_SHA
            and manifest["dtbSha256"] == DTB_SHA and manifest["verification"]["roundtrip"] == "PASS",
            "different packed image")

    def evidence(key, expected_path):
        require(record[key]["file"] == expected_path, "unexpected evidence path")
        return json.loads(checked_file(root, record[key], ("docs",))[1])

    prior = evidence("priorPanel", PREVIOUS)
    require(prior["physicalPanel"]["rawLines"][0] == "UFS CLOCKS SAMPLED" and
            prior["observation"]["domainPowerOn"] is True and
            prior["observation"]["softwareCollapseVote"] is False and
            prior["observation"]["activeBranchesWhenSampled"] == CLOCK_LABELS[1:] and
            prior["physicalUfsStreamId"] == prior["physicalFdPageBus"] == "UNKNOWN",
            "missing physical clock observation")
    rpm = evidence("stockAudit", STOCK)
    inventory = json.loads((root / "docs/evidence/partitions.json").read_bytes())
    stock, = [p for p in inventory["partitions"] if p["name"] == "rpm_a"]
    domains = [r["physicalAddress"] for r in rpm["domains"] if r["name"] == "VDD_AGGRE2_NOC"]
    require(rpm["stockRpmSha256"] == stock["sha256"] and
            domains + [r["physicalAddress"] for r in rpm["aggre2Branches"]] == CLOCK_ADDRESSES,
            "wrong clock register provenance")
    fdt = evidence("runtimeFdtAudit", FDT_AUDIT)
    node = fdt["anoc2"]
    require(fdt["runtimeFdtSha256"] == "0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929"
            and node["node"] == "/soc/arm,smmu-anoc2@1680000" and node["compatible"] == "qcom,smmu-v2"
            and node["status"] == "ok" and node["flags"]["qcom,skip-init"] is True
            and node["iommuReferences"] == 0 and fdt["physicalUfsStreamIdAfterLk"] == "UNKNOWN"
            and node["reg"] == [hex(VIEW_BASE), "0x20000"], "unexpected Pacific ANOC2 range")
    require(record["publishedModel"]["file"] == PUBLISHED and
            checked_file(root, record["publishedModel"], ("docs",))[1] ==
            checked_file(root, record["model"], ("build",))[1], "published model differs")
    return image, serial


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-route-view", measure)
