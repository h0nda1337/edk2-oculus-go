"""Verify takeover of running, idle UFS legacy lists using emulator MMIO and DMA traces.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from shell_prompt_qemu import inspect_pacific
from ufs_platform_hc_qemu import MODULES
from ufs_shell_buffer_qemu import (CAPACITY, DATA, EFI, FIRMWARE, HEX, LUN_BYTES, MACHINE, PAGE,
                                   SMMU_EVENT, SMMU_TRACE, UFS_SID, digest, launch, require)


HCE, UTR, TRDB, TRRS, UTM, TMDB, TMRS = 0x34, 0x50, 0x58, 0x60, 0x70, 0x78, 0x80
MMIO = re.compile(r"ufs_mmio_(read|write) addr 0x([0-9a-f]+) data 0x([0-9a-f]+) size 4")
SCSI = re.compile(r"ufs_exec_scsi_cmd slot (\d+), lun 0x4, opcode 0x25")
EXTRA_EVENTS = ("ufs_mmio_read", "ufs_mmio_write", "ufs_err_unsupport_register_offset")
MODEL_PATCH = Path(__file__).resolve().parent / "qemu/ufs-idle-task-list-10.0.13.patch"


@dataclass(frozen=True)
class Event:
    kind: str
    reg: int
    value: int


def decode(lines):
    events = []
    for line in lines:
        if match := MMIO.fullmatch(line):
            events.append(Event(match[1], int(match[2], 16), int(match[3], 16)))
        elif match := SCSI.fullmatch(line):
            events.append(Event("capacity", int(match[1]), 0x25))
        elif line.partition(" ")[0] in SMMU_TRACE:
            # virt's unconfigured SMMUv3 takes bypass. Record this requester's
            # address for each translation, including descriptor and data accesses.
            if f"sid={UFS_SID:#x} " in line:
                match = SMMU_EVENT.fullmatch(line)
                require(match is not None, f"unrecognized translation for UFS: {line}")
                events.append(Event("dma", int(match[2], 16), 0))
        elif line.startswith("ufs_err_unsupport_register_offset "):
            match = re.fullmatch(r"ufs_err_unsupport_register_offset Register offset 0x([0-9a-f]+) is not yet supported", line)
            require(match, f"unrecognized unsupported-register event: {line}")
            events.append(Event("unsupported", int(match[1], 16), 0))
        else:
            raise ValueError(f"unexpected command, disk I/O, or trace event: {line}")
    return events


def select(events, kind, reg=None, value=None, start=0, stop=None):
    return [i for i in range(start, len(events) if stop is None else stop)
            if events[i].kind == kind and (reg is None or events[i].reg == reg)
            and (value is None or events[i].value == value)]


def one(items, description):
    require(len(items) == 1, f"expected one {description}, found {items}")
    return items[0]


def queue_registers(pair):
    utr, utm = pair
    return {UTR: utr & 0xffffffff, UTR + 4: utr >> 32, UTM: utm & 0xffffffff, UTM + 4: utm >> 32}


def verify_seed(events, old, stock):
    old_starts = select(events, "write", HCE, 1)
    require(old_starts, "owner never enabled HCE")
    first = old_starts[0]
    off = select(events, "write", HCE, 0, first + 1)
    require(off, "controller remained enabled at shutdown")
    stop = off[0]
    values = queue_registers(old)
    for reg, val in values.items():
        prog = one(select(events, "write", reg, start=first + 1, stop=stop), f"inherited base write at {reg:#x}")
        require(events[prog].value == val and select(events, "read", reg, val, prog + 1, stop),
                f"inherited base {reg:#x} was not confirmed")
    for reg in (TRRS, TMRS):
        one(select(events, "write", reg, 1, first + 1, stop), f"inherited queue run at {reg:#x}")
    # Snapshot must precede any stop even if the original owner cleans up a rejection.
    stops = [i for reg in (TRRS, TMRS) for i in select(events, "write", reg, 0, first + 1, stop)]
    before_stop = min([stop, *stops])
    ready = max(i for reg in (TRRS, TMRS) for i in select(events, "write", reg, 1, first + 1, stop)) + 1
    for reg, value in {HCE: 1, TRRS: 1, TMRS: int(not stock), TRDB: 0, TMDB: 0}.items():
        reads = select(events, "read", reg, start=ready, stop=before_stop)
        require(reads and all(events[i].value == value for i in reads),
                f"owner observation missing or changed at {reg:#x} (expected {value})")
    for reg in (TRDB, TMDB):
        require(not select(events, "write", reg, start=first, stop=stop), f"doorbell before takeover at {reg:#x}")
    for address in old:
        require(address and address % 1024 == 0, "inherited list is zero or misaligned")
        page = address & ~(PAGE - 1)
        require(not any(e.kind == "dma" and page <= e.reg < page + PAGE for e in events),
                f"device accessed the inherited queue page at {address:#x}")
    require(old[0] != old[1], "inherited queue addresses alias")
    require(bool(select(events, "unsupported", TMRS)) == stock, "unexpected QEMU UTMRLRSR support")
    return stop


def verify_takeover(events, old, new, endpoints):
    stop = verify_seed(events, old, stock=False)
    require([e.value for e in events if (e.kind, e.reg) == ("write", HCE)] == [1, 0, 1, 0],
            "unexpected HCE transition or missing final stop")
    for reg, val in queue_registers(old).items():
        reads = select(events, "read", reg, stop=stop)
        require(len(reads) >= 3 and all(events[i].value == val for i in reads),
                "initial owner and two DXE samples did not agree on inherited list bases")
    require(set(old).isdisjoint(new) and len(set(new)) == 2, "old and new queue bases alias")
    start = one(select(events, "write", HCE, 1, stop + 1), "re-enable HCE")
    require(select(events, "read", HCE, 0, stop + 1, start), "missing disabled readback before HCE re-enable")
    rings = select(events, "write", TRDB, start=start + 1)
    require(rings and all(events[i].value > 0 for i in rings), "no transfer submissions")
    require(not select(events, "write", TMDB), "unexpected task-management request")
    first_ring = rings[0]
    enabled = select(events, "read", HCE, 1, start + 1, first_ring)
    require(enabled, "HCE enable never observed before submission")
    for reg, base in queue_registers(new).items():
        prog = one(select(events, "write", reg, start=stop + 1), f"new base write at {reg:#x}")
        run_reg = TRRS if reg in (UTR, UTR + 4) else TMRS
        run = one(select(events, "write", run_reg, 1, start=stop + 1), f"new list run {run_reg:#x}")
        require(enabled[0] < prog < run < first_ring and events[prog].value == base,
                f"DXE list {reg:#x} programmed incorrectly or out of order")
    commands = select(events, "capacity")
    require(2 <= len(commands) <= 3, "expected two completed capacities with optional unit attention")
    require(not select(events, "write", HCE, 0, start + 1, commands[-1]), "controller reset during submissions")
    for reg, val in {**queue_registers(new), TRRS: 1, TMRS: 1}.items():
        require(select(events, "read", reg, val, start + 1, commands[0]) and
                select(events, "read", reg, val, commands[-1] + 1),
                f"new queue register {reg:#x} not verified around capacity pair")
    for i, command in enumerate(commands):
        slot = events[command].reg
        previous = [ring for ring in rings if ring < command]
        require(previous and events[previous[-1]].value == 1 << slot, "CDB missing matching transfer doorbell")
        ring = previous[-1]
        require(select(events, "dma", new[0] + slot * 32, start=ring + 1, stop=command),
                "no device access to the submitted UTRD in the DXE queue")
        if i >= len(commands) - 2:
            end = endpoints[i - (len(commands) - 2)]
            next_ring = next((r for r in rings if r > command), len(events))
            require(select(events, "dma", end, start=command + 1, stop=next_ring),
                    "device did not access reported data endpoint in this command")
    require(select(events, "write", HCE, 0, commands[-1] + 1), "transport did not shut down")
    return {"hceWrites": [e.value for e in events if (e.kind, e.reg) == ("write", HCE)],
            "legacyRunsBeforeReset": [1, 1], "legacyDoorbellsBeforeReset": [0, 0],
            "dxeBasesProgrammedBeforeFirstDoorbell": True, "readCapacityLun4": len(commands),
            "oldQueuePageDmaEvents": 0, "taskManagementRequests": 0, "sectorReads": 0, "sectorWrites": 0}


def verify_denial(events, old, stock):
    verify_seed(events, old, stock)
    for reg, value in queue_registers(old).items():
        positions = select(events, "write", reg)
        require(len(positions) == 1 and events[positions[0]].value == value, "old base was replaced")
    require(len(select(events, "write", HCE, 1)) == 1, "controller re-enabled after denial")
    seeded = max(select(events, "write", TRRS, 1) + select(events, "write", TMRS, 1))
    writes = [(e.reg, e.value) for e in events[seeded + 1:] if e.kind == "write"]
    require(writes == [(TMRS, 0), (TRRS, 0), (HCE, 0)],
            f"unexpected register write before or during previous owner's cleanup: {writes}")
    require(not any(e.kind in ("capacity", "dma") or (e.kind == "write" and e.reg in (TRDB, TMDB))
                    for e in events), "command, DMA or doorbell after denial")
    return {"legacyRunsBeforeCleanup": [1, int(not stock)], "legacyDoorbellsBeforeCleanup": [0, 0],
            "taskRunUnsupportedEvent": stock, "readCapacityLun4": 0, "sectorReads": 0, "sectorWrites": 0}


def mutations(events, old, new, endpoints):
    """Perturb the passing trace so an oracle regression cannot pass on guest printouts alone."""
    reset = select(events, "write", HCE, 0)[0]
    start = select(events, "write", HCE, 1, reset + 1)[0]
    program = select(events, "write", UTR, start=start)[0]
    ring = select(events, "write", TRDB)[0]
    command = select(events, "capacity")[0]
    last_ring = [i for i in select(events, "write", TRDB) if i < command][-1]
    conf = select(events, "read", HCE, 0, reset + 1, start)
    tail = select(events, "capacity")[-1]
    variants = {
        "missing-disable-readback": [e for i, e in enumerate(events) if i not in conf],
        "pending-inherited-transfer": events[:reset] + [Event("read", TRDB, 1)] + events[reset:],
        "pending-inherited-task": events[:reset] + [Event("read", TMDB, 1)] + events[reset:],
        "inherited-base-reused": events[:program] + [Event("write", UTR, old[0] & 0xffffffff)] + events[program + 1:],
        "base-installed-after-doorbell": events[:program] + events[program + 1:ring + 1] + [events[program]] + events[ring + 1:],
        "no-device-utr-fetch": [e for i, e in enumerate(events)
                                if not (last_ring < i < command and e.kind == "dma" and e.reg == new[0])],
        "controller-touched-previous-queue": events + [Event("dma", old[0], 0)],
        "capacity-tail-dma-missing": [e for i, e in enumerate(events)
                                     if not (i > tail and e.kind == "dma" and e.reg == endpoints[-1])],
    }
    rejected = []
    for label, variant in variants.items():
        try:
            verify_takeover(variant, old, new, endpoints)
        except ValueError:
            rejected.append(label)
        else:
            raise ValueError(f"oracle accepted mutation {label}")
    for invalid in ("ufs_exec_scsi_cmd slot 0, lun 0x2, opcode 0x25",
                    "scsi_disk_dma_command_READ Read (sector 1, count 1)",
                    "scsi_disk_dma_command_WRITE Write (sector 1, count 1)"):
        try:
            decode([invalid])
        except ValueError:
            rejected.append(invalid.split()[0] + ":rejected")
        else:
            raise ValueError(f"oracle admitted {invalid}")
    return rejected


def get_line(lines, pattern):
    return one(re.findall("^" + pattern + "$", "\n".join(lines), re.M), pattern)


def run_case(work, modules, qemu, ram, marker, stock, check_mutations):
    log, trace = launch(work, modules, ram, LUN_BYTES, marker, True, MODULES, qemu=qemu, extra_events=EXTRA_EVENTS)
    lines = [line for line in log.splitlines() if line.startswith("PLATFORM ")]
    events = decode(trace)
    old = tuple(int(v, 16) for v in get_line(lines, rf"PLATFORM OLD UTR ({HEX}) UTM ({HEX})"))
    snap = tuple(int(v, 16) for v in get_line(lines, rf"PLATFORM INITIAL HCE ({HEX}) TRR ({HEX}) TMR ({HEX}) "
                                                    rf"TRD ({HEX}) TMD ({HEX})"))
    require(snap == (1, 1, int(not stock), 0, 0), f"guest/emulator initial state mismatch: {snap}")
    result = get_line(lines, r"PLATFORM RESULT (.+)")
    require("PLATFORM OLD BUFFERS FREED" in lines and "PLATFORM FIXTURE RELEASED" in lines,
            f"cleanup of previous owner and virtual board incomplete: {lines}")
    counts = [int(v) for v in get_line(lines, r"PLATFORM COUNTS INIT (\d+) ALLOC (\d+) FREE (\d+) "
                                              r"MAP (\d+) GRANT (\d+) REVOKE (\d+) UNMAP (\d+) DENIED (\d+) SHORT (\d+)")]
    accepted = not stock and marker == "TAKEOVER"
    if accepted:
        require(result == "Success" and "PLATFORM RELEASE GRANTED" in lines and "PLATFORM OLD PRESERVED" in lines
                and "PLATFORM NEW MAPS STILL LIVE" in lines and "PLATFORM BIND Success HC 1 PCI 0" in lines
                and "PLATFORM TRANSPORT Success" in lines
                and "PLATFORM STOP TRANSPORT Success" in lines and "PLATFORM STOP HC Success" in lines,
                f"handoff, data, queue preservation or cleanup failed: {lines}")
        new = tuple(int(v, 16) for v in get_line(lines, rf"PLATFORM NEW UTR ({HEX}) UTM ({HEX})"))
        ends = [(int(i), int(cpu, 16), int(dma, 16), data.lower())
                for i, cpu, dma, data in re.findall(rf"^PLATFORM END (\d+) CPU ({HEX}) DMA ({HEX}) BYTES ({DATA})$",
                                                    "\n".join(lines), re.M)]
        require(len(ends) == 2 and [e[0] for e in ends] == [0, 1] and ends[0][1] % PAGE == 0
                and ends[1][1] == ends[0][1] + PAGE - len(CAPACITY)
                and all(e[3] == CAPACITY.hex() for e in ends), "wrong geometry or endpoint pair")
        endpoints = [e[2] for e in ends]
        data_maps = [(int(cpu, 16), int(dma, 16), int(n), data.lower()) for cpu, dma, n, data in
                     re.findall(rf"^PLATFORM DATA CPU ({HEX}) DMA ({HEX}) MAPPED (\d+) BYTES ({DATA})$",
                                "\n".join(lines), re.M)]
        checks = verify_takeover(events, old, new, endpoints)
        require(len(data_maps) == checks["readCapacityLun4"] and
                data_maps[-2:] == [(cpu, dma, 8, data) for _, cpu, dma, data in ends], "capacity map mismatch")
        init, alloc, freed, mapped, granted, revoked, unmapped, denied, short = counts
        require(init == 1 and alloc == freed > 0 and mapped == unmapped >= granted == revoked > 0 and
                denied == short == 0, f"binding leaked DMA resources: {counts}")
        checks.update({"newQueues": [hex(x) for x in new], "endpoints": [
            {"cpu": hex(cpu), "bus": hex(bus), "bytes": data} for _, cpu, bus, data in ends]})
        checks["smmuTraceModesAtVirtualUfsSid"] = sorted({line.split()[0] for line in trace
                                                          if line.startswith("smmuv3_translate_")
                                                          and f"sid={UFS_SID:#x} " in line})
        if check_mutations:
            checks["rejectedTraceMutations"] = mutations(events, old, new, endpoints)
    else:
        require(counts == [int(not stock)] + [0] * 8, f"DXE allocated or granted DMA on rejection: {counts}")
        require(result != "Success" and "PLATFORM OWNER CLEANUP" in lines and "PLATFORM RELEASE GRANTED" not in lines and not any(
            line.startswith(("PLATFORM NEW ", "PLATFORM END ", "PLATFORM DATA ")) for line in lines),
            f"takeover succeeded on a negative control: {lines}")
        if stock:
            require(result == "Unsupported" and not any(line.startswith(("PLATFORM BIND ", "PLATFORM RELEASE "))
                                                         for line in lines), f"stock model guard: {lines}")
        else:
            require(result == "Access Denied" and "PLATFORM RELEASE DENIED" in lines and "PLATFORM OLD PRESERVED" in lines
                    and "PLATFORM BIND Access Denied HC 0 PCI 0" in lines, f"previous owner lost the controller: {lines}")
        checks = verify_denial(events, old, stock)
    return {"mode": marker, "stockModel": stock, "ramMiB": ram, "guestResult": result,
            "inheritedQueues": [hex(x) for x in old], **checks, "guestLog": lines,
            "traceSha256": hashlib.sha256(("\n".join(trace) + "\n").encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, help="QEMU with the legacy task-list run/stop fixture")
    parser.add_argument("--stock-qemu", default="qemu-system-aarch64")
    parser.add_argument("--normal-build", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    driver_dir = args.normal_build / "AARCH64"
    normal = inspect_pacific(args.normal_build / "FV/OCULUS_GO_DIRECT.fd", driver_dir / "Shell.efi")
    with tempfile.TemporaryDirectory() as tmp:
        modules = Path(tmp) / "modules"
        modules.mkdir()
        for filename in MODULES:
            shutil.copyfile((EFI if filename == MODULES[0] else driver_dir) / filename, modules / filename)
        binaries = {name: digest(modules / name) for name in MODULES}
        for driver in MODULES[1:]:
            require(binaries[driver] == normal["ufsDriverPeSha256"][Path(driver).stem], f"{driver} != NORMAL FV")
        cases = []
        for name, emulator, ram, marker, stock in (
                ("stock-control", args.stock_qemu, 768, "TAKEOVER", True),
                ("owner-retained", args.qemu, 768, "NORELEASE", False),
                ("owner-released", args.qemu, 768, "TAKEOVER", False),
                ("relocated", args.qemu, 1536, "TAKEOVER", False)):
            work = Path(tmp) / name
            work.mkdir()
            row = run_case(work, modules, emulator, ram, marker, stock, name == "owner-released")
            cases.append({"name": name, **row})
            print(name, row["guestResult"], row["readCapacityLun4"], flush=True)
        require(cases[2]["inheritedQueues"] != cases[3]["inheritedQueues"] and
                cases[2]["newQueues"] != cases[3]["newQueues"] and
                cases[2]["endpoints"][0]["cpu"] != cases[3]["endpoints"][0]["cpu"],
                "relocated boot reused fixed queue addresses or the Shell buffer")
    emulators = {}
    for key, binary in (("extended", args.qemu), ("stock", args.stock_qemu)):
        location = shutil.which(str(binary))
        require(location, f"emulator {binary} missing")
        emulators[key] = {"version": subprocess.check_output([location, "--version"], text=True).splitlines()[0],
                          "binarySha256": digest(Path(location))}
    report = {"outcome": "PASS-QEMU-UFS-DXE-TAKEOVER", "machine": MACHINE,
              "emulators": emulators, "idleTaskListModelPatchSha256": digest(MODEL_PATCH), "firmwareSha256": digest(FIRMWARE),
              "normalFdSha256": normal["fdSha256"], "efiSha256": binaries,
              "lun": {"id": 4, "logicalBlocks": LUN_BYTES // PAGE, "blockBytes": PAGE, "readOnly": True,
                      "backend": "null-co"},
              "virtualPciRequesterId": hex(UFS_SID),
              "scope": "Virtual PCI DMA provider and explicit transfer of ownership from a synthetic previous owner. "
                       "Pacific queue ownership, SID and bus mappings remain unverified.",
              "cases": cases}
    with tempfile.TemporaryDirectory(dir=args.report.parent) as tmp:
        out = Path(tmp) / "evidence.json"
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        out.replace(args.report)


if __name__ == "__main__":
    main()
