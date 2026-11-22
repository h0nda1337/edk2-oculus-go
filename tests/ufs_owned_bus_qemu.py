"""Observe both DMA endpoints under a nonidentity SMMUv3 mapping in QEMU.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
from pathlib import Path
import struct
import tempfile

from ufs_data_qemu import CAPACITY, LUN_BYTES, unit_args
from ufs_lk_nop_qemu import BAR, MACHINE, TM, TR, check, controller
from ufs_nop11_bus import IOVA, PAGE, WINDOW, seed_lk, set_translation


def capacity(bus, destination):
    ucd = TM + 640
    bus.write(ucd, struct.pack("<8I", 0x01044001, 0, 0, 0x08000000, 0x25, 0, 0, 0))
    bus.write(ucd+128, bytes([0xa5])*64)
    bus.write(ucd+208, struct.pack("<4I", destination, 0, 0, 7))
    bus.write(TR+32, struct.pack("<8I", 0x05000000, 0, 15, 0, ucd, 0, (32<<16)|16, (52<<16)|1))
    bus.write32(BAR+0x58, 2)
    bus.wait_bits(BAR+0x58, 2, 0)
    response = bus.read(ucd+128, 64)
    check(bus.read32(TR+40) == 0 and response[0] == 0x21 and response[3] == 1, "bad UFS response")
    return response


def exercise_endpoints(bus, iova, misdirect_tail):
    """Issue two control requests and one at each page endpoint. Verify guards after each."""
    cpu = WINDOW + PAGE
    wrong_bus, wrong_cpu = iova + PAGE, cpu + PAGE
    sentinel = bytes([0xa5]) * PAGE
    expected = bytearray(sentinel * 4)
    seed_lk(bus)
    bus.write(WINDOW, expected)
    bus.write(iova, sentinel)
    control = TM+640+256
    before = capacity(bus, control)
    check(before[7] == 2 and (before[36] & 15) == 6, "expected initial unit attention")
    check(capacity(bus, control)[7] == 0 and bus.read(control, 8)==CAPACITY, "control failed")
    rows = []
    for offset in (0, PAGE-8):
        negative = misdirect_tail and offset == PAGE-8
        destination = (wrong_bus if negative else iova) + offset
        check(bus.read(cpu+offset, 8) != CAPACITY, "stale successful response before request")
        response = capacity(bus, destination)
        check(response[2] == 4 and response[6:8] == bytes(2) and response[12:16] == bytes(4),
              "wrong LUN, SCSI error or residual")
        expected[PAGE+offset:PAGE+offset+8] = CAPACITY
        observed = bus.read(WINDOW, len(expected))
        if negative:
            check(observed != expected and bus.read(cpu+offset, 8)==sentinel[:8],
                  "wrong DMA destination accepted as a successful tail")
            expected[PAGE+offset:PAGE+offset+8] = sentinel[:8]
            expected[2*PAGE+offset:2*PAGE+offset+8] = CAPACITY
        check(observed==expected, "unexpected data or guards")
        check(bus.read(iova, PAGE)==sentinel, "numeric alias changed")
        row = dict(cpu=hex(cpu+offset), bus=hex(destination), payload=bus.read(cpu+offset, 8).hex())
        if negative:
            row.update(observedCpu=hex(wrong_cpu+offset), observedPayload=bus.read(wrong_cpu+offset, 8).hex(),
                       scsiStatus=response[7], destinationVerified=False)
        rows.append(row)
    return rows


def trial(tmp, misdirect_tail=False):
    machine = [part.replace("1280M", "1536M").replace("virt,highmem=off", "virt,highmem=off,iommu=smmuv3")
               for part in MACHINE]
    cpu = WINDOW+PAGE
    with controller(tmp, 0x3f000000, BAR, machine=machine, units=unit_args(LUN_BYTES)) as bus:
        wrong_bus, wrong_cpu = IOVA + PAGE, WINDOW + 2*PAGE
        leaves = [(IOVA, cpu)]
        if misdirect_tail:
            leaves.append((wrong_bus, wrong_cpu))
        set_translation(bus, leaves)
        rows = exercise_endpoints(bus, IOVA, misdirect_tail)
    events = (tmp/"ufs.trace").read_text().splitlines()
    check(events == ["ufs_exec_nop_cmd UTRLDBR slot 0"]+["ufs_exec_scsi_cmd slot 1, lun 0x4, opcode 0x25"]*4,
          f"unexpected device trace {events}")
    return dict(outcome="PASS-QEMU-MISDIRECTED-TAIL" if misdirect_tail else "PASS-QEMU-NONIDENTITY-ENDPOINTS",
                provider="QEMU virt PCI UFS + SMMUv3 stage 2",
                rows=rows, guardsIntact=not misdirect_tail, numericAliasIntact=True, capacityCommands=4,
                mediaReads=0, mediaWrites=0, physicalPacificBus="UNKNOWN")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--misdirect-tail", action="store_true", help="send the second DMA to a different mapped page")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        result = trial(Path(directory), args.misdirect_tail)
    args.report.write_text(json.dumps(result, indent=2)+"\n")
    print(result["outcome"], result["rows"])
