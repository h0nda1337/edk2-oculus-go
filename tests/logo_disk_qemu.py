"""Read the original emblem from a real virtual GPT disk through EDK2 protocols.
Run in WSL with the private splash dump. Guest attachments are read-only.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from uuid import UUID

from oculus_logo import STOCK_HASH

ROOT = Path(__file__).resolve().parents[1]
BDS = ROOT / "OculusGoPkg/Drivers/GoBdsDxe"


def disk(path, payload, label, sector=512, last_lba=None):
    if sector not in (512, 4096) or not payload or len(payload) % sector:
        raise ValueError("Fixture must contain whole logical blocks")
    start = 2048
    table_blocks = 128 * 128 // sector
    end = start + len(payload) // sector - 1
    last = end + 2048 if last_lba is None else last_lba
    if end >= last - table_blocks:
        raise ValueError("Fixture does not fit the requested geometry")
    entries = bytearray(128 * 128)
    struct.pack_into(
        "<16s16sQQQ",
        entries,
        0,
        UUID("0fc63daf-8483-4772-8e79-3d69d8477de4").bytes_le,
        UUID("39f69a3b-6171-4f23-ad03-12442061a182").bytes_le,
        start,
        end,
        0,
    )
    name = label.encode("utf-16le")
    entries[56 : 56 + len(name)] = name

    def header(at, backup, table):
        value = bytearray(
            struct.pack(
                "<8s4I4Q16sQ3I",
                b"EFI PART",
                0x10000,
                92,
                0,
                0,
                at,
                backup,
                2 + table_blocks,
                last - 1 - table_blocks,
                UUID("7bcb9530-f2e9-4a2f-95c4-e3707c44221e").bytes_le,
                table,
                128,
                128,
                zlib.crc32(entries),
            )
        )
        struct.pack_into("<I", value, 16, zlib.crc32(value))
        return value

    with path.open("wb") as f:
        f.truncate((last + 1) * sector)
        mbr = bytearray(sector)
        mbr[450] = 0xEE
        struct.pack_into("<II", mbr, 454, 1, last)
        mbr[510:512] = b"\x55\xaa"
        for lba, data in [
            (0, mbr),
            (1, header(1, last, 2)),
            (2, entries),
            (start, payload),
            (last - table_blocks, entries),
            (last, header(last, 1, last - table_blocks)),
        ]:
            f.seek(lba * sector)
            f.write(data)


def run(splash, output):
    source = splash.read_bytes()
    assert hashlib.sha256(source).hexdigest() == STOCK_HASH
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        boot = work / "esp/EFI/BOOT"
        boot.mkdir(parents=True)
        inc = ROOT / "edk2/MdePkg/Include"
        for src in [BDS / "OculusLogo.c", ROOT / "tests/logo_disk_app.c"]:
            subprocess.run(
                [
                    "clang",
                    "--target=aarch64-pc-windows-msvc",
                    "-O2",
                    "-ffreestanding",
                    "-fno-stack-protector",
                    "-fshort-wchar",
                    "-DMDEPKG_NDEBUG",
                    "-I",
                    inc,
                    "-I",
                    inc / "AArch64",
                    "-I",
                    ROOT / "OculusGoPkg/Include",
                    "-I",
                    BDS,
                    "-c",
                    src,
                    "-o",
                    work / (src.stem + ".obj"),
                ],
                check=True,
            )
        subprocess.run(
            [
                "lld-link",
                "/entry:TestMain",
                "/nodefaultlib",
                "/subsystem:efi_application",
                "/out:" + str(boot / "BOOTAA64.EFI"),
                work / "OculusLogo.obj",
                work / "logo_disk_app.obj",
            ],
            check=True,
        )
        firmware = Path("/usr/share/AAVMF/AAVMF_CODE.fd")
        for label, expected in [("splash", "PASS"), ("other", "MISSING")]:
            backing = work / "gpt.raw"
            disk(backing, source, label)
            nvram = work / "vars.fd"
            shutil.copyfile("/usr/share/AAVMF/AAVMF_VARS.fd", nvram)
            cmd = [
                "qemu-system-aarch64",
                "-machine",
                "virt",
                "-cpu",
                "cortex-a57",
                "-m",
                "512",
                "-nodefaults",
                "-nographic",
                "-serial",
                "stdio",
                "-monitor",
                "none",
                "-no-reboot",
                "-drive",
                f"if=pflash,format=raw,readonly=on,file={firmware}",
                "-drive",
                f"if=pflash,format=raw,file={nvram}",
                "-drive",
                f"if=none,id=boot,format=raw,readonly=on,file=fat:ro:{work / 'esp'}",
                "-device",
                "virtio-blk-pci,drive=boot,bootindex=1",
                "-drive",
                f"if=none,id=stock,format=raw,readonly=on,file={backing}",
                "-device",
                "virtio-blk-pci,drive=stock",
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=75, check=True)
            log = result.stdout + result.stderr
            (output / (label + ".log")).write_bytes(log)
            assert ("GO-GPT-EMBLEM-" + expected).encode() in log, log[-1024:]
            results[label] = expected
        report = {
            "backend": "read-only virtio-blk PCI, GPT, EDK2 Disk I/O",
            "splashSha256": STOCK_HASH,
            "readerSha256": hashlib.sha256(
                (BDS / "OculusLogo.c").read_bytes()
            ).hexdigest(),
            "edk2TestFirmwareSha256": hashlib.sha256(firmware.read_bytes()).hexdigest(),
            "cases": results,
        }
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("splash", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.splash, args.output)
