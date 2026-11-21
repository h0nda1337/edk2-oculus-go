"""Attended Android readback of the Pacific splash LUN and its primary GPT.
Reads only sysfs, two GPT regions and the existing by-name link. Local output.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zlib

from collect_readonly_preflight import ADB_SHA256, require_identity

ROOT = Path(__file__).resolve().parents[1]


def layout(header, sector, last):
    if sector not in (512, 1024, 2048, 4096) or len(header) != sector:
        raise ValueError("Unexpected logical sector")
    sig, rev, length, crc, reserved, current, alt, first, end = struct.unpack_from("<8s4I4Q", header)
    table, count, stride, array_crc = struct.unpack_from("<QIII", header, 72)
    checked = bytearray(header[:length])
    checked[16:20] = bytes(4)
    if (sig != b"EFI PART" or rev != 0x10000 or not 92 <= length <= sector
        or reserved or crc != zlib.crc32(checked) or current != 1 or alt != last
        or not 2 <= table < first <= end < last or count == 0 or stride < 128
        or stride & (stride - 1) or count * stride > 65536):
        raise ValueError("Unsupported or corrupt primary GPT")
    blocks = (count * stride + sector - 1) // sector
    if table + blocks > first:
        raise ValueError("Entry array overlaps usable range")
    return table, blocks, count, stride, array_crc


def collect(adb, serial, out):
    if not re.fullmatch(r"[A-Za-z0-9]+", serial) or hashlib.sha256(adb.read_bytes()).hexdigest() != ADB_SHA256:
        raise ValueError("Unexpected ADB binary or serial")
    out.mkdir(parents=True, exist_ok=False)
    def run(*args):
        entry = {"command": list(args)}
        try:
            proc = subprocess.run([str(adb), "-s", serial, *args], capture_output=True, timeout=20)
            entry.update(exitCode=proc.returncode, stdoutBytes=len(proc.stdout))
            proc.check_returncode()
            return proc.stdout
        finally:
            with (out / "commands.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry) + "\n")
    def shell(*args):
        return run("shell", *args).decode().strip()
    require_identity(run("devices").decode(), serial, shell("getprop", "ro.serialno"),
                     shell("getprop", "ro.product.device"))
    if shell("id", "-u") != "0":
        raise ValueError("Requires an already-rooted adbd")
    stock = next(p for p in json.loads((ROOT / "docs/evidence/partitions.json").read_text())["partitions"]
                 if p["name"] == "splash")
    path = shell("readlink", "-f", "/dev/block/bootdevice/by-name/splash")
    match = re.fullmatch(r"/dev/block/(sd[a-f])([0-9]+)", path)
    if not match or path != stock["blockDevice"]:
        raise ValueError("Splash identity differs from backup")
    drive = match[1]
    sys = f"/sys/class/block/{drive}"
    scsi = shell("readlink", "-f", sys + "/device")
    if "/624000.ufshc/" not in scsi or not re.search(r"/\d+:\d+:\d+:\d+$", scsi):
        raise ValueError("Unexpected SCSI host path")
    sector = int(shell("cat", sys + "/queue/logical_block_size"))
    capacity = int(shell("cat", sys + "/size")) * 512
    start = int(shell("cat", sys + match[2] + "/start")) * 512
    size = int(shell("cat", sys + match[2] + "/size")) * 512
    if size != stock["size"] or sector not in (512, 1024, 2048, 4096) or capacity % sector:
        raise ValueError("Unexpected block geometry")
    def blocks(lba, count):
        # exec-out preserves binary data. Pass the redirection as shell syntax,
        # not as a quoted dd operand. drive is allowlisted and sizes are integers.
        data = run("exec-out", f"dd if=/dev/block/{drive} bs={sector} skip={lba} count={count} 2>/dev/null")
        if len(data) != count * sector:
            raise ValueError("Short GPT read")
        return data
    header = blocks(1, 1)
    table, nblocks, count, stride, crc = layout(header, sector, capacity // sector - 1)
    entries = blocks(table, nblocks)[:count * stride]
    if zlib.crc32(entries) != crc:
        raise ValueError("GPT array CRC mismatch")
    hits = []
    for offset in range(0, len(entries), stride):
        entry = entries[offset:offset + stride]
        if entry[:16] != bytes(16) and entry[56:70] == "splash\0".encode("utf-16le"):
            hits.append(struct.unpack_from("<QQ", entry, 32))
    if len(hits) != 1 or (hits[0][0] * sector, (hits[0][1] + 1) * sector) != (start, start + size):
        raise ValueError("Named GPT entry differs from kernel partition bounds")
    (out / "primary-header.bin").write_bytes(header)
    (out / "primary-entries.bin").write_bytes(entries)
    report = {"source": "Android, after kernel initialization", "scsiDevice": scsi,
              "diskBytes": capacity, "blockSize": sector, "start": hits[0][0], "end": hits[0][1],
              "splashBytes": size, "entriesCrc32": f"{crc:08x}"}
    for name, filename in [("runtimePower", "power/runtime_status"), ("dmaMaskBits", "dma_mask_bits")]:
        p = "/sys/bus/platform/devices/624000.ufshc/" + filename
        try:
            report[name] = shell("cat", p)
        except subprocess.CalledProcessError:
            report[name] = "UNKNOWN"
    group = "/sys/bus/platform/devices/624000.ufshc/iommu_group"
    try:
        # readlink without -f fails for an absent link. Absence on this kernel
        # does not establish an identity DMA mapping.
        report["iommuGroupLink"] = shell("readlink", group)
    except subprocess.CalledProcessError:
        report["iommuGroupLink"] = "UNKNOWN"
    (out / "layout.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Verified primary GPT and Android splash extent. Local report:", out / "layout.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--expected-serial", required=True)
    args = parser.parse_args()
    collect(args.adb, args.expected_serial, ROOT / "local" / datetime.now(timezone.utc).strftime("ufs-layout-%Y%m%d-%H%M%S"))
