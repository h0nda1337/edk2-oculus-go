"""Match a synthetic SMMUv2 stream snapshot to a known QEMU UFS requester.
The transfer engine and its SMMUv3 are QEMU devices. The SMMUv2 registers
are input samples in the host test, never physical register reads.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from ufs_data_qemu import CAPACITY, LUN_BYTES, unit_args
from ufs_discover_iova_qemu import OWNED_PAGE, Refused, SMMU, STREAM_START, TABLE_START, discover
from ufs_lk_nop_qemu import BAR, MACHINE, TM, check, controller
from ufs_nop11_bus import PAGE, WINDOW, seed_lk, set_translation
from ufs_owned_bus_qemu import capacity


PCI_ECAM = 0x3f000000
RID = 1 << 3  # fixture attaches 00:01.0
IOVA = 0x85120000
VALID = 1 << 31
BYPASS, FAULT = 1 << 16, 2 << 16
CB = 3
SID_BITS = 8
SID_MASK = (1 << SID_BITS) - 1
PROFILE_ID0 = (1 << 29) | (1 << 27) | (SID_BITS << 9) | 4
# Test profile only. S2 AArch64, 32-bit IPA, initial level 1, 40-bit PA.
VTCR_GEOMETRY = 32 | (1 << 6) | (2 << 16)
REVIEWED_BANK = (1, 1, 1, (1 << 31) | VTCR_GEOMETRY, TABLE_START)  # CBAR, CBA2R, SCTLR, TTBCR, TTBR0
MACHINE_ARGS = [x.replace("1280M", "1536M").replace("virt,highmem=off", "virt,highmem=off,iommu=smmuv3")
                for x in MACHINE]


@dataclass(frozen=True)
class Snapshot:
    # Four synthetic non-secure, non-EXIDS stream match groups. Fault on unmatched.
    pairs: tuple
    id0: int = PROFILE_ID0  # S2TS, SMS, NUMSIDB, NUMSMRG
    scr0: int = 1 << 10
    bank_index: int = CB
    bank: tuple = REVIEWED_BANK


def dt_route(tmp):
    dt = tmp / "machine.dtb"
    subprocess.run([*MACHINE_ARGS, "-machine", f"dumpdtb={dt}"], check=True, capture_output=True)

    def cells(node, key):
        out = subprocess.check_output(["fdtget", "-tx", dt, node, key], text=True)
        return [int(word, 16) for word in out.split()]

    pci = "/pcie@10000000"
    iommu = "/smmuv3@9050000"
    check(cells(pci, "reg")[:2] == [0, PCI_ECAM], "unexpected PCI ECAM layout")
    pci_first, provider, sid_first, length = cells(pci, "iommu-map")
    check(cells(iommu, "reg")[:2] == [0, SMMU] and [provider] == cells(iommu, "phandle"),
          "unexpected PCI requester route")
    properties = subprocess.check_output(["fdtget", "-p", dt, pci], text=True).splitlines()
    mask = cells(pci, "iommu-map-mask")[0] if "iommu-map-mask" in properties else 0xffffffff
    requester = RID & mask
    check(pci_first <= requester < pci_first + length, "unrouted virtual requester")
    return sid_first + requester - pci_first


def selected_route(snap, sid):
    if sid is None or not 0 <= sid <= SID_MASK:
        raise Refused("UFS stream identity unavailable")
    if snap.id0 != PROFILE_ID0 or snap.scr0 not in (0, 1 << 10):
        raise Refused("unsupported stream mode")
    if len(snap.pairs) != (snap.id0 & 0xff):
        raise Refused("incomplete stream snapshot")
    matches = []
    for slot, (smr, s2cr) in enumerate(snap.pairs):
        if smr & VALID:
            if smr & ~(VALID | (SID_MASK << 16) | SID_MASK):
                raise Refused("unrepresentable stream match")
            mask = (smr >> 16) & SID_MASK
            if ((sid ^ smr) & SID_MASK & ~mask) == 0:
                matches.append((slot, s2cr))
    if not matches:
        raise Refused("unmatched stream faults" if snap.scr0 & (1 << 10) else "unmatched default unresolved")
    if len(matches) != 1:
        raise Refused("overlapping matches")
    slot, s2cr = matches[0]
    if s2cr == BYPASS:
        return slot, "bypass", None
    if (s2cr >> 16) & 3 == 2:
        raise Refused("stream fault")
    if s2cr != snap.bank_index:
        raise Refused("unsupported or missing context")
    # Restrict to the exact v2 test profile. A translate SMR/S2CR alone has
    # no information about the address at either end of the page.
    if snap.bank[:4] != REVIEWED_BANK[:4]:
        raise Refused("unverified context geometry")
    return slot, "S2", snap.bank[4]


def authorize(bus, snap, sid):
    slot, mode, root = selected_route(snap, sid)
    if mode == "S2":
        iova, _, backend_root, _ = discover(bus, sid, OWNED_PAGE)
        if root != backend_root:
            raise Refused("context root disagrees with backend")
        return slot, mode, iova
    # In this virt fixture PCI goes directly into this one SMMUv3. A bypass
    # match in a Go capture would still require evidence about the other hops.
    check(bus.read32(SMMU + 0x20) == bus.read32(SMMU + 0x24) == 1, "backend SMMU disabled")
    stream = int(bus.command(f"readq {SMMU + 0x80:#x}")[0], 16)
    if (stream != STREAM_START or bus.read32(SMMU + 0x88) != 5 or
            bus.read(stream + 64 * sid, 64) != struct.pack("<Q", 9) + bytes(56)):
        raise Refused("bypass disagrees with backend")
    return slot, mode, OWNED_PAGE


def transfer(bus, iova):
    seed_lk(bus)
    control = TM + 640 + 256
    first = capacity(bus, control)
    check(first[7] == 2 and first[36] & 15 == 6, "expected unit attention")
    check(capacity(bus, control)[7] == 0 and bus.read(control, 8) == CAPACITY, "bad control")
    guard = bytearray(bytes([0xa5]) * PAGE * 4)
    bus.write(WINDOW, guard)
    if iova != OWNED_PAGE:
        bus.write(iova, bytes([0x66]) * PAGE)
    endpoints = []
    for offset in (0, PAGE - 8):
        check(bus.read(OWNED_PAGE + offset, 8) != CAPACITY, "stale capacity")
        response = capacity(bus, iova + offset)
        check(response[2] == 4 and response[6:8] == bytes(2) and response[12:16] == bytes(4), "bad response")
        guard[PAGE + offset: PAGE + offset + 8] = CAPACITY
        payload = bus.read(OWNED_PAGE + offset, 8)
        check(payload == CAPACITY and bus.read(WINDOW, len(guard)) == guard, "wrong destination or guards")
        endpoints.append({"cpu": hex(OWNED_PAGE + offset), "bus": hex(iova + offset), "data": payload.hex()})
    if iova != OWNED_PAGE:
        check(bus.read(iova, PAGE) == bytes([0x66]) * PAGE, "numeric alias changed")
    return endpoints


def run(tmp, case, snap, sid_input, backend, expected):
    with controller(tmp, PCI_ECAM, BAR, machine=MACHINE_ARGS, units=unit_args(LUN_BYTES)) as bus:
        check(bus.read32(PCI_ECAM + RID * PAGE + 8) >> 8 == 0x010901, "wrong PCI requester")
        pa = OWNED_PAGE + PAGE if backend == "other-page" else OWNED_PAGE
        set_translation(bus, [(IOVA, pa)])
        if backend == "bypass":
            # Set the virtual STE while stopped and before the first DMA.
            bus.write32(SMMU + 0x20, 0)
            bus.wait_bits(SMMU + 0x24, 1, 0)
            bus.write(STREAM_START + 64 * RID, struct.pack("<Q", 9) + bytes(56))
            bus.write32(SMMU + 0x20, 1)
            bus.wait_bits(SMMU + 0x24, 1, 1)
        row = {"case": case, "testedSid": sid_input, "backend": backend}
        try:
            slot, route, iova = authorize(bus, snap, sid_input)
        except Refused as why:
            check(str(why) == expected, f"{case}: {why} vs {expected}")
            row.update(refused=str(why), capacityCommands=0)
        else:
            check(route == expected, f"{case}: unexpected authorization")
            check(iova == (OWNED_PAGE if route == "bypass" else IOVA), "wrong independent lookup")
            row.update(slot=slot, route=route, endpoints=transfer(bus, iova), capacityCommands=4)
    events = (tmp / "ufs.trace").read_text().splitlines()
    accepted = row["capacityCommands"] != 0
    check(events == (["ufs_exec_nop_cmd UTRLDBR slot 0"] +
                     ["ufs_exec_scsi_cmd slot 1, lun 0x4, opcode 0x25"] * 4 if accepted else []),
          f"{case}: unexpected I/O {events}")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as dirname:
        folder = Path(dirname)
        sid = dt_route(folder)
        check(sid == RID, "fixture mapping changed")
        # Group 0 belongs to another master. Group 1 is invalid even though
        # its ID matches. Group 3 matches IDs 0 and 8 by ignoring bit 3.
        prefix = ((VALID | 16, BYPASS), (sid, FAULT), (0, 0))
        def sample(pair):
            return Snapshot(prefix + (pair,))

        match = VALID | (8 << 16)  # ID=0, MASK=8; the requester SID is 8
        trans = sample((match, CB))
        bypass = sample((match, BYPASS))
        absent = sample((VALID | (sid + 2), BYPASS))
        cases = [
            ("masked-s2", trans, sid, "stage2", "S2"),
            ("masked-bypass", bypass, sid, "bypass", "bypass"),
            ("missing-identity", bypass, None, "bypass", "UFS stream identity unavailable"),
            ("unsupported-numsidb", replace(trans, id0=PROFILE_ID0 ^ (1 << 9)), sid, "stage2", "unsupported stream mode"),
            ("foreign-id-bit", sample((match | 0x100, CB)), sid, "stage2", "unrepresentable stream match"),
            ("no-match-fault", absent, sid, "stage2", "unmatched stream faults"),
            ("no-match-default", replace(absent, scr0=0), sid, "stage2", "unmatched default unresolved"),
            ("stream-fault", sample((match, FAULT)), sid, "stage2", "stream fault"),
            ("overlap", replace(trans, pairs=((VALID | sid, BYPASS),) + trans.pairs[1:]), sid, "stage2", "overlapping matches"),
            ("truncated", replace(trans, pairs=trans.pairs[:3]), sid, "stage2", "incomplete stream snapshot"),
            ("clientpd", replace(trans, scr0=1), sid, "stage2", "unsupported stream mode"),
            ("missing-context", sample((match, CB + 1)), sid, "stage2", "unsupported or missing context"),
            ("different-stage", replace(trans, bank=((1 << 16) | 1,) + trans.bank[1:]), sid, "stage2", "unverified context geometry"),
            ("wrong-root", replace(trans, bank=trans.bank[:4] + (TABLE_START + PAGE,)), sid, "stage2", "context root disagrees with backend"),
            ("bypass-on-translated-backend", bypass, sid, "stage2", "bypass disagrees with backend"),
            ("wrong-page", trans, sid, "other-page", "page absent"),
        ]
        rows = []
        for case in cases:
            tmp = folder / case[0]
            tmp.mkdir()
            rows.append(run(tmp, *case))
    report = {"outcome": "PASS-QEMU-V2-ROUTE", "qemu": subprocess.check_output([MACHINE[0], "--version"],
              text=True).splitlines()[0], "v2": "synthetic host snapshot, classic stream matching, AArch64 S2 test profile",
              "backend": "QEMU PCI UFS and SMMUv3 with read-only null-co LUN 4", "cpuPage": hex(OWNED_PAGE),
              "virtualSidFromPciAndDtb": sid, "pacificUfsSid": "UNKNOWN", "pacificBus": "UNKNOWN",
              "mediaReads": 0, "mediaWrites": 0, "cases": rows}
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(report["outcome"], len(rows), "cases")


if __name__ == "__main__":
    main()
