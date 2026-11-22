"""End-to-end read-only UFS evidence, using a private Pacific splash backup.
Run in Debian/WSL after scripts/build-qemu-ufs-drivers.sh. No USB access.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import struct
import zlib
import tempfile

from logo_disk_qemu import disk
from pacific_lun import write_lun
from oculus_logo import STOCK_HASH

ROOT = Path(__file__).resolve().parents[1]
EFI = ROOT / "Build/PacificUfsTest/DEBUG_GCC5/AARCH64"
SECTOR = 4096
START = 2048


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def flip(path, offset):
    with path.open("r+b") as f:
        f.seek(offset)
        byte = f.read(1)
        f.seek(offset)
        f.write(bytes([byte[0] ^ 1]))


def change_entry(path, duplicate):
    # Keep both GPT CRCs valid so these cases exercise semantic checks.
    with path.open("r+b") as f:
        f.seek(SECTOR)
        header = bytearray(f.read(SECTOR))
        table, count, stride = struct.unpack_from("<QII", header, 72)
        f.seek(table * SECTOR)
        entries = bytearray(f.read(count * stride))
        if duplicate:
            entries[stride:2 * stride] = entries[:stride]
            entries[stride + 16] ^= 1
        else:
            struct.pack_into("<Q", entries, 40, struct.unpack_from("<Q", header, 48)[0] + 1)
        struct.pack_into("<I", header, 88, zlib.crc32(entries))
        struct.pack_into("<I", header, 16, 0)
        struct.pack_into("<I", header, 16, zlib.crc32(header[:92]))
        f.seek(table * SECTOR)
        f.write(entries)
        f.seek(SECTOR)
        f.write(header)


def run(splash, output, pacific_layout=None):
    output.mkdir(parents=True, exist_ok=True)
    report = output / "result.json"
    report.write_text(json.dumps({"status": "IN_PROGRESS"}) + "\n")
    if digest(splash) != STOCK_HASH:
        raise ValueError("Unexpected private splash digest")
    source = splash.read_bytes()
    measured = json.loads((ROOT / "docs/evidence/ufs-splash-physical-layout-20261120.json").read_text())
    pacific_last = measured["lunBytes"] // measured["logicalBlockBytes"] - 1
    result = {
        "qemu": subprocess.check_output(["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
        "splashSha256": STOCK_HASH, "sectorBytes": SECTOR, "cases": {},
    }
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        esp = work / "esp"
        boot = esp / "EFI/BOOT"
        boot.mkdir(parents=True)
        files = {"BOOTAA64.EFI": EFI / "UfsSplashApp.efi",
                 "UfsPciHcDxe.efi": EFI / "UfsPciHcDxe.efi",
                 "UfsPassThruDxe.efi": EFI / "UfsPassThruDxe.efi"}
        for name, path in files.items():
            shutil.copyfile(path, (boot if name == "BOOTAA64.EFI" else esp) / name)
        result["efiSha256"] = {name: digest(path) for name, path in files.items()}
        firmware = Path("/usr/share/AAVMF/AAVMF_CODE.fd")
        result["aavmfSha256"] = digest(firmware)
        events = work / "events"
        events.write_text("ufs_exec_scsi_cmd\nufs_exec_query_cmd\nscsi_req_build_sense\nscsi_disk_dma_command_READ\n")
        # A second user LUN with no GPT checks enumeration before the true volume.
        blank = work / "blank.raw"
        with blank.open("wb") as f:
            f.truncate(1024 * 1024)
        cases = [("stock", 4), ("moved", 2), ("sparse", 4), ("wrong-label", 4),
                          ("bad-header-crc", 4), ("bad-entries-crc", 4), ("outside-range", 4),
                          ("duplicate", 4), ("bad-logo", 4), ("wrong-geometry", 4)]
        positive = {"stock", "moved", "sparse", "pacific"}
        for case, lun in ([("pacific", 4)] if pacific_layout else cases):
            image = work / "gpt.raw"
            if pacific_layout:
                result["geometry"] = write_lun(image, source, pacific_layout)
            else:
                last = pacific_last - int(case == "wrong-geometry") if lun == 4 else None
                disk(image, source, "other" if case == "wrong-label" else "splash",
                     sector=SECTOR, last_lba=last)
            if case == "bad-header-crc":
                flip(image, SECTOR + 16)
            elif case == "bad-entries-crc":
                flip(image, 2 * SECTOR + 56)
            elif case in {"outside-range", "duplicate"}:
                change_entry(image, duplicate=(case == "duplicate"))
            elif case == "bad-logo":
                # Invert a 3x3 white/black sample into a visibly different value.
                offset = START * SECTOR + 512 + 558 * 4320 + 657 * 3
                with image.open("r+b") as f:
                    for row in range(3):
                        f.seek(offset + row * 4320)
                        f.write(bytes([0xff]) * 9)
            before = {p.name: digest(p) for p in (image, blank)}
            nvram = work / "vars.fd"
            shutil.copyfile("/usr/share/AAVMF/AAVMF_VARS.fd", nvram)
            trace = output.resolve() / (case + ".trace")
            cmd = ["qemu-system-aarch64", "-machine", "virt", "-cpu", "cortex-a57",
                   "-m", "512", "-nodefaults", "-display", "none", "-serial", "stdio",
                   "-monitor", "none", "-no-reboot", "-device", "ramfb",
                   "-drive", f"if=pflash,format=raw,readonly=on,file={firmware}",
                   "-drive", f"if=pflash,format=raw,file={nvram}",
                   "-drive", f"if=none,id=esp,format=raw,readonly=on,file=fat:ro:{esp}",
                   "-device", "virtio-blk-pci,drive=esp,bootindex=1",
                   "-device", "ufs,id=ufshc,mcq=off",
                   "-drive", f"if=none,id=empty,format=raw,readonly=on,file={blank}",
                   "-device", "ufs-lu,drive=empty,bus=ufshc,lun=0",
                   "-drive", f"if=none,id=stock,format=raw,readonly=on,file={image}",
                   "-device", f"ufs-lu,drive=stock,bus=ufshc,lun={lun}",
                   "-trace", f"events={events},file={trace}"]
            for prior in (() if case == "sparse" else range(1, lun)):
                cmd.extend(["-drive", f"if=none,id=empty{prior},format=raw,readonly=on,file={blank}",
                            "-device", f"ufs-lu,drive=empty{prior},bus=ufshc,lun={prior}"])
            with (output / (case + ".log")).open("wb") as log:
                subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=100, check=True)
            log = (output / (case + ".log")).read_text(errors="replace")
            expected = "FOUND 93104DC6" if case in positive else "ABSENT 00000000"
            if "GO-UFS-GOP-CLEAR Success" not in log or (
                case in positive and "GO-UFS-GOP-READBACK Success" not in log
            ):
                raise AssertionError((case, log[-2048:]))
            if ("GO-UFS-RESULT " + expected).lower() not in log.lower():
                raise AssertionError((case, log[-2048:]))
            trace_text = trace.read_text()
            query_ops = Counter(int(op, 16) for op in re.findall(r"ufs_exec_query_cmd slot \d+, opcode 0x([\da-fA-F]+)", trace_text))
            if set(query_ops) != {0x01, 0x05, 0x06}:
                raise AssertionError((case, "unexpected UFS management operations", query_ops))
            matches = re.findall(r"ufs_exec_scsi_cmd slot \d+, lun 0x([\da-fA-F]+), opcode 0x([\da-fA-F]+)", trace_text)
            commands = Counter((int(unit, 16), int(op, 16)) for unit, op in matches)
            if case == "wrong-geometry":
                if set(commands) != {(4, 0x25)}:
                    raise AssertionError((case, "unexpected CDB after capacity mismatch", commands))
            elif lun == 4:
                stream = [(int(unit, 16), int(op, 16)) for unit, op in matches]
                first_read = next((i for i, (_, op) in enumerate(stream) if op == 0x28), 0)
                if first_read < 2 or any(unit != 4 for unit, _ in stream) or any(
                    op != 0x25 for _, op in stream[:first_read]
                ):
                    raise AssertionError((case, "GPT before LUN 4 capacity pair", stream))
            if ((case != "wrong-geometry" and not commands[(lun, 0x28)])
                or (lun != 4 and not commands[(0, 0x25)]) or any(
                op not in (0x25, 0x28) or unit not in range(lun + 1) for unit, op in commands
            )):
                raise AssertionError((case, commands))
            if before != {p.name: digest(p) for p in (image, blank)}:
                raise AssertionError("UFS backing digest changed")
            result["cases"][case] = {"guestResult": expected, "gopPixelReadback": case in positive,
                "queryCommands": {f"0x{op:02x}": count for op, count in sorted(query_ops.items())},
                "stationaryBackingSha256": before,
                "scsiCommands": {f"LUN{unit}/0x{op:02x}": count for (unit, op), count in sorted(commands.items())}}
            if pacific_layout:
                # The SCSI target traces the decoded CDB in logical sector units.
                reads = [(int(lba), int(n)) for lba, n in re.findall(
                    r"ufs_exec_scsi_cmd slot \d+, lun 0x4, opcode 0x28\n"
                    r"scsi_disk_dma_command_READ Read \(sector (\d+), count (\d+)\)", trace_text)]
                geom = result["geometry"]
                start, end = geom["firstSplashLba"], geom["lastSplashLbaInclusive"]
                if (len(reads) != commands[(4, 0x28)] or reads[:3] != [(1, 1), (2, 2), (start, 1)]
                        or len(reads) < 4 or any(n < 1 or lba < start or lba + n - 1 > end
                                                  for lba, n in reads[3:])):
                    raise AssertionError(("Unexpected LUN 4 READ(10) extents", reads))
                result["cases"][case]["lun4Read10LbaAndCount"] = reads
            print(case, expected, flush=True)
    result["status"] = "PASS"
    report.with_suffix(".tmp").write_text(json.dumps(result, indent=2) + "\n")
    report.with_suffix(".tmp").replace(report)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("splash", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--pacific-layout", type=Path, help="Directory with the private primary GPT and layout.json")
    args = ap.parse_args()
    run(args.splash, args.output, args.pacific_layout)
