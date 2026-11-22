"""Collect the published Android platform-device links for Pacific UFS.
Raw reports stay on the host. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from collect_readonly_preflight import ADB_SHA256, require_identity


DEVICE = "/sys/bus/platform/devices/624000.ufshc"
LINKS = ("of_node", "driver", "iommu_group")


def query_links(shell):
    listing = shell("ls", "-1a", DEVICE)
    if listing.returncode:
        raise RuntimeError(f"Cannot enumerate UFS platform device: {listing.stderr.strip()}")
    names = set(listing.stdout.splitlines())
    if "uevent" not in names:
        raise ValueError("Incomplete platform-device listing")
    result = {}
    for name in LINKS:
        if name not in names:
            result[name] = {"state": "NOT-EXPORTED"}
            continue
        link = shell("readlink", "-f", DEVICE + "/" + name)
        if link.returncode:
            raise RuntimeError(f"Exported {name} link unreadable: {link.stderr.strip()}")
        if shell("test", "-d", DEVICE + "/" + name).returncode:
            raise RuntimeError(f"Exported {name} link has no accessible directory target")
        target = link.stdout.strip()
        if not target.startswith("/sys/") or any(c.isspace() for c in target):
            raise ValueError(f"Unexpected sysfs target for {name}")
        if name == "of_node" and target.rsplit("/", 1)[-1] != "ufshc@624000":
            raise ValueError("Platform device and OF node disagree")
        if name == "driver" and not target.startswith("/sys/bus/platform/drivers/"):
            raise ValueError("Driver target outside platform bus")
        result[name] = {"state": "EXPORTED", "target": target}
        if name == "iommu_group":
            group = re.fullmatch(r"/sys/(?:.*/)?iommu_groups/([0-9]+)", target)
            if not group:
                raise ValueError("Unrecognized IOMMU group path")
            result[name]["linuxGroupNumber"] = int(group.group(1))
    return result


def collect(adb, serial):
    if not re.fullmatch("[A-Za-z0-9]+", serial):
        raise ValueError("Expected a single Pacific serial")
    if hashlib.sha256(adb.read_bytes()).hexdigest() != ADB_SHA256:
        raise ValueError("ADB does not match the project tool")
    def run(*args):
        return subprocess.run([str(adb), *args], capture_output=True, text=True, timeout=15)
    def shell(*args):
        return run("-s", serial, "shell", *args)
    # Select an authorized transport before issuing even a property query.
    devices = run("devices", "-l")
    devices.check_returncode()
    transports = [line.split()[:2] for line in devices.stdout.splitlines()]
    if transports.count([serial, "device"]) != 1:
        raise ValueError("Expected authorized Android transport unavailable")
    product = shell("getprop", "ro.product.device")
    reported = run("-s", serial, "get-serialno")
    boot = shell("getprop", "sys.boot_completed")
    for response in (product, reported, boot):
        response.check_returncode()
    require_identity(devices.stdout, serial, reported.stdout, product.stdout)
    if boot.stdout.strip() != "1":
        raise ValueError("Android boot incomplete")
    first = query_links(shell)
    if first != query_links(shell):
        raise RuntimeError("UFS platform binding changed between samples")
    return first


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--expected-serial", required=True)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    out = Path(__file__).resolve().parents[1] / "local" / ("ufs-binding-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    report = {"scope": "Android platform UFS binding", "device": DEVICE,
              "postLkUfsSid": "UNKNOWN", "postLkPageBus": "UNKNOWN"}
    try:
        report["links"] = collect(args.adb.resolve(), args.expected_serial)
        report["result"] = "PASS-READONLY"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report["result"] = "INCOMPLETE"
        report["error"] = str(error)
    (out / "REPORT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(report["result"], out)
    return int(report["result"] != "PASS-READONLY")


if __name__ == "__main__":
    raise SystemExit(main())
