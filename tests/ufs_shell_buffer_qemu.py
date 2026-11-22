"""Exercise the Shell consumer's Boot Services allocation and real UFS mappings in AAVMF.
The boot ESP and the content-free LUN 4 are read-only. No device access.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ufs_capacity_map_qemu import SMMU_TRACE
from ufs_data_qemu import CAPACITY, LUN_BYTES, unit_args
from ufs_nop11_bus import PAGE
from ufs_splash_qemu import EFI, digest


FIRMWARE = Path("/usr/share/AAVMF/AAVMF_CODE.fd")
NVRAM = Path("/usr/share/AAVMF/AAVMF_VARS.fd")
MODULES = ("UfsShellBuffer.efi", "UfsPciHcDxe.efi", "UfsPassThruDxe.efi")
MACHINE = "virt,acpi=on,gic-version=3,its=on,iommu=smmuv3"
UFS_SID = 3 << 3  # fixed virtual PCI device 00:03.0 in this model
HEX = r"[0-9a-fA-F]+"
DATA = r"[0-9a-fA-F]{16}"
CAP_COMMAND = re.compile(r"ufs_exec_scsi_cmd slot \d+, lun 0x4, opcode 0x25")
SMMU_EVENT = re.compile(
    r"smmuv3_translate_(?:disable|bypass) \S+ sid=0x([0-9a-f]+) "
    r"(?:bypass \(smmu disabled\)|STE bypass) iova:0x([0-9a-f]+) is_write=\d+"
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def launch(work, modules, size_mib, lun_bytes, marker, with_ufs):
    boot = work / "esp/EFI/BOOT"
    boot.mkdir(parents=True)
    esp = work / "esp"
    for name in MODULES:
        dest = boot / "BOOTAA64.EFI" if name == MODULES[0] else esp / name
        shutil.copyfile(modules / name, dest)
    if marker:
        (esp / marker).touch()
    nvram = work / "vars.fd"
    shutil.copyfile(NVRAM, nvram)
    events = work / "events"
    trace = work / "trace"
    events.write_text("\n".join(("ufs_exec_scsi_cmd", "scsi_disk_dma_command_READ",
                                 "scsi_disk_dma_command_WRITE", *SMMU_TRACE)) + "\n")
    cmd = ["qemu-system-aarch64", "-machine", MACHINE, "-cpu", "cortex-a57", "-m", f"{size_mib}M",
           "-nodefaults", "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot",
           "-drive", f"if=pflash,format=raw,readonly=on,file={FIRMWARE}",
           "-drive", f"if=pflash,format=raw,file={nvram}",
           "-drive", f"if=none,id=esp,format=raw,readonly=on,file=fat:ro:{esp}",
           "-device", "virtio-blk-pci,drive=esp,bootindex=1",
           "-trace", f"events={events},file={trace}"]
    if with_ufs:
        cmd.extend(["-device", "ufs,mcq=off,addr=3.0", *unit_args(lun_bytes)])
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=100,
                            text=True, errors="replace")
    require(result.returncode == 0, f"QEMU exited with {result.returncode}\n{result.stdout[-2000:]}")
    return result.stdout, trace.read_text().splitlines()


def command_transfers(trace):
    """Group SMMU model events by actual SCSI submission; reject all sector ops."""
    transfers = []
    for line in trace:
        if CAP_COMMAND.fullmatch(line):
            transfers.append(set())
        elif line.partition(" ")[0] in SMMU_TRACE:
            event = SMMU_EVENT.fullmatch(line)
            if event and int(event[1], 16) == UFS_SID and transfers:
                transfers[-1].add(int(event[2], 16))
        else:
            raise ValueError(f"Unexpected UFS command or disk access: {line}")
    return transfers


def checked_case(work, modules, name, size_mib):
    with_ufs = name != "no-provider"
    lun_bytes = LUN_BYTES - PAGE if name == "wrong-capacity" else LUN_BYTES
    marker = {"deny-tail": "DENYTAIL", "short-tail": "SHORTMAP",
              "bounce": "BOUNCE", "changed-guard": "GUARD"}.get(name)
    log, trace = launch(work, modules, size_mib, lun_bytes, marker, with_ufs)
    lines = [line for line in log.splitlines() if line.startswith("UFS-BUFFER ")]
    outcomes = [line.removeprefix("UFS-BUFFER RESULT ") for line in lines
                if line.startswith("UFS-BUFFER RESULT ")]
    require(len(outcomes) == 1, f"{name}: missing unique guest result\n{log[-1800:]}")
    terminal = outcomes[0]
    stats = re.findall(r"^UFS-BUFFER MAPS (\d+) UNMAPS (\d+) DENIED (\d+)$", log, re.M)
    require(len(stats) == 1, f"{name}: missing mapping counts {lines}")
    mapped, unmapped, denied = map(int, stats[0])
    shortened = re.findall(r"^UFS-BUFFER SHORT (\d+)$", log, re.M)
    require(shortened == [str(int(name == "short-tail"))], f"{name}: short Map count {lines}")
    short_count = int(shortened[0])
    require("UFS-BUFFER ORACLE ERROR" not in lines, f"{name}: guest validation failed {lines}")
    transfers = command_transfers(trace)
    observed = [(int(host, 16), int(bus, 16), data.lower())
                for host, bus, data in re.findall(
                    rf"^UFS-BUFFER OBS CPU ({HEX}) DMA ({HEX}) DATA ({DATA})$", log, re.M)]
    ends = [(int(i), int(host, 16), int(bus, 16), data.lower())
            for i, host, bus, data in re.findall(
                rf"^UFS-BUFFER END (\d+) CPU ({HEX}) DMA ({HEX}) DATA ({DATA})$", log, re.M)]
    require(mapped == unmapped == len(observed) == len(transfers) + short_count,
            f"{name}: mapping/command lifecycle mismatch {stats} {len(transfers)} {lines}")
    require(denied == int(name == "deny-tail"), f"{name}: wrong denial count {denied}")
    positive = name in ("small-ram", "large-ram", "bounce")
    if positive:
        require(terminal == "Success" and len(ends) == 2, f"{name}: {lines}")
        base = ends[0][1]
        require(base % PAGE == 0 and [row[:2] for row in ends] == [(0, base), (1, base + PAGE - 8)],
                f"{name}: invalid dynamically allocated page {ends}")
        require(0x40000000 <= base <= 0x40000000 + (size_mib << 20) - PAGE,
                f"{name}: allocation falls outside virt RAM {base:#x}")
        require(2 <= mapped <= 3, f"{name}: unexpected SCSI request count")
        for (_, cpu, bus, data), actual, access in zip(ends, observed[-2:], transfers[-2:]):
            require((cpu, bus, data) == actual and data == CAPACITY.hex(),
                    f"{name}: production result differs from provider completion {ends}, {observed}")
            require(bus in access, f"{name}: SMMU did not observe reported bus {bus:#x}")
            if name == "bounce":
                require(bus != cpu, f"{name}: expected a distinct staging address")
    else:
        require(not ends and terminal != "Success", f"{name}: published a failed result {lines}")
        if name == "no-provider":
            require(terminal == "Unsupported" and mapped == 0 and "UFS-BUFFER NO PROVIDER" in lines,
                    f"{name}: missing no-provider observation {lines}")
        elif name == "changed-guard":
            require(terminal == "Compromised Data" and 2 <= len(transfers) <= 3,
                    f"{name}: did not detect a changed guard byte {lines}")
            first, last = observed[-2:]
            require(first[0] % PAGE == 0 and last[0] == first[0] + PAGE - 8,
                    f"{name}: unexpected CPU endpoints {lines}")
            for (_, bus, data), access in zip((first, last), transfers[-2:]):
                require(bus in access and data == CAPACITY.hex(), f"{name}: invalid capacity data")
        else:
            require(1 <= len(transfers) <= 2, f"{name}: unexpected head CDB count {lines}")
            cpu, bus, data = observed[-1 - short_count]
            require(bus in transfers[-1], f"{name}: missing matching data transfer")
            submitted = observed[:len(transfers)]
            require(all(sample[0] == cpu for sample in submitted),
                    f"{name}: unexpected second endpoint submission {lines}")
            if name in ("deny-tail", "short-tail"):
                require(terminal in ("Device Error", "No mapping", "Bad Buffer Size")
                        and data == CAPACITY.hex() and cpu % PAGE == 0,
                        f"{name}: unexpected tail error or head data {lines}")
                if short_count:
                    tail_cpu, tail_dma, unchanged = observed[-1]
                    require(tail_cpu == cpu + PAGE - 8 and unchanged == "a5" * 8
                            and all(tail_dma not in x for x in transfers),
                            f"{name}: truncated tail mapping reached the device {lines}")
            else:
                expected = (lun_bytes // PAGE - 1).to_bytes(4, "big") + PAGE.to_bytes(4, "big")
                require(terminal == "Volume Corrupt" and data == expected.hex(),
                        f"{name}: wrong rejected capacity {lines}")
    return {"case": name, "guestRamMiB": size_mib, "lunBytes": lun_bytes if with_ufs else None,
            "terminal": terminal, "mapsAccepted": mapped, "mapsUnmapped": unmapped,
            "mapsRefused": denied, "mapsShortened": short_count, "readCapacityCommands": len(transfers),
            "ufsMediaReads": 0, "ufsMediaWrites": 0,
            "unmapObservations": [{"cpu": hex(cpu), "dma": hex(bus), "bytesAfterUnmap": data}
                                  for cpu, bus, data in observed],
            "endpoints": [{"index": i, "cpu": hex(cpu), "dma": hex(bus), "data": data,
                           "traceSid": UFS_SID} for i, cpu, bus, data in ends]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    fixtures = [("small-ram", 768), ("large-ram", 1536), ("bounce", 768),
                ("wrong-capacity", 768), ("deny-tail", 768), ("short-tail", 768),
                ("changed-guard", 768), ("no-provider", 768)]
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        modules = Path(directory) / "modules"
        modules.mkdir()
        for name in MODULES:
            shutil.copyfile(EFI / name, modules / name)
        module_digests = {name: digest(modules / name) for name in MODULES}
        for name, size in fixtures:
            work = Path(directory) / name
            work.mkdir()
            result = checked_case(work, modules, name, size)
            cases.append(result)
            print(name, result["terminal"], result["endpoints"], flush=True)
    require(cases[0]["endpoints"][0]["cpu"] != cases[1]["endpoints"][0]["cpu"],
            "changing VM RAM size did not relocate the observed allocation")
    report = {"outcome": "PASS-QEMU-SHELL-UFS-BUFFER",
              "qemu": subprocess.check_output(["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
              "machine": MACHINE, "syntheticLun": 4, "lunBackend": "null-co,read-only=on",
              "logicalBlockBytes": PAGE, "testWindowBytes": PAGE,
              "smmuTraceScope": "Correlates UFS requester and bus address. The QEMU bypass/disabled "
                                "event converts permission flags to a boolean. Inbound direction is "
                                "verified by the UFS host Map operation, SCSI command and returned bytes.",
              "firmwareSha256": digest(FIRMWARE),
              "efiSha256": module_digests, "cases": cases,
              "pacificShellDmaAddress": "UNKNOWN"}
    with tempfile.TemporaryDirectory(dir=args.report.parent) as directory:
        temporary_report = Path(directory) / "report.json"
        temporary_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary_report.replace(args.report)


if __name__ == "__main__":
    main()
