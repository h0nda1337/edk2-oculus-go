"""Boot the normal Go console/BDS on QEMU virt and read the prompt from both eyes.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import hashlib
import json
import lzma
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from android_boot import DTB_SHA
from sec_dxe_static import GUIDED, files, sections, unique
from verify_fd import SHELL_FD_SIZE, verify
from verify_fd import SIZE as FIRMWARE_BYTES

FB = 0x83401000
NATIVE_WIDTH, EYE_WIDTH = 1440, 1280
SIZE = NATIVE_WIDTH * EYE_WIDTH * 2 * 3
# Logical per-eye coordinates, origin at the top left when worn.
# Keep the original layout for replay of the first physical Shell image.
LAYOUTS = {"wide": (56, 15, 10, 25), "centered": (24, 12, 16, 38), "legacy": (80, 25, 16, 38)}
SHELL_GUID = "7c04a583-9e3e-4f1c-ad65-e05268d0b4d1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def embedded_shell(fd, reference):
    verify(fd)
    if len(fd) != SHELL_FD_SIZE:
        raise ValueError("Expected the normal boot image with its loader-owned RAM")
    wrapped = unique(body for kind, _, body in files(fd[0x1000:FIRMWARE_BYTES]) if kind == 11)
    guided = unique(s for kind, s in sections(wrapped) if kind == 2)
    offset, flags = struct.unpack_from("<HH", guided, 20)
    if guided[4:20] != GUIDED.bytes_le or flags != 1 or not 24 <= offset < len(guided):
        raise ValueError("Unexpected guided FV section")
    unpacker = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    payload = unpacker.decompress(guided[offset:], max_length=FIRMWARE_BYTES)
    if not unpacker.eof or unpacker.unused_data:
        raise ValueError("Incomplete or oversized inner FV")
    volume = unique(s[4:] for kind, s in sections(payload) if kind == 0x17)
    entries = list(files(volume))
    modules = {}
    for kind, guid, body in entries:
        if kind == 0xF0 or (kind == 2 and str(guid) == "fc510ee7-ffdc-11d4-bd41-0080c73c8881"):
            continue
        if kind not in (5, 7, 9):
            raise ValueError("Unexpected executable file type in FV")
        ui = unique(sec[4:] for tag, sec in sections(body) if tag == 0x15)
        name = ui.decode("utf-16le").rstrip(chr(0))
        if name in modules:
            raise ValueError("Duplicate module in FV")
        modules[name] = str(guid)
    body = unique(b for kind, guid, b in entries if kind == 9 and guid == UUID(SHELL_GUID))
    pe = unique(s[4:] for kind, s in sections(body) if kind == 0x10)
    if pe != reference.read_bytes():
        raise ValueError("Shell in packaged FV differs from compiler output")
    (coff,) = struct.unpack_from("<I", pe, 0x3C)
    if (
        pe[coff : coff + 4] != b"PE\0\0"
        or struct.unpack_from("<H", pe, coff + 4)[0] != 0xAA64
        or struct.unpack_from("<H", pe, coff + 24)[0] != 0x20B
        or struct.unpack_from("<H", pe, coff + 24 + 68)[0] != 10
    ):
        raise ValueError("Shell is not an AArch64 EFI application")
    return {
        "shellPeSha256": sha(pe),
        "shellPeBytes": len(pe),
        "innerFvSha256": sha(volume),
        "modules": modules,
    }


def inspect_pacific(fd, reference):
    data = fd.read_bytes()
    report = embedded_shell(data, reference)
    # The complete executable roster matters for this RAM-only device trial.
    expected = {
        "DxeCore",
        "PcdDxe",
        "TrustMeBroDxe",
        "DevicePathDxe",
        "InheritedGopDxe",
        "HiiDatabase",
        "EnglishDxe",
        "VariableRuntimeDxe",
        "CapsuleRuntimeDxe",
        "WatchdogTimer",
        "RealTimeClock",
        "ConSplitterDxe",
        "GoBdsDxe",
        "Shell",
        "ArmGicDxe",
        "ArmCpuDxe",
        "ArmTimerDxe",
        "MetronomeDxe",
        "EmbeddedMonotonicCounter",
        "RuntimeDxe",
        "ResetSystemRuntimeDxe",
        "SecurityStubDxe",
    }
    if set(report["modules"]) != expected:
        raise ValueError("Unexpected modules in Pacific FV")
    return {
        **report,
        "fdSha256": sha(data),
        "shellFileGuid": SHELL_GUID,
        "flashBackedStorageDrivers": [],
    }


def decode_grid(scan, columns, height, cell_w, cell_h):
    """Decode visible 8x19 ASCII glyphs from native clockwise panel coordinates."""
    header = (ROOT / "OculusGoPkg/Include/third-party/edk2/ConsoleFont.h").read_text()
    font = {
        bytes.fromhex(" ".join(re.findall(r"0x([0-9a-f]{2})", bits))): chr(int(code, 16))
        for bits, code in re.findall(r"\{ ([^{}]+) \},  // U\+([0-9A-Fa-f]{4})", header)
    }
    assert len(font) >= 95
    left, right = scan[: SIZE // 2], scan[SIZE // 2 :]
    if left != right:
        raise ValueError("Frame is changing or left/right eye pixels differ")
    rows = []
    left_margin = (EYE_WIDTH - columns * cell_w) // 2
    top_margin = (NATIVE_WIDTH - height * cell_h) // 2
    for row in range(height):
        top_x = NATIVE_WIDTH - 1 - top_margin - row * cell_h
        chars = []
        for col in range(columns):
            base = 3 * ((left_margin + col * cell_w) * NATIVE_WIDTH + top_x)
            bits = bytearray()
            for v in range(19):
                raster_y = (2*v + 1)*cell_h // (2*19)
                pos = base - 3*raster_y
                value = 0
                for u in range(8):
                    raster_x = (2*u + 1)*cell_w // (2*8)
                    dot = pos + 3*raster_x*NATIVE_WIDTH
                    value = (value << 1) | (left[dot : dot + 3] != b"\x00\x00\x00")
                bits.append(value)
            chars.append(font.get(bytes(bits), "\ufffd"))
        rows.append("".join(chars).rstrip())
    return rows


def eye_png(frame):
    # Exactly one pixel per glyph sample, preserving the real BGR colors.
    w, h = EYE_WIDTH // 2, NATIVE_WIDTH // 2
    pixels = bytearray()
    for y in range(h):
        pixels.append(0)
        x_native = NATIVE_WIDTH - 1 - 2 * y
        for x in range(w):
            pos = 3 * (2 * x * NATIVE_WIDTH + x_native)
            pixels.extend(frame[pos : pos + 3][::-1])

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(pixels, 9))
        + chunk(b"IEND", b"")
    )


def request(wire, command, args=None):
    msg = {"execute": command}
    if args is not None:
        msg["arguments"] = args
    wire.write(json.dumps(msg).encode() + b"\n")
    while True:
        reply = json.loads(wire.readline())
        if "error" in reply:
            raise RuntimeError(reply["error"])
        if "return" in reply:
            return reply["return"]


def wait_for_prompt(wire, log, surface, deadline, trace_loader, layout, welcome=None):
    previous = None
    serial = ""
    while time.monotonic() < deadline:
        time.sleep(0.09 if welcome else 0.35)
        serial = log.read_text(errors="replace")
        fault = re.search(r"ASSERT \[|Go BDS: Shell returned|Exception at", serial)
        if fault:
            raise RuntimeError("Boot stopped: " + serial[fault.start() : fault.start() + 400])
        if welcome is None and trace_loader and not re.search(r"Loading driver at .* Shell\.efi", serial):
            continue
        request(wire, "pmemsave", {"val": FB, "size": SIZE, "filename": str(surface)})
        frame = surface.read_bytes()
        if len(frame) != SIZE:
            raise RuntimeError("Incomplete scanout")
        if welcome:
            welcome.observe(frame)
        if frame[: SIZE // 2] != frame[SIZE // 2 :]:
            previous = None
            continue
        rows = decode_grid(frame, *LAYOUTS[layout])
        if (
            "Shell>" in rows
            and any(row.startswith("UEFI Basic Shell v") for row in rows)
            and "OculusGoUEFI,0x00000002" in "".join("".join(rows).split())
        ):
            if previous == frame:
                return frame, rows, serial
            previous = frame
        else:
            previous = None
    regs = request(wire, "human-monitor-command", {"command-line": "info registers"})
    raise TimeoutError("Prompt not observed. " + regs[:330] + " " + serial[-1700:])


def verify_viewport(frame, rows, layout):
    columns, height, cell_w, cell_h = LAYOUTS[layout]
    left = (EYE_WIDTH - columns * cell_w) // 2
    top = (NATIVE_WIDTH - height * cell_h) // 2
    prompt_y = top + rows.index("Shell>") * cell_h
    if layout in ("centered", "wide"):
        # Test the physical crop regression directly in worn per-eye pixels.
        if (left != (360 if layout == "wide" else 448)
                or prompt_y < 570 or prompt_y + cell_h > 870):
            raise ValueError("Prompt fell outside the proposed central reading area")
        for u in range(EYE_WIDTH):
            column = frame[3 * u * NATIVE_WIDTH : 3 * (u + 1) * NATIVE_WIDTH]
            if left <= u < left + columns * cell_w:
                if any(column[: 3 * (NATIVE_WIDTH-top-height*cell_h)]) or any(column[3 * (NATIVE_WIDTH - top) :]):
                    raise ValueError("Pixels above or below the viewport")
            elif any(column):
                raise ValueError("Pixels beyond a horizontal margin")
    return {
        "perEyeDimensions": [EYE_WIDTH, NATIVE_WIDTH],
        "viewportXYWH": [left, top, columns * cell_w, height * cell_h],
        "promptCellBoundsXYWH": [left, prompt_y, len("Shell>") * cell_w, cell_h],
    }


def run(fd, reference, output, timeout, el, dtb=None, layout="wide", observe_welcome=False, stock_splash=None):
    welcome = None
    stock = mark = None
    if stock_splash is not None:
        if not observe_welcome or layout not in ("wide", "centered"):
            raise ValueError("Stock emblem requires the centered welcome observer")
        from oculus_logo import stock_frame, stock_mark
        stock = stock_frame(stock_splash)
        mark = stock_mark(stock)
    if observe_welcome:
        from welcome_observer import WelcomeObserver
        welcome = WelcomeObserver(output / "welcome", mark)

    evidence = embedded_shell(fd.read_bytes(), reference)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "uart.log"
        monitor = Path(tmp) / "qmp"
        surface = Path(tmp) / "frame"
        command = [
            "qemu-system-aarch64",
            "-machine",
            "virt,gic-version=3,secure=off,virtualization=" + ("on" if el == 2 else "off"),
            "-accel",
            "tcg",
            "-cpu",
            "cortex-a57",
            "-smp",
            "1",
            "-m",
            "1536",
            "-nodefaults",
            "-display",
            "none",
            "-serial",
            "file:" + str(log),
            "-qmp",
            f"unix:{monitor},server=on,wait=off",
            "-device",
            f"loader,file={fd.resolve()},addr=0x80080000,cpu-num=0,force-raw=on",
        ]
        if dtb is not None:
            if el != 1 or sha(dtb.read_bytes()) != DTB_SHA:
                raise ValueError("Pacific model requires EL1 and the verified stock EVT tree")
            fixture = Path(tmp) / "pacific.elf"
            obj = fixture.with_suffix(".o")
            subprocess.run(
                ["aarch64-linux-gnu-as", "-o", obj, ROOT / "tests/pacific_qemu_el2.S"], check=True
            )
            subprocess.run(
                ["aarch64-linux-gnu-ld", "-Ttext=0x42000000", "-o", fixture, obj], check=True
            )
            command[2] = "virt,gic-version=3,secure=off,virtualization=on"
            command[command.index("-cpu") + 1] = "cortex-a57,cntfrq=19200000"
            command[-1] = f"loader,file={fd.resolve()},addr=0x80080000,force-raw=on"
            command += [
                "-device",
                f"loader,file={dtb.resolve()},addr=0x82000000,force-raw=on",
                "-device",
                f"loader,file={fixture},cpu-num=0",
            ]
        if stock is not None:
            surface_input = Path(tmp) / "inherited.bgr"
            surface_input.write_bytes(stock)
            command += ["-device", f"loader,file={surface_input},addr={FB:#x},force-raw=on"]
        child = subprocess.Popen(command)
        deadline = time.monotonic() + timeout
        try:
            with socket.socket(socket.AF_UNIX) as channel:
                while not monitor.exists():
                    if child.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError("QEMU monitor did not start")
                    time.sleep(0.1)
                channel.settimeout(8)
                channel.connect(str(monitor))
                with channel.makefile("rwb", buffering=0) as wire:
                    assert "QMP" in json.loads(wire.readline())
                    request(wire, "qmp_capabilities")
                    frame, rows, serial = wait_for_prompt(wire, log, surface, deadline, dtb is None, layout, welcome)
            loads = re.findall(r"Loading driver at [^\r\n]+ (?:GoBdsDxe|Shell)\.efi", serial)
            if dtb is None and [line.split()[-1] for line in loads] != [
                "GoBdsDxe.efi",
                "Shell.efi",
            ]:
                raise RuntimeError("Unexpected BDS / Shell load sequence")
            if dtb is None and f"TrustMeBro: SEC -> DXE, EL{el}" not in serial:
                raise RuntimeError("Entry exception level differs")
            png = eye_png(frame)
            (output / "eye.png").write_bytes(png)
            viewport_frame = frame
            if mark is not None:
                from oculus_logo import check_footer
                footer_y = 919 if layout == "wide" else 960
                viewport_frame = check_footer(frame, mark, footer_y)
            report = {
                **evidence,
                "el": el,
                "machine": command[2],
                "fdSha256": sha(fd.read_bytes()),
                "shellFileGuid": SHELL_GUID,
                "screenRows": rows,
                "eyeGeometry": verify_viewport(viewport_frame, rows, layout),
                "eyesMatch": True,
                "eyeNativeBgrSha256": sha(frame[: SIZE // 2]),
                "eyePngSha256": sha(png),
                "uartLoadMessages": loads,
                "qemu": subprocess.check_output(
                    ["qemu-system-aarch64", "--version"], text=True
                ).splitlines()[0],
            }
            if welcome:
                report["welcome"] = welcome.finish()
            if mark is not None:
                report["oculusEmblem"] = {"source": "stock pixels preloaded into inherited scanout",
                                          "reducedLumaSha256": sha(mark), "exactPixelsBothEyes": True,
                                          "welcomeTopInTile": 355, "shellTopInEye": footer_y,
                                          "size": [68, 42]}
            if dtb is not None:
                report["pacificFdAtEl1"] = True
                report["dtbSha256"] = DTB_SHA
                report["counterHz"] = 19200000
                report["el2FixtureSha256"] = sha((ROOT / "tests/pacific_qemu_el2.S").read_bytes())
            (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
            return report
        finally:
            child.terminate()
            child.wait(timeout=10)
            if log.exists():
                (output / "uart.log").write_bytes(log.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fd", type=Path)
    parser.add_argument("shell_efi", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--timeout", type=int, default=65)
    parser.add_argument("--el", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--inspect-only", action="store_true", help="Check the Pacific FV without booting it"
    )
    parser.add_argument(
        "--pacific-dtb", type=Path, help="Boot the real Pacific FD using the EL2 QEMU GIC map"
    )
    parser.add_argument("--layout", choices=LAYOUTS, default="wide")
    parser.add_argument("--observe-welcome", action="store_true", help="Validate the 3D intro before the prompt")
    parser.add_argument("--stock-splash", type=Path, help="Seed inherited scanout from the private stock splash dump")
    args = parser.parse_args()
    if args.inspect_only:
        detail = inspect_pacific(args.fd, args.shell_efi)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "static.json").write_text(json.dumps(detail, indent=2) + "\n")
    else:
        detail = run(
            args.fd, args.shell_efi, args.output.resolve(), args.timeout, args.el, args.pacific_dtb, args.layout, args.observe_welcome, args.stock_splash
        )
    print(json.dumps(detail, indent=2))
