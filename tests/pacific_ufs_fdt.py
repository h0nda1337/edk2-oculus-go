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
                        *[fdtlib / f for f in ["fdt.c", "fdt_ro.c", "fdt_addresses.c"]],
                        "-o", module], check=True)
        guest = ct.CDLL(str(module))
        guest.HostParse.argtypes = [ct.c_void_p, ct.c_size_t, ct.POINTER(Resource)]
        guest.HostParse.restype = ct.c_uint8
        guest.HostPrepare.argtypes = [ct.c_size_t, ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_size_t)]
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
        idle = [0x00010100, 1, 0, 0, 0, 0]
        for name, release, registers, expected, reads in [
            ("missing-handoff", 0, idle, high | 6, 0), ("declined-handoff", 1, idle, high | 6, 0),
            ("unsupported-HCI", 2, [0x20000, *idle[1:]], high | 3, 1),
            ("unexpected-HCE", 2, [idle[0], 0xffffffff, *idle[2:]], high | 6, 2),
            ("LK-lists-running", 2, [*idle[:2], 1, 1, 0, 0], high | 6, 3),
            ("task-list-running", 2, [*idle[:3], 1, 0, 0], high | 6, 4),
            ("transfer-pending", 2, [*idle[:4], 1, 0], high | 6, 5),
            ("task-pending", 2, [*idle[:5], 1], high | 6, 6),
            ("released-idle", 2, idle, 0, 6),
        ]:
            actual = ct.c_size_t()
            result = guest.HostPrepare(release, (ct.c_uint32 * 6)(*registers), ct.byref(actual))
            if (result, actual.value) != (expected, reads):
                raise AssertionError((name, result, actual.value))
            cases[name] = {"status": hex(result), "mockRegisterReads": actual.value}
    report = {"result": "PASS", "scope": "Host replay with pinned libfdt, preserved EVT and mock MMIO",
              "stockDtbSha256": EVT, "cases": cases}
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    run(args.stock, args.report)
