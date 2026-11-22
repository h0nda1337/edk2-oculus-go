"""Prove two UFS DMA destinations using stage-1 translation in QEMU virt.
The stream mapping, context and page tables belong entirely to this fixture.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from ufs_data_qemu import LUN_BYTES, unit_args
from ufs_discover_iova_qemu import OWNED_PAGE, SMMU, STREAM_START, TABLE_START
from ufs_lk_nop_qemu import BAR, MACHINE, TR, check, controller
from ufs_nop11_bus import PAGE
from ufs_owned_bus_qemu import exercise_endpoints
from ufs_v2_route_qemu import MACHINE_ARGS, PCI_ECAM, dt_route

IOVA = 0x85120000
CD = STREAM_START + PAGE
TRANSLATE = re.compile(r"^smmuv3_translate_success \S+ sid=(0x[\da-f]+) iova=(0x[\da-f]+) "
                       r"translated=(0x[\da-f]+) perm=(0x[\da-f]+) stage=(\d+)$")


def install_stage1(bus, sid, wrong_tail):
    check(bus.read32(SMMU) & 2, "SMMUv3 stage 1 unavailable")
    check(bus.read32(SMMU + 0x24) == 0, "SMMUv3 already configured")

    # Fixed allocations in fresh QEMU RAM. Both IOVAs use one L1 entry.
    # Index by the whole input address to keep different L2 regions independent.
    queue_page = TR & -PAGE
    mappings = [(queue_page, queue_page), (IOVA, OWNED_PAGE)]
    if wrong_tail:
        mappings.append((IOVA + PAGE, OWNED_PAGE + PAGE))
    tables = {}
    for va, pa in mappings:
        table = TABLE_START
        for shift in (30, 21):
            entry = table + 8 * ((va >> shift) & 511)
            if entry not in tables:
                tables[entry] = TABLE_START + PAGE * (len(tables) + 1)
                bus.write(entry, struct.pack("<Q", tables[entry] | 3))
            table = tables[entry]
        # Page descriptor: valid leaf, AP=01 (RW), inner shareable, AF=1.
        bus.write(table + 8 * ((va >> 12) & 511), struct.pack("<Q", pa | 0x743))

    # Linear STE, stage 1 only. Use CD zero for transactions without a substream.
    bus.write(STREAM_START + sid * 64, struct.pack("<8Q", CD | 11, 2, 0, 0, 0, 0, 0, 0))
    # AArch64, valid, T0SZ=28 (36-bit VA), 4 KiB granule, disable TTBR1;
    # IPS=1 (36-bit output), synchronous abort, TTBR0, MAIR Attr0=normal WB.
    cd_low = 28 | (1 << 30) | (1 << 31)
    cd_high = 1 | (1 << 9) | (1 << 14)
    bus.write(CD, struct.pack("<8Q", cd_low | (cd_high << 32), TABLE_START, 0, 0xff, 0, 0, 0, 0))
    bus.command(f"writeq {SMMU + 0x80:#x} {STREAM_START:#x}")
    bus.write32(SMMU + 0x88, 5)
    bus.write32(SMMU + 0x20, 1)
    bus.wait_bits(SMMU + 0x24, 1, 1)


def case(tmp, sid, wrong_tail):
    extra = ["-trace", "enable=smmuv3_translate_success", "-trace", "enable=smmuv3_decode_cd",
             "-trace", "enable=smmuv3_decode_cd_tt"]
    with controller(tmp, PCI_ECAM, BAR, machine=MACHINE_ARGS, extra=extra, units=unit_args(LUN_BYTES)) as bus:
        install_stage1(bus, sid, wrong_tail)
        rows = exercise_endpoints(bus, IOVA, wrong_tail)

    trace = (tmp / "ufs.trace").read_bytes()
    lines = trace.decode().splitlines()
    commands = [line for line in lines if not line.startswith("smmuv3_")]
    check(commands == ["ufs_exec_nop_cmd UTRLDBR slot 0"] + ["ufs_exec_scsi_cmd slot 1, lun 0x4, opcode 0x25"] * 4,
          f"unexpected trace of UFS or sector commands: {commands}")
    check("smmuv3_decode_cd oas=36" in lines, "wrong output width")
    check(f"smmuv3_decode_cd_tt TT[0]:tsz:28 ttb:0x{TABLE_START:x} granule_sz:12 had:0" in lines,
          "unexpected input geometry")
    translations = set()
    for line in lines:
        if line.startswith("smmuv3_translate_success "):
            match = TRANSLATE.fullmatch(line)
            check(match is not None, f"unrecognised QEMU trace: {line}")
            stream, va, pa, perm, stage = [int(v, 0) for v in match.groups()]
            check(stream == sid and stage == 1, f"wrong SID or translation stage: {line}")
            if perm & 2:
                translations.add((va, pa))
    for row in rows:
        # qtest RAM comparison and SMMU's own translation trace are independent.
        actual = row.get("observedCpu", row["cpu"])
        check((int(row["bus"], 16), int(actual, 16)) in translations, f"missing DMA translation for {row}")
    return {"case": "misdirected-tail" if wrong_tail else "mapped-endpoints", "rows": rows,
            "verifiedTraceSid": sid, "verifiedStage": 1, "cpuGuardWindowComparedBytesAfterEach": 16384,
            "capacityCommands": 4, "mediaReads": 0, "mediaWrites": 0,
            "traceSha256": hashlib.sha256(trace).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        sid = dt_route(tmp)
        results = []
        for name, wrong in [("correct", False), ("neighbor", True)]:
            folder = tmp / name
            folder.mkdir()
            results.append(case(folder, sid, wrong))
    version = subprocess.check_output([MACHINE[0], "--version"], text=True).splitlines()[0]
    report = {
        "outcome": "PASS-QEMU-STAGE1-ENDPOINTS", "qemu": version,
        "backend": "QEMU virt PCI UFS and SMMUv3", "lun": 4, "backendBytes": LUN_BYTES,
        "backendReadOnly": True, "dtDerivedVirtualSid": sid, "fixtureInputBits": 36,
        "fixtureOutputBits": 36, "fixtureGranule": PAGE, "pacificUfsSid": "UNKNOWN",
        "pacificPageBus": "UNKNOWN", "cases": results,
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(report["outcome"])


if __name__ == "__main__":
    main()
