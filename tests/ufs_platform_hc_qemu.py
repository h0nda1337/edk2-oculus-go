"""Exercise the production non-discoverable DXE UFS binding against QEMU UFS.
QEMU's board fixture supplies the assigned BAR and per-controller PCI DMA backend.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from logo_disk_qemu import disk
from ufs_shell_buffer_qemu import (CAPACITY, DATA, EFI, FIRMWARE, HEX, LUN_BYTES, MACHINE, PAGE,
                                   SMMU_EVENT, SMMU_TRACE, UFS_SID, digest, launch, require)


MODULES = ("UfsPlatformBuffer.efi", "GoUfsHcDxe.efi", "UfsPassThruDxe.efi")
CASES = (
    ("direct", 768, None), ("relocated", 1536, None), ("bounce", 768, "BOUNCE"),
    ("wrong-geometry", 768, None), ("deny-tail", 768, "DENYTAIL"), ("short-tail", 768, "SHORTMAP"),
    ("missing-dma", 768, "NODMA"), ("other-handle", 768, "OTHERDMA"), ("busy-handoff", 768, "BUSY"),
    ("reject-common", 768, "NOGRANT"), ("failed-revoke", 768, "RETRY"),
    ("allocation", 768, "ALLOC"), ("missing-lun4", 768, "NOLUN4"), ("gpt", 768, "GPT"),
)


def device_trace(lines):
    commands = []
    extents = []
    mmio = {"ufs_mmio_read": 0, "ufs_mmio_write": 0}
    for line in lines:
        if match := re.fullmatch(r"ufs_exec_scsi_cmd slot \d+, lun 0x4, opcode 0x(25|28)", line):
            commands.append((int(match[1], 16), set()))
        elif match := re.fullmatch(r"scsi_disk_dma_command_READ Read \(sector (\d+), count (\d+)\)", line):
            require(commands and commands[-1][0] == 0x28, "disk read outside a LUN 4 READ(10)")
            extents.append([int(match[1]), int(match[2])])
        elif line.partition(" ")[0] in mmio:
            mmio[line.partition(" ")[0]] += 1
        elif line.partition(" ")[0] in SMMU_TRACE:
            event = SMMU_EVENT.fullmatch(line)
            if commands and event and int(event[1], 16) == UFS_SID:
                commands[-1][1].add(int(event[2], 16))
        else:
            raise ValueError(f"Unexpected SCSI command or disk access: {line}")
    return commands, extents, mmio


def run_case(work, modules, name, ram, marker):
    size = LUN_BYTES - PAGE if name == "wrong-geometry" else LUN_BYTES
    backing = None
    before = None
    if name == "gpt":
        backing = work / "gpt.raw"
        disk(backing, b"GO-UFS-PLATFORM\0".ljust(PAGE, b"\0"), "splash",
             sector=PAGE, last_lba=LUN_BYTES // PAGE - 1)
        before = digest(backing)
    log, trace = launch(work, modules, ram, size, marker, True, MODULES, backing,
                        lun=2 if name == "missing-lun4" else 4, extra_events=("ufs_mmio_read", "ufs_mmio_write"))
    lines = [line for line in log.splitlines() if line.startswith("PLATFORM ")]

    def one(pattern):
        found = re.findall(pattern, "\n".join(lines), re.M)
        require(len(found) == 1, f"{name}: {pattern!r} missing or duplicated; {lines}, log: {log[-900:]}")
        return found[0]

    require("PLATFORM PCI DMA SERVICE PRESERVED" in lines, f"{name}: firmware DMA service changed")
    terminal = one(r"^PLATFORM RESULT (.+)$")
    bind, installed = one(r"^PLATFORM BIND (.+) HC ([01]) PCI 0$")
    bar, length = (int(v, 16) for v in one(rf"^PLATFORM RESOURCE ({HEX}) SIZE ({HEX})$"))
    fields = one(r"^PLATFORM COUNTS INIT (\d+) ALLOC (\d+) FREE (\d+) MAP (\d+) GRANT (\d+) "
                 r"REVOKE (\d+) UNMAP (\d+) DENIED (\d+) SHORT (\d+)$")
    init, allocated, freed, mapped, granted, revoked, unmapped, denied, shortened = map(int, fields)
    require(allocated == freed and mapped == unmapped and granted == revoked,
            f"{name}: DMA resources retained after stop {fields}")
    commands, extents, mmio = device_trace(trace)
    capacity = [addrs for op, addrs in commands if op == 0x25]
    observed = [(int(cpu, 16), int(bus, 16), int(n), data.lower()) for cpu, bus, n, data in re.findall(
        rf"^PLATFORM DATA CPU ({HEX}) DMA ({HEX}) MAPPED (\d+) BYTES ({DATA})$", log, re.M)]
    ends = [(int(i), int(cpu, 16), int(bus, 16), data.lower()) for i, cpu, bus, data in re.findall(
        rf"^PLATFORM END (\d+) CPU ({HEX}) DMA ({HEX}) BYTES ({DATA})$", log, re.M)]
    probe_denials, revoke_failures = map(int, one(r"^PLATFORM PROBE DENIED (\d+) REVOKE FAILED (\d+)$"))
    require(probe_denials == int(name == "reject-common") and revoke_failures == int(name == "failed-revoke"),
            f"{name}: incorrect probe grant or revoke observations")
    if installed == "0":
        require(sum(mmio.values()) == 0, f"{name}: MMIO before ownership {mmio}")
    else:
        require(all(mmio.values()), f"{name}: host emitted no HCI MMIO")
    if name == "reject-common":
        require(bind != "Success" and terminal == bind and installed == "0" and init == 1 and not commands
                and not observed and not ends and allocated == mapped == 1 and granted == 0,
                f"{name}: published HC or retained common buffer after provider rejection {lines}")
    elif name in ("missing-dma", "other-handle", "busy-handoff"):
        expected_init = int(name == "busy-handoff")
        require(bind != "Success" and terminal == bind and installed == "0"
                and init == expected_init and not commands and not observed and not ends
                and all(n == "0" for n in fields[1:]), f"{name}: unexpected binding or DMA {lines}")
        if expected_init:
            require(bind == "Not Ready", f"{name}: handoff failure not propagated {bind}")
    else:
        require(bind == "Success" and installed == "1" and init == 1, f"{name}: bind: {lines}")
        require(int(one(rf"^PLATFORM HC BAR ({HEX})$"), 16) == bar, f"{name}: wrong MMIO resource")
        require(one(r"^PLATFORM TRANSPORT (.+)$") == "Success", f"{name}: transport did not bind")
        require(one(r"^PLATFORM STOP TRANSPORT (.+)$") == one(r"^PLATFORM STOP HC (.+)$") == "Success",
                f"{name}: orderly driver stop failed")
        require(allocated > 0 and mapped >= granted > 0, f"{name}: missing DMA handoff {fields}")
        require(denied == int(name == "deny-tail") and shortened == int(name == "short-tail"),
                f"{name}: bad fixture injection {fields}")
        drop = denied + shortened
        require(len(observed) == len(capacity) + drop, f"{name}: unmatched data map or submission {lines}")
        # The last successful head/tail request(s) carry data. The first command
        # may raise unit attention without causing any inbound DMA.
        expected = (size // PAGE - 1).to_bytes(4, "big") + PAGE.to_bytes(4, "big")
        matches = [(cpu, bus, n, data) for (cpu, bus, n, data), access in zip(observed, capacity)
                   if bus in access and n == 8 and data == expected.hex()]
        if name in ("deny-tail", "short-tail", "wrong-geometry"):
            require(terminal != "Success" and not ends and len(matches) == 1,
                    f"{name}: unexpected result for incomplete capacity pair {lines}")
            require(matches[0][0] % PAGE == 0, f"{name}: first request was not the page head")
            if drop:
                cpu, bus, n, data = observed[-1]
                require(cpu == matches[0][0] + PAGE - 8 and n == (4 if shortened else 8)
                        and data == "a5" * 8 and all(bus not in addresses for addresses in capacity),
                        f"{name}: failed tail mapping was submitted or modified")
            else:
                require(terminal == "Volume Corrupt", f"{name}: incorrect geometry accepted")
        elif name == "missing-lun4":
            require(terminal == "Success" and not commands and not ends and not observed
                    and "PLATFORM BDS LUN 4 ABSENT" in lines, f"{name}: command sent to another LUN")
        elif name == "failed-revoke":
            require(terminal == "Device Error" and not ends and len(matches) == 2
                    and matches[-1][0] == matches[0][0] + PAGE - 8,
                    f"{name}: lost map token or published result after provider failure {lines}")
        else:
            require(terminal == "Success" and len(matches) == 2, f"{name}: endpoint data {lines}")
            if name == "allocation":
                require("PLATFORM OWNED ALLOCATION VERIFIED" in lines, f"{name}: invalid page ownership")
            head, tail = matches
            require(head[0] % PAGE == 0 and tail[0] == head[0] + PAGE - 8
                    and expected == CAPACITY, f"{name}: inconsistent CPU page")
            if name == "bounce":
                require(all(cpu != bus for cpu, bus, _, _ in matches), f"{name}: expected nonidentity DMA")
            if name == "gpt":
                require(not ends and "PLATFORM BDS GPT MARKER FOUND" in lines, f"{name}: absent GPT marker")
            else:
                require(ends == [(i, cpu, bus, data) for i, (cpu, bus, _, data) in enumerate(matches)],
                        f"{name}: reported address differs from controller map {ends}, {matches}")
        if name != "missing-lun4":
            count = range(2, 4) if terminal == "Success" or name == "failed-revoke" else range(1, 3)
            require(len(capacity) in count, f"{name}: unexpected number of READ CAPACITY requests")

    ops = [op for op, _ in commands]
    if name == "gpt":
        require(ops == [0x25] * len(capacity) + [0x28] * 3 and extents == [[1, 1], [2, 4], [2048, 1]],
                f"GPT read ordering/range mismatch: {ops}, {extents}")
        require(digest(backing) == before, "virtual LUN changed")
    else:
        require(ops == [0x25] * len(capacity) and not extents, f"{name}: sector I/O before GPT case")
    return {"case": name, "guestRamMiB": ram, "result": terminal, "hostBinding": bind, "hcPublished": installed == "1",
            "mmioTraceCounts": mmio, "resourceBase": hex(bar), "resourceBytes": length, "initializeCalls": init,
            "commonAllocations": allocated, "commonFrees": freed, "maps": mapped, "grants": granted,
            "revocations": revoked, "revokeFailures": revoke_failures, "probeGrantDenials": probe_denials, "unmaps": unmapped, "deniedTailGrants": denied, "shortTailMaps": shortened,
            "lun4ScsiOpcodes": [f"0x{op:02x}" for op in ops], "lun4Read10Extents": extents,
            "ufsSectorWrites": 0, "backingSha256BeforeAndAfter": before,
            "capacityObservations": [{"cpu": hex(cpu), "dma": hex(bus), "mappedBytes": n, "bytes": data}
                                     for cpu, bus, n, data in observed],
            "traceSha256": hashlib.sha256("\n".join(trace).encode()).hexdigest(),
            "guestLog": lines}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        modules = Path(tmp) / "modules"
        modules.mkdir()
        for name in MODULES:
            shutil.copyfile(EFI / name, modules / name)
        binaries = {name: digest(modules / name) for name in MODULES}
        for name, ram, marker in CASES:
            work = Path(tmp) / name
            work.mkdir()
            row = run_case(work, modules, name, ram, marker)
            print(name, row["result"], row["lun4ScsiOpcodes"], flush=True)
            results.append(row)
    require(results[0]["capacityObservations"][-2]["cpu"] != results[1]["capacityObservations"][-2]["cpu"],
            "changing guest RAM did not relocate the Shell page")
    report = {"outcome": "PASS-QEMU-PLATFORM-UFS", "qemu": subprocess.check_output(
                  ["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
              "machine": MACHINE, "firmwareSha256": digest(FIRMWARE), "efiSha256": binaries,
              "virtualBus": "Non-discoverable UFS resource + controller-local GoUfsPlatformDma (EDKII_IOMMU_PROTOCOL ABI)",
              "pciBackend": "QEMU PCI BAR and PciIo DMA; UfsPciHcDxe omitted",
              "checkedAccess": "Fixture enforces operation-specific grant/revoke on the platform handle. "
                               "QEMU's SMMU trace correlates the virtual requester and bus addresses.",
              "pacificPhysicalDmaAddress": "UNKNOWN", "cases": results}
    with tempfile.TemporaryDirectory(dir=args.report.parent) as tmp:
        path = Path(tmp) / "evidence.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        path.replace(args.report)


if __name__ == "__main__":
    main()
