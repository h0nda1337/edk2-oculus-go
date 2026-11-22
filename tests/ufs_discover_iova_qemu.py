"""Discover a UFS DMA address from the live QEMU virt SMMUv3 stage-2 tables.

Host qtest, stopped guest, fixture-owned table memory. The monitor accepts only
the stage-2/32-bit-input/4-KiB-leaf profile constructed by set_translation().
It is not an SMMU driver or a physical Pacific probe.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from ufs_data_qemu import CAPACITY, LUN_BYTES, unit_args
from ufs_lk_nop_qemu import BAR, MACHINE, TM, check, controller
from ufs_nop11_bus import PAGE, WINDOW, seed_lk, set_translation
from ufs_owned_bus_qemu import capacity


SMMU = 0x09050000  # QEMU virt SMMUv3 MMIO
UFS_SID = 8        # QEMU virt 00:01.0 -> RID 8 -> SID 8
OWNED_PAGE = WINDOW + PAGE
STREAM_START, TABLE_START, TABLE_END = 0x40500000, 0x40510000, 0x40520000
PA_MASK = ((1 << 40) - 1) & -PAGE  # STE.S2PS = 2
SEED = bytes([0xA5])


class Refused(ValueError):
    """The observer cannot authorize an endpoint transfer from this evidence."""


def discover(bus, sid, target):
    if target != OWNED_PAGE:
        raise Refused("page not reserved for this test")
    if bus.read32(SMMU + 0x20) != 1 or bus.read32(SMMU + 0x24) != 1:
        raise Refused("SMMU not enabled in fixture mode")
    cfg = bus.read32(SMMU + 0x88)
    if cfg != 5 or not 0 <= sid < (1 << cfg):
        raise Refused("unsupported stream table")
    stream_table = int(bus.command(f"readq {SMMU + 0x80:#x}")[0], 16)
    stream_size = 64 << cfg
    if stream_table & (stream_size - 1):
        raise Refused("unsupported stream table base")
    if not STREAM_START <= stream_table <= TABLE_START - stream_size:
        raise Refused("stream table outside fixture allocation")
    entry = bus.read(stream_table + sid * 64, 64)
    words = struct.unpack("<8Q", entry)
    # V=1, Config=S2; S2T0SZ=32, SL0=L1, TG0=4K, PS=40, AA64.
    geometry = 32 | (1 << 6) | (2 << 16) | (1 << 19)
    if (words[0:2] != (13, 0) or words[2] != ((geometry << 32) | 1) or
            words[3] & ~PA_MASK or any(words[4:])):
        raise Refused("unsupported STE or translation geometry")
    root = words[3]
    visited = set()
    matches = []

    def walk(table, shift, prefix):
        if not TABLE_START <= table <= TABLE_END - PAGE:
            raise Refused("translation table outside fixture allocation")
        if table in visited:
            raise Refused("shared or cyclic translation table")
        visited.add(table)
        descriptors = struct.unpack("<512Q", bus.read(table, PAGE))
        entries = descriptors[:4] if shift == 30 else descriptors
        for index, descriptor in enumerate(entries):
            if not descriptor & 1:
                continue
            address = descriptor & PA_MASK
            iova = prefix | (index << shift)
            if shift > 12:
                if descriptor != address | 3:
                    raise Refused("unsupported table or block descriptor")
                walk(address, shift - 9, iova)
            else:
                # Permit only ordinary fixture page attributes, S2AP and AF.
                if descriptor & ~(PA_MASK | 0x4C0) != 0x3F:
                    raise Refused("unsupported leaf attributes")
                if address == target:
                    matches.append((iova, descriptor))

    walk(root, 30, 0)
    if not matches:
        raise Refused("page absent")
    if len(matches) != 1:
        raise Refused("ambiguous alias")
    iova, descriptor = matches[0]
    if descriptor & 0x480 != 0x480:  # AF and S2AP[1] (write)
        raise Refused("endpoint not writable or AF clear")
    return iova, stream_table, root, len(visited)


def configure_table_case(bus, name):
    # Pause translation while preparing the alternate fixture, before any UFS
    # traffic. The walker receives neither of these addresses as an argument.
    bus.write32(SMMU + 0x20, 0)
    bus.wait_bits(SMMU + 0x24, 1, 0)
    stream = STREAM_START
    ste = stream + 64 * UFS_SID
    if name == "unique-b":
        new_root = TABLE_END - PAGE
        stream += PAGE
        bus.write(new_root, bus.read(TABLE_START, PAGE))
        bus.write(stream, bus.read(STREAM_START, 32 * 64))
        bus.write(stream + 64 * UFS_SID + 24, struct.pack("<Q", new_root))
        bus.write(STREAM_START, bytes(32 * 64))
        bus.write(TABLE_START, bytes(PAGE))
    elif name == "foreign-stream-table":
        stream = TABLE_END
    elif name == "foreign-root":
        bus.write(ste + 24, struct.pack("<Q", TABLE_END))
    elif name == "foreign-child":
        bus.write(TABLE_START, struct.pack("<Q", TABLE_END | 3))
    bus.command(f"writeq {SMMU + 0x80:#x} {stream:#x}")
    bus.write32(SMMU + 0x20, 1)
    bus.wait_bits(SMMU + 0x24, 1, 1)


def restrict_fixture_leaf(bus, iova, clear):
    # Builder side only. Change permissions before any emulated UFS request.
    table = TABLE_START  # root allocated by set_translation
    for shift in (30, 21):
        address = table + 8 * ((iova >> shift) & 511)
        table = struct.unpack("<Q", bus.read(address, 8))[0] & PA_MASK
    address = table + 8 * ((iova >> 12) & 511)
    leaf = struct.unpack("<Q", bus.read(address, 8))[0]
    bus.write(address, struct.pack("<Q", leaf & ~clear))


def endpoints(bus, iova):
    control = TM + 640 + 256
    initial = capacity(bus, control)
    check(initial[7] == 2 and initial[36] & 15 == 6, "missing initial unit attention")
    check(capacity(bus, control)[7] == 0 and bus.read(control, 8) == CAPACITY, "bad control")
    expected = bytearray(SEED * (PAGE * 4))
    bus.write(WINDOW, expected)
    alias_guard = bytes([0x5A]) * PAGE
    bus.write(iova, alias_guard)
    rows = []
    for offset in (0, PAGE - 8):
        reply = capacity(bus, iova + offset)
        check(reply[6:8] == bytes(2) and reply[12:16] == bytes(4), "SCSI status or residual")
        expected[PAGE + offset:PAGE + offset + 8] = CAPACITY
        check(bus.read(WINDOW, len(expected)) == expected, "DMA destination or guards")
        check(bus.read(iova, PAGE) == alias_guard, "numeric alias was modified")
        rows.append({"offset": offset, "bus": hex(iova + offset), "payload": CAPACITY.hex()})
    return rows


def trial(tmp, name, fixture_iova, refusal):
    machine = [arg.replace("1280M", "1536M").replace("virt,highmem=off", "virt,highmem=off,iommu=smmuv3")
               for arg in MACHINE]
    leaves = [] if name == "absent" else [(fixture_iova, OWNED_PAGE)]
    target, sid = OWNED_PAGE, UFS_SID
    if name == "aliased":
        leaves.append((fixture_iova + 2 * PAGE, OWNED_PAGE))
    if name == "other-backing":
        leaves = [(fixture_iova, OWNED_PAGE + PAGE)]
    if name == "not-owned":
        target += PAGE
        leaves = [(fixture_iova, target)]
    if name == "other-stream":
        sid += 1
    with controller(tmp, 0x3F000000, BAR, machine=machine, units=unit_args(LUN_BYTES)) as bus:
        set_translation(bus, leaves)
        if name in ("unique-b", "foreign-stream-table", "foreign-root", "foreign-child"):
            configure_table_case(bus, name)
        if name in ("read-only", "af-clear"):
            restrict_fixture_leaf(bus, fixture_iova, 0x80 if name == "read-only" else 0x400)
        try:
            found, stream, root, tables = discover(bus, sid, target)
        except Refused as exc:
            check(refusal == str(exc), f"{name}: unexpected refusal {exc}")
            result = {"case": name, "refused": str(exc), "capacityCommands": 0}
        else:
            check(refusal is None and found == fixture_iova, f"{name}: wrong authorization or IOVA")
            seed_lk(bus)
            result = {"case": name, "discoveredBus": hex(found), "tablesRead": tables,
                      "streamTable": hex(stream), "translationRoot": hex(root),
                      "endpoints": endpoints(bus, found), "capacityCommands": 4}
    commands = (tmp / "ufs.trace").read_text().splitlines()
    allowed = [] if refusal else ["ufs_exec_nop_cmd UTRLDBR slot 0"] + [
        "ufs_exec_scsi_cmd slot 1, lun 0x4, opcode 0x25"] * 4
    check(commands == allowed, f"{name}: unexpected device trace {commands}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    cases = [
        ("unique-a", 0x81673000, None), ("unique-b", 0x88AD0000, None),
        ("absent", 0x81673000, "page absent"), ("other-backing", 0x81673000, "page absent"),
        ("aliased", 0x81673000, "ambiguous alias"), ("not-owned", 0x81673000, "page not reserved for this test"),
        ("read-only", 0x81673000, "endpoint not writable or AF clear"),
        ("af-clear", 0x81673000, "endpoint not writable or AF clear"),
        ("other-stream", 0x81673000, "unsupported STE or translation geometry"),
        ("foreign-stream-table", 0x81673000, "stream table outside fixture allocation"),
        ("foreign-root", 0x81673000, "translation table outside fixture allocation"),
        ("foreign-child", 0x81673000, "translation table outside fixture allocation"),
    ]
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for name, setup_bus, refusal in cases:
            tmp = Path(directory) / name
            tmp.mkdir()
            row = trial(tmp, name, setup_bus, refusal)
            rows.append(row)
            print(name, row.get("discoveredBus", row.get("refused")), flush=True)
    report = {"outcome": "PASS-QEMU-REVERSE-S2", "physicalPacificBus": "UNKNOWN",
              "cpuPage": hex(OWNED_PAGE), "provider": "qtest virt PCI UFS, SMMUv3 stage 2",
              "qemu": subprocess.check_output([MACHINE[0], "--version"], text=True).splitlines()[0],
              "cases": rows, "mediaReads": 0, "mediaWrites": 0}
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
