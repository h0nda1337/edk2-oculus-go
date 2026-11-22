"""QEMU-only UFS DMA read witness. Run: python3 -B tests/ufs_outbound_witness_qemu.py

SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import hashlib
import json
from pathlib import Path
import socket
import struct
import tempfile

from ufs_data_qemu import CAPACITY, LUN_BYTES, unit_args
from ufs_lk_nop_qemu import BAR, MACHINE, TM, TR, check, controller
from ufs_nop11_bus import IOVA, PAGE, WINDOW, seed_lk, set_translation
from ufs_owned_bus_qemu import capacity


UCD = TM + 640
CONTROL = UCD + 256
CPU = WINDOW + PAGE
ALIAS = CPU + PAGE
MODE_PAGE = ALIAS + PAGE
MODE_BUS = IOVA + 2 * PAGE
GOOD = "GOOD"
BAD_LENGTH = "05/1a/00"


def mode_command(bus, address, *, sense=False):
    # The CDB, direction, transfer length, LUN and response destination are
    # fixed by the test. Candidate bytes can only supply the eight-byte header.
    if sense:
        cdb = bytes.fromhex("5a003f00000000010000")  # all current mode pages
        direction, flags, size = 0x05000000, 0x40, 256
    else:
        cdb = bytes.fromhex("55100000000000000800")  # PF=1, SP=0
        direction, flags, size = 0x03000000, 0x20, 8
    upiu = bytes([1, flags, 4, 1]) + bytes(8) + size.to_bytes(4, "big") + cdb.ljust(16, b"\0")
    bus.write(UCD, upiu)
    bus.write(UCD + 128, bytes([0xa5]) * 64)
    bus.write(UCD + 208, struct.pack("<4I", address, 0, 0, size - 1))
    bus.write(TR + 32, struct.pack("<8I", direction, 0, 15, 0, UCD, 0, (32 << 16) | 16, (52 << 16) | 1))
    bus.write32(BAR + 0x58, 2)
    bus.wait_bits(BAR + 0x58, 2, 0)
    response = bus.read(UCD + 128, 64)
    check(bus.read32(TR + 40) == 0 and response[0] == 0x21 and response[3] == 1, "invalid UFS completion")
    return response


def current_mode_pages(bus):
    bus.write(MODE_PAGE, bytes([0xa5]) * 256)
    response = mode_command(bus, MODE_BUS, sense=True)
    check(response[6:8] == bytes(2), "MODE SENSE failed")
    data = bus.read(MODE_PAGE, 256)
    length = int.from_bytes(data[:2], "big") + 2
    check(8 < length <= 256, "incomplete mode parameter data")
    return data[:length]


def signature(bus, cpu, source):
    statuses = []
    for header in (bytes(8), bytes(7) + b"\x08", bytes(8)):
        bus.write(cpu, header)
        guards = bus.read(WINDOW, 4 * PAGE)
        response = mode_command(bus, source)
        check(bus.read(WINDOW, 4 * PAGE) == guards, "outbound transfer wrote the guarded window")
        check(bus.read(cpu, 8) == header, "outbound transfer changed the CPU header")
        check(response[1] == 0 and response[12:16] == bytes(4), "residual or overflow")
        if response[6:8] == bytes(2):
            statuses.append(GOOD)
        else:
            check(response[6:8] == bytes([1, 2]) and int.from_bytes(response[32:34], "big") >= 14
                  and response[34] & 0x7f in (0x70, 0x71), "unexpected SCSI result or sense format")
            statuses.append(f"{response[36] & 15:02x}/{response[46]:02x}/{response[47]:02x}")
    return statuses


def backend_status(path):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(5)
        sock.connect(str(path))
        with sock.makefile("rwb", buffering=0) as wire:
            version = json.loads(wire.readline())["QMP"]["version"]
            def query(command):
                wire.write(json.dumps({"execute": command}).encode() + b"\n")
                while True:
                    reply = json.loads(wire.readline())
                    if "event" not in reply:
                        return reply["return"]
            query("qmp_capabilities")
            (disk,) = query("query-block")
            (counter,) = query("query-blockstats")
    node = disk["inserted"]
    check(node["drv"] == "null-co" and node["ro"] and node["backing_file_depth"] == 0
          and node["image"]["virtual-size"] == LUN_BYTES, "unexpected block backend")
    check(node["node-name"] == counter["node-name"] == "capacity" and disk["qdev"] == counter["qdev"]
          and disk["qdev"].endswith("/ufs-scsi"), "stats are for a different device")
    stats = counter["stats"]
    check(all(value == 0 for name, value in stats.items() if name.endswith(("_bytes", "_operations"))),
          f"backend performed I/O: {stats}")
    return {"qemu": version, "backend": node["drv"], "readOnly": node["ro"],
            "operations": {name: stats[name] for name in ("rd_operations", "wr_operations", "flush_operations")}}


def trial(tmp):
    machine = [part.replace("1280M", "1536M").replace("virt,highmem=off", "virt,highmem=off,iommu=smmuv3")
               for part in MACHINE]
    qmp = tmp / "qmp"
    extra = ["-qmp", f"unix:{qmp},server=on,wait=off"]
    with controller(tmp, 0x3f000000, BAR, machine=machine, extra=extra, units=unit_args(LUN_BYTES)) as bus:
        set_translation(bus, [(IOVA, CPU), (IOVA + PAGE, ALIAS), (MODE_BUS, MODE_PAGE)])
        seed_lk(bus)
        check(capacity(bus, CONTROL)[7] == 2, "missing initial unit attention")
        check(capacity(bus, CONTROL)[7] == 0 and bus.read(CONTROL, 8) == CAPACITY, "baseline geometry")
        before = current_mode_pages(bus)
        rows = {}
        # With any eight bytes, the QEMU parser either sees no descriptors or
        # rejects the list before applying any. No mode page fits after the header.
        for label, cpu, dma, expected in (
            ("control", CONTROL, CONTROL, [GOOD, BAD_LENGTH, GOOD]),
            ("head", CPU, IOVA, [GOOD, BAD_LENGTH, GOOD]),
            ("tail", CPU + PAGE - 8, IOVA + PAGE - 8, [GOOD, BAD_LENGTH, GOOD]),
            ("aliasZero", CPU, IOVA + PAGE, [GOOD] * 3),
            ("aliasForeign", CPU, IOVA + PAGE, [BAD_LENGTH] * 3),
        ):
            if label.startswith("alias"):
                bus.write(ALIAS, bytes(8) if label == "aliasZero" else bytes.fromhex("55aac37e9173ffff"))
            rows[label] = signature(bus, cpu, dma)
            check(rows[label] == expected, f"{label}: {rows[label]}")
        after = current_mode_pages(bus)
        check(before == after, "current mode parameters changed")
        check(capacity(bus, CONTROL)[7] == 0 and bus.read(CONTROL, 8) == CAPACITY, "final geometry")
        result = backend_status(qmp)
    prefix = "ufs_exec_scsi_cmd slot 1, lun 0x4, opcode "
    commands = [0x25, 0x25, 0x5a] + [0x55] * 15 + [0x5a, 0x25]
    check((tmp / "ufs.trace").read_text().splitlines() ==
          ["ufs_exec_nop_cmd UTRLDBR slot 0"] + [f"{prefix}{code:#x}" for code in commands], "unexpected UFS trace")
    return {**result, "result": "PASS-QEMU-OUTBOUND", "lun": 4, "cpu": hex(CPU), "virtualBus": hex(IOVA),
            "signatures": rows, "modeBytes": len(before), "modeSha256": hashlib.sha256(before).hexdigest(),
            "physicalBus": "UNKNOWN"}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        print(json.dumps(trial(Path(directory)), separators=(",", ":")))
