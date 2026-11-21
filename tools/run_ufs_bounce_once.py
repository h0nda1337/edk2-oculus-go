"""Validate the reviewed LK bounce package offline; optional attended temporary boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import json

from android_boot import DTB_SHA, STOCK_SHA
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_ufs_data_once import SEC, REQUIRED as DATA_INPUTS, ROOT
from terminal_review import verify_terminal_inputs

REVIEW = "docs/evidence/ufs-bounce-review-20261121.json"
PREVIOUS = "docs/evidence/ufs-data-transfer-20261121.json"
LEDGER = "local/physical-attempts/ufs-bounce-20261121.json"
REQUIRED = (DATA_INPUTS - {"OculusGoPkg/SecMem/UfsData.inf"}) | {
    "OculusGoPkg/SecMem/UfsBounce.inf", "tests/ufs_bounce_fd_qemu.py", "tools/run_ufs_bounce_once.py"
}

def verify_reports(model, static, digest):
    require(model["outcome"]=="PASS-QEMU-FD-BOUNCE" and static["status"]=="PASS-STATIC" and
            model["fdSha256"]==static["fdSha256"]==digest, "FD report mismatch")
    require((static["secOnly"],static["vectorsVerified"],static["registerStore"],static["value"])==
            ("2eb661f1-f41a-41b8-b5d1-39b61bc1d720",16,"0x624058",2), "unexpected SEC or doorbell")
    require(model["mediaReads"]==model["mediaWrites"]==0 and model["physicalWindowDma"]=="UNKNOWN",
            "media access or unsupported claim")
    rows=model["cases"]
    require(len(rows)==4 and {(r["el"],r["case"]) for r in rows}==
            {(el,case) for el in (1,2) for case in ("lk-only","wrong-geometry")}, "missing FD tests")
    for row in rows:
        ok=row["case"]=="lk-only"
        n=4 if ok else 0
        require(row["directWindowMappings"]==0 and row["dmaPages"]==["0x918ee000"] and
                row["restored"] is True and row["cpuCopies"]==n, "unverified copies or mapping")
        require(row["panel"][2]==f"COPY MASK {(1<<n)-1:08X}" and
                row["panel"][-1]=="FD DIRECT UNTESTED", "ambiguous panel")
        expected=[(2,"a5"*8,0)]+([(0,"0011ffff00001000",i) for i in range(4)] if ok
                                  else [(0,"0011fffe00001000",0)])
        require(all(c["bus"]=="0x918eef80" for c in row["completions"]) and
                [(c["status"],c["bytes"],c["copiedBeforeCpuResumed"]) for c in row["completions"]]==expected,
                "unexpected DMA address, payload or CPU sequence")

def reviewed(root, record):
    image, unit = verify_terminal_inputs(root,record,scope="terminal-ufs-bounce",build_prefix="DEBUG-UFS_BOUNCE-",
        sec_sources=SEC,required=REQUIRED,previous_record=PREVIOUS,validate_reports=verify_reports)
    path, raw=checked_file(root,record["containerManifest"],("local",))
    manifest=json.loads(raw)
    require(path==image.with_suffix(".json") and manifest["imageSha256"]==record["image"]["sha256"] and
            manifest["fdSha256"]==record["fd"]["sha256"] and manifest["dtbSha256"]==DTB_SHA and
            manifest["stockBootSha256"]==STOCK_SHA and manifest["verification"]["roundtrip"]=="PASS",
            "container manifest mismatch")
    _, raw=checked_file(root,record["priorData"],("docs",))
    prior=json.loads(raw)
    require(record["priorData"]["file"]==PREVIOUS and prior["lkDataIn"]["result"]=="CONFIRMED" and
            prior["lkDataIn"]["controlDataAddressFromReviewedFirmware"]=="0x918EEF80" and
            prior["capacity"]["returnedBytesFromPanelBigEndian"]=="0011ffff00001000", "missing physical LK control")
    _, published=checked_file(root,record["publishedModel"],("docs",))
    _, local=checked_file(root,record["model"],("build",))
    require(published==local, "published model differs")
    return image,unit

def measure(root,image,tool,serial,preflight,report,output):
    measure_once(root,LEDGER,image,tool,serial,preflight,report,output)

if __name__=="__main__":
    attended_main(ROOT,REVIEW,LEDGER,reviewed,"ufs-bounce",measure)
