"""Verify the CPU-only byte census, or boot it once in an attended session.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_buf4k_once import ROOT, SEC, REQUIRED as PREVIOUS_INPUTS
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-zero4k-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-buf4k-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-zero4k-20261121.json"
GUID = "497f6dc9-8be0-4fc9-8b68-a4c489645b66"
REQUIRED = (PREVIOUS_INPUTS - {"OculusGoPkg/SecMem/UfsBuf4k.inf"}) | {
    "OculusGoPkg/SecMem/UfsZero4k.inf", "tools/run_ufs_zero4k_once.py", "tools/audit_lk_header_lifetime.py"
}


def verify_reports(model, static, digest):
    require((static["status"], static["secOnly"], static["vectorsVerified"], static["transportLinked"]) ==
            ("PASS-STATIC", GUID, 16, False), "unexpected SEC profile or transport")
    require(model["fdSha256"] == static["fdSha256"] == digest and model["outcome"] == "PASS-QEMU-ZERO4K"
            and (model["candidate"], model["bytes"]) == ("0x918d7e80", 4096), "wrong FD or model")
    nonzero = {"first": (1, 0), "last": (1, 4095), "split-left": (1, 383), "split-right": (1, 384),
               "crc-collision": (5, 382), "full": (4096, 0)}
    cases = {(1, k) for k in nonzero} | {(1,"changing"), (1,"wrong-size"), (1,"zero"), (2,"zero")}
    rows = model["cases"]
    require(len(rows) == len(cases) and {(r["el"], r["case"]) for r in rows} == cases, "missing zero trials")
    for row in rows:
        case, panel = row["case"], row["panel"]
        require(row["restored"] and row["firmwareDoorbells"] == row["mediaWrites"] == 0
                and all(not row[k] for k in ("transfers","readExtents","mappedCandidateLeaves","gptSectorSha256"))
                and panel[1] == "BUF  918D7E80" and panel[7] == "CPU ONLY", "unexpected device access")
        if case in ("changing","wrong-size"):
            require(panel[0] == {"changing":"UFS CHANGED   BUFFER","wrong-size":"UFS STOP      LKPG"}[case]
                    and panel[3:7] == ["OLD","","",""], "invalid error panel")
            continue
        require(panel[0] == "UFS ZERO4K    DONE" and panel[2] == "LKPG 00001000", "invalid completion")
        if case in ("crc-collision","zero"):
            require(panel[3] == "OLD  C71C0011", "missing CRC control")
        if case == "zero":
            require(panel[4:7] == ["NZ   00000000","FIRST NONE","ZERO EXACT"], "invalid zero result")
        else:
            count, offset = nonzero[case]
            require(panel[4:7] == [f"NZ   {count:08X}", f"OFF  {offset:08X}", "NONZERO"], "invalid count")


def reviewed(root, record):
    image, unit = verify_terminal_inputs(root, record, scope="terminal-ufs-zero4k",
        build_prefix="DEBUG-UFS_ZERO4K-", sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS,
        validate_reports=verify_reports)
    path, raw = checked_file(root, record["containerManifest"], ("local",))
    manifest = json.loads(raw)
    require(path == image.with_suffix(".json") and manifest["imageSha256"] == record["image"]["sha256"]
            and manifest["fdSha256"] == record["fd"]["sha256"] and manifest["stockBootSha256"] == STOCK_SHA
            and manifest["dtbSha256"] == DTB_SHA and manifest["verification"]["roundtrip"] == "PASS",
            "different container")
    _, raw = checked_file(root, record["lifetimeAudit"], ("docs",))
    result = json.loads(raw)
    require(result["stockElfSha256"] == json.loads((root/PREVIOUS).read_bytes())["recovery"]["matchedBeforeAndOriginals"]["aboot_a"]
            and result["exclusiveAfterHandoff"] == result["retainedEndpointDma"] == "UNKNOWN"
            and result["cpuBuffer"] == "0x918d7e80", "different stock evidence")
    _, published = checked_file(root, record["publishedModel"], ("docs",))
    _, local = checked_file(root, record["model"], ("build",))
    require(local == published, "different published QEMU report")
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-zero4k", measure)
