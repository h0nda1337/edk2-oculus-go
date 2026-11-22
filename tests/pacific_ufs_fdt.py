"""Replay Pacific board identification and its handoff check with host-only inputs."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import argparse
import ctypes as ct
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EVT = "70ae171c99befc564acec661f3afc4365a831ebd1d6e01ca0e53035a4d8b1f35"
UFS = "/soc/ufshc@624000"


class Resource(ct.Structure):
    _fields_ = [("base", ct.c_uint64), ("length", ct.c_uint32), ("coherent", ct.c_uint32)]


def run(stock, output):
    original = stock.read_bytes()
    if hashlib.sha256(original).hexdigest() != EVT:
        raise ValueError("Expected the preserved Pacific EVT tree")
    cases = {}
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        module = work / "test.so"
        fdtlib = ROOT / "edk2/EmbeddedPkg/Library/FdtLib"
        includes = ["edk2/MdePkg/Include", "edk2/MdePkg/Include/X64", "edk2/EmbeddedPkg/Include",
                    "edk2/MdeModulePkg/Include", "OculusGoPkg/Include"]
        subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-fshort-wchar", "-fno-builtin",
                        "-DMDEPKG_NDEBUG", "-include", "Uefi.h", "-ffunction-sections", "-fdata-sections", "-fvisibility=hidden",
                        "-Wl,--gc-sections,-z,defs", *["-I" + str(ROOT / inc) for inc in includes],
                        ROOT / "OculusGoPkg/PrePi/PacificUfsFdt.c", ROOT / "tests/pacific_ufs_board_host.c",
                        ROOT / "OculusGoPkg/Library/GoUfsHandoffLib/UfsHandoff.c",
                        *[fdtlib / f for f in ["fdt.c", "fdt_ro.c", "fdt_addresses.c"]],
                        "-o", module], check=True)
        guest = ct.CDLL(str(module))
        guest.HostParse.argtypes = [ct.c_void_p, ct.c_size_t, ct.POINTER(Resource)]
        guest.HostParse.restype = ct.c_uint8
        register_array = ct.c_uint32 * 10
        guest.HostPrepare.argtypes = [ct.c_size_t, ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_uint32),
                                      ct.POINTER(ct.c_size_t)]
        guest.HostPrepare.restype = ct.c_uint64

        def parse(name, data, expected, coherent=0):
            res = Resource()
            buf = None if data is None else ct.create_string_buffer(data)
            ok = bool(guest.HostParse(buf, len(data or b""), ct.byref(res)))
            if ok != expected or (ok and (res.base, res.length, res.coherent) !=
                                  (0x624000, 0x2500, coherent)):
                raise AssertionError(name)
            cases[name] = {"resource": ok, "coherent": bool(res.coherent) if ok else None}

        parse("evt", original, True)
        parse("null", None, False)
        parse("truncated", original[:39], False)
        parse("short-totalsize", original[:-32], False)
        damaged = bytearray(original)
        struct.pack_into(">I", damaged, 12, 0xfffffff0)
        parse("strings-outside", bytes(damaged), False)
        badname = bytearray(original)
        structure = struct.unpack_from(">I", badname, 8)[0]
        assert struct.unpack_from(">I", badname, structure + 8)[0] == 3
        struct.pack_into(">I", badname, structure + 16, 0xfffffff0)
        parse("name-outside", bytes(badname), False)
        variants = [
            ("controller-disabled", False, 0, ["-t", "s", UFS, "status", "disabled"]),
            ("parent-disabled", False, 0, ["-t", "s", "/soc", "status", "disabled"]),
            ("okay", True, 0, ["-t", "s", UFS, "status", "okay"]),
            ("different-model", False, 0, ["-t", "s", "/", "model", "Other board"]),
            ("wrong-base", False, 0, ["-t", "x", UFS, "reg", "624100", "2500"]),
            ("wrong-length", False, 0, ["-t", "x", UFS, "reg", "624000", "3000"]),
            ("different-compatible", False, 0, ["-t", "s", UFS, "compatible", "example,controller"]),
            ("different-bus", False, 0, ["-t", "x", "/soc", "ranges", "0", "0", "40000", "ffffffff"]),
            ("inherited-coherence", True, 1, ["/soc", "dma-coherent"]),
            ("no-controller", False, 0, ["-r", UFS]),
        ]
        fixture = work / "board.dtb"
        for name, enabled, coherent, variant in variants:
            fixture.write_bytes(original)
            index = next(i for i, token in enumerate(variant) if token.startswith("/"))
            subprocess.run(["fdtput", *variant[:index], fixture, *variant[index:]], check=True)
            parse(name, fixture.read_bytes(), enabled, coherent)
        fixture.write_bytes(original)
        subprocess.run(["fdtput", fixture, "/soc", "dma-coherent"], check=True)
        subprocess.run(["fdtput", fixture, UFS, "dma-noncoherent"], check=True)
        parse("child-overrides-parent", fixture.read_bytes(), True, 0)
        subprocess.run(["fdtput", fixture, UFS, "dma-coherent"], check=True)
        parse("conflicting-coherence", fixture.read_bytes(), False)
        high = 1 << 63
        guest.HostRegister.argtypes = [ct.c_uint8, ct.c_int32, ct.POINTER(Resource),
                                      ct.POINTER(ct.c_size_t)]
        guest.HostRegister.restype = ct.c_uint64
        accepted = (0x624000, 0x2500, 0)
        for name, present, adjust, resource, expected, count in [
            ("missing-hob", False, 0, accepted, high | 14, 0),
            ("short-hob", True, -8, accepted, high | 33, 0),
            ("long-hob", True, 8, accepted, high | 33, 0),
            ("wrong-hob-base", True, 0, (0x627000, *accepted[1:]), high | 33, 0),
            ("wrong-hob-length", True, 0, (accepted[0], 0x3000, 0), high | 33, 0),
            ("wrong-hob-coherence", True, 0, (*accepted[:2], 2), high | 33, 0),
            ("register-noncoherent", True, 0, accepted, 0, 1),
            ("register-coherent", True, 0, (*accepted[:2], 1), 0, 1),
        ]:
            actual = ct.c_size_t()
            result = guest.HostRegister(present, adjust, ct.byref(Resource(*resource)), ct.byref(actual))
            if (result, actual.value) != (expected, count):
                raise AssertionError((name, result, actual.value))
            cases[name] = {"status": hex(result), "registrations": actual.value}
        source = "docs/evidence/ufs-handoff-transfer-20261121.json"
        panel = json.loads((ROOT / source).read_text())["physicalPanel"]["registersHex"]
        fields = ("VER", "HCE", "TRR", "TMR", "TRD", "TMD")
        # The four base words model aligned, private test queues. Only the first
        # six registers are replayed from the physical panel.
        active = [int(panel[field], 16) for field in fields] + [0x10000, 0, 0x14000, 0]
        assert active[:6] == [0x10100, 1, 1, 1, 0, 0]
        stopped = [*active[:2], 0, 0, *active[4:]]

        def change(registers, field, value):
            variant = registers.copy()
            variant[field] = value
            return variant

        denied = high | 6
        for name, release, first, second, expected, reads in [
            ("missing-handoff", 0, active, active, denied, 0),
            ("declined-handoff", 1, active, active, denied, 0),
            ("warning-handoff", 3, active, active, denied, 0),
            ("unsupported-HCI", 2, change(active, 0, 0x20000), active, high | 3, 1),
            ("unexpected-HCE", 2, change(active, 1, 0xffffffff), active, denied, 2),
            ("disabled-running", 2, change(active, 1, 0), active, denied, 3),
            ("invalid-run-bit", 2, change(active, 2, 3), active, denied, 3),
            ("only-transfer-running", 2, change(active, 3, 0), active, denied, 4),
            ("only-task-running", 2, change(active, 2, 0), active, denied, 4),
            ("transfer-pending", 2, change(active, 4, 1), active, denied, 5),
            ("task-pending", 2, change(active, 5, 1), active, denied, 6),
            ("stopped-transfer-pending", 2, change(stopped, 4, 1), stopped, denied, 5),
            ("unaligned-transfer-base", 2, change(active, 6, 0x10100), active, denied, 10),
            ("unaligned-task-base", 2, change(active, 8, 0x14100), active, denied, 10),
            ("missing-transfer-base", 2, change(active, 6, 0), active, denied, 10),
            ("missing-task-base", 2, change(active, 8, 0), active, denied, 10),
            ("aliased-list-bases", 2, change(active, 8, active[6]), active, denied, 10),
            ("transfer-arrived", 2, active, change(active, 4, 1), denied, 14),
            ("task-arrived", 2, active, change(active, 5, 1), denied, 15),
            ("pair-stopped-during-sampling", 2, active, stopped, denied, 15),
            ("pair-started-during-sampling", 2, stopped, active, denied, 15),
            ("HCE-changed", 2, stopped, change(stopped, 1, 0), denied, 11),
            ("transfer-base-changed", 2, active, change(active, 6, 0x18000), denied, 19),
            ("transfer-base-upper-changed", 2, active, change(active, 7, 1), denied, 19),
            ("task-base-changed", 2, active, change(active, 8, 0x18000), denied, 19),
            ("task-base-upper-changed", 2, active, change(active, 9, 1), denied, 19),
            ("released-disabled", 2, change(stopped, 1, 0), change(stopped, 1, 0), 0, 11),
            ("released-stopped", 2, stopped, stopped, 0, 11),
            ("released-LK-running-idle", 2, active, active, 0, 19),
        ]:
            actual = ct.c_size_t()
            result = guest.HostPrepare(release, register_array(*first), register_array(*second), ct.byref(actual))
            if (result, actual.value) != (expected, reads):
                raise AssertionError((name, result, actual.value))
            cases[name] = {"status": hex(result), "mockRegisterReads": actual.value}
    report = {"result": "PASS", "scope": "Host replay with pinned libfdt, preserved EVT and mock MMIO",
              "physicalStateSource": source, "replayedFields": fields,
              "releaseAndQueueBaseSource": "Host fixture", "stockDtbSha256": EVT, "cases": cases}
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    run(args.stock, args.report)
