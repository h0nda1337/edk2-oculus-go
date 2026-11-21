"""Capture the stock driver's view of the Pacific UFS device. Read-only, no reboot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from collect_readonly_preflight import ADB_SHA256, require_identity

HOST = "/sys/bus/platform/devices/624000.ufshc"
# Read only driver-owned metadata. Absence is common on the stock 3.18 kernel.
FIELDS = {
    "driver": ("readlink", HOST+"/driver"),
    "deviceTreeNode": ("readlink", HOST+"/of_node"),
    "iommuGroup": ("readlink", HOST+"/iommu_group"),
    "dmaMaskBits": ("cat", HOST+"/dma_mask_bits"),
    "consistentDmaMaskBits": ("cat", HOST+"/consistent_dma_mask_bits"),
    "groupType": ("cat", HOST+"/iommu_group/type"),
}

def collect(read):
    fields = {}
    for name, args in FIELDS.items():
        code, value = read(*args)
        if code and (code != 1 or (value and not any(reason in value.lower() for reason in
                ("no such file", "permission denied", "invalid argument", "not a symbolic link")))):
            raise RuntimeError(f"unexpected sysfs failure for {name}: {code} {value}")
        fields[name] = {"result": "OBSERVED" if code == 0 else "UNAVAILABLE", "value": value}
    driver = fields["driver"]
    if driver["result"] != "OBSERVED" or not driver["value"] or "ufs" not in driver["value"].lower():
        raise ValueError("expected bound UFS platform driver")
    return {"environment":"stock Android", "host":"624000.ufshc", "fields":fields,
            "lkWindowDma":"UNKNOWN"}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", type=Path, required=True)
    ap.add_argument("--expected-serial", required=True)
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]+",args.expected_serial):
        raise ValueError("invalid serial")
    adb = args.adb.resolve(strict=True)
    if hashlib.sha256(adb.read_bytes()).hexdigest()!=ADB_SHA256:
        raise ValueError("different adb executable")
    def run(*argv):
        p = subprocess.run([str(adb),"-s",args.expected_serial,*argv],
                           capture_output=True, timeout=10)
        text = (p.stdout+p.stderr).decode(errors="replace").strip()
        if len(text)>4096:
            raise ValueError("unexpected output size")
        return p.returncode,text
    def checked(*argv):
        code,value=run(*argv)
        if code: raise RuntimeError(value)
        return value
    listing = checked("devices","-l")
    require_identity(listing,args.expected_serial,checked("shell","getprop","ro.serialno"),
                     checked("shell","getprop","ro.product.device"))
    report = collect(lambda *argv: run("shell",*argv))
    root = Path(__file__).resolve().parents[1]/"local"
    root.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    out=root/f"ufs-android-dma-{stamp}.json"
    with out.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(out.name)

if __name__=="__main__":
    main()
