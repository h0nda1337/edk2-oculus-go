"""Observe the procedural startup scene in QEMU guest RAM. SPDX-License-Identifier: BSD-2-Clause-Patent"""

import hashlib
import json
import math
import re
import struct
import time
import zlib
from pathlib import Path

WIDTH, HEIGHT = 352, 400
MESSAGE = "Welcome to EDK2 Go!"
ROOT = Path(__file__).resolve().parents[1]


def eye_crop(scan, eye):
    # Worn-orientation RGB, retaining every guest pixel in the scene tile.
    stride = 1440 * 3
    first = (eye * 1280 + (1280 - WIDTH) // 2) * stride
    rgb = bytearray(WIDTH * HEIGHT * 3)
    for y in range(HEIGHT):
        pos = first + (1439 - (1440 - HEIGHT) // 2 - y) * 3
        line = memoryview(rgb)[3 * y * WIDTH : 3 * (y + 1) * WIDTH]
        for channel in range(3):
            start = pos + 2 - channel
            line[channel::3] = scan[start : start + WIDTH * stride : stride]
    return rgb


SCAN_ROWS = range(56, 285, 8)


def scan_edges(rgb):
    edges = []
    for y in SCAN_ROWS:
        blue = rgb[y * WIDTH * 3 + 2 : (y + 1) * WIDTH * 3 : 6]
        xs = [2 * i for i, value in enumerate(blue) if value > 24]
        edges.append((xs[0], xs[-1]) if xs else None)
    return edges


def references():
    # Independently project the actual vertices with floating-point rotations.
    # At each scanline the extrema of chords between vertices bound a convex hull.
    src = (ROOT / "OculusGoPkg/Drivers/GoBdsDxe/Welcome.c").read_text()
    mesh = src.split("POINT mMesh[] = {", 1)[1].split("};", 1)[0]
    vertices = [
        tuple(map(int, v))
        for v in re.findall(r"\{\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\s*\}", mesh)
    ]
    assert len(vertices) == 5
    apex, *base = vertices
    assert len({y for x, y, z in base}) == 1 and apex[1] < base[0][1]
    assert len({(x, z) for x, y, z in base}) == 4
    assert {x for x, y, z in base} == {-84, 84} == {z for x, y, z in base}
    assert apex[0] == apex[2] == 0 and base[0][1] - apex[1] == 153
    poses = {}
    pitch = math.radians(14)
    for degree in range(0, 90, 3):
        yaw = math.radians(degree) + 148 * math.tau / 1024
        pts = []
        for x, y, z in vertices:
            x, z = (
                x * math.cos(yaw) + z * math.sin(yaw),
                z * math.cos(yaw) - x * math.sin(yaw),
            )
            y, z = (
                y * math.cos(pitch) - z * math.sin(pitch),
                z * math.cos(pitch) + y * math.sin(pitch),
            )
            y -= 10
            pts.append(
                (
                    WIDTH / 2 + (340 * x - 14 * z) / (340 + z),
                    HEIGHT / 2 + 340 * y / (340 + z),
                )
            )
        outline = []
        for row in SCAN_ROWS:
            xs = [
                x0 + (x1 - x0) * (row - y0) / (y1 - y0)
                for x0, y0 in pts
                for x1, y1 in pts
                if y0 <= row < y1
            ]
            outline.append((min(xs), max(xs)) if xs else None)
        poses[degree] = outline
    return poses


def estimate_yaw(edges, poses):
    if sum(pair is not None for pair in edges) < 15:
        return None

    def distance(template):
        error = 0
        for actual, expected in zip(edges, template):
            if actual and expected:
                error += sum(abs(a - b) for a, b in zip(actual, expected)) / 2
            elif actual or expected:
                error += 28
        return error / len(edges)

    error, degree = min((distance(template), deg) for deg, template in poses.items())
    return degree if error < 6 else None


def lit_letters(rgb, font):
    """Recognize the Shell glyph masks and measure the ink intensity of each."""
    levels = []
    for i, ch in enumerate(MESSAGE):
        if ch == " ":
            continue
        level = 0
        matched = True
        for v, row in enumerate(font[ch]):
            for u in range(8):
                x = (WIDTH - len(MESSAGE) * 16) // 2 + 16 * i + 2 * u
                y = HEIGHT // 2 + 115 + 2 * v
                pos = 3 * (y * WIDTH + x)
                red, green, blue = rgb[pos : pos + 3]
                # The reflected light pool can reach the top blank row. Select
                # the measured ink chromaticity, including integer fade rounding.
                ink = (
                    blue >= 32
                    and abs(255 * red - 58 * blue) <= 510
                    and abs(255 * green - 156 * blue) <= 510
                )
                if ink != bool(row & (128 >> u)):
                    matched = False
                    break
                if ink:
                    level = max(level, blue)
            if not matched:
                break
        levels.append(level if matched else 0)
    return levels


def png(rgb):
    def chunk(tag, b):
        return (
            struct.pack(">I", len(b)) + tag + b + struct.pack(">I", zlib.crc32(tag + b))
        )

    raw = b"".join(
        b"\0" + rgb[y * 3 * WIDTH : (y + 1) * 3 * WIDTH] for y in range(HEIGHT)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 4))
        + chunk(b"IEND", b"")
    )


class WelcomeObserver:
    def __init__(self, output, stock_mark=None):
        self.stock_mark = stock_mark
        self.output = output
        self.frames = []
        self.start = None
        self.poses = references()
        header = (
            ROOT / "OculusGoPkg/Include/third-party/edk2/ConsoleFont.h"
        ).read_text()
        self.font = {
            chr(int(code, 16)): bytes.fromhex(
                " ".join(re.findall(r"0x([0-9a-f]{2})", bits))
            )
            for bits, code in re.findall(
                r"\{ ([^{}]+) \},  // U\+([0-9A-Fa-f]{4})", header
            )
        }
        self.output.mkdir(parents=True, exist_ok=True)

    def observe(self, frame):
        first = eye_crop(frame, 0)
        # Signature of the static blue backdrop outside the projected solid.
        pos = 3 * (200 * WIDTH + 22)
        if first[pos : pos + 3] != bytes((0, 0, 2)):
            return
        second = eye_crop(frame, 1)
        if second[pos : pos + 3] != first[pos : pos + 3]:
            return
        now = time.monotonic()
        if self.start is None:
            self.start = now
        left_edges = scan_edges(first)
        right_edges = scan_edges(second)
        occupied = [y for y, pair in zip(SCAN_ROWS, left_edges) if pair]
        image = png(first)
        name = f"frame-{len(self.frames):03}.png"
        (self.output / name).write_bytes(image)
        from oculus_logo import matches_tile
        stock_visible = (self.stock_mark is not None and matches_tile(first, self.stock_mark)
                        and matches_tile(second, self.stock_mark))
        self.frames.append(
            {
                "ms": round(1000 * (now - self.start)),
                "top": min(occupied, default=None),
                "estimatedYaw": estimate_yaw(left_edges, self.poses),
                "stereoContourRows": sum(
                    1 for a, b in zip(left_edges, right_edges) if a and b and a != b
                ),
                "letters": lit_letters(first, self.font),
                "rightLetters": lit_letters(second, self.font),
                "differentViews": first != second,
                "stockEmblemBothEyes": stock_visible,
                "png": name,
                "sha256": hashlib.sha256(image).hexdigest(),
            }
        )

    def finish(self):
        (self.output / "samples.json").write_text(
            json.dumps(self.frames, indent=2) + "\n"
        )
        targets = [0, 90, 180, 270, 360]
        observed = []
        angle = 0
        previous = None
        rising = False
        partial = False
        full = None
        for sample in self.frames:
            if sample["top"] is not None and sample["top"] > 195:
                rising = True
            levels = sample["letters"]
            degree = sample["estimatedYaw"]
            if degree is not None and not any(levels):
                # A regular pyramid repeats its silhouette every 90 degrees.
                # Follow successive poses around the four faces and unwrap them.
                if previous is None and min(degree, 90 - degree) <= 9:
                    previous = degree
                if previous is not None:
                    prior_angle = angle
                    step = (degree - previous + 45) % 90 - 45
                    angle += step
                    previous = degree
                    if len(observed) < len(targets):
                        target = targets[len(observed)]
                        # QMP samples are asynchronous: e.g. 168° then 192°
                        # brackets 180°. Only interpolate a small forward step,
                        # well below the 45° silhouette unwrapping ambiguity.
                        crossed = 0 < step <= 30 and prior_angle < target < angle
                        if abs(angle - target) <= 10 or crossed:
                            observed.append(target)
            if 0 < sum(v > 0 for v in levels) < len(levels) and any(
                32 <= v < 245 for v in levels
            ):
                partial = True
            if (
                min(levels) == 255
                and min(sample["rightLetters"]) == 255
                and (self.stock_mark is None or sample["stockEmblemBothEyes"])
                and sample["differentViews"]
                and sample["stereoContourRows"] >= 6
            ):
                full = sample
        if not (
            rising and observed == targets and 342 <= angle <= 378 and partial and full
        ):
            raise ValueError(
                f"Incomplete intro observations: rise={rising}, turn={observed} ({angle}°), "
                f"fade={partial}, stereo greeting={bool(full)}, samples={len(self.frames)}"
            )
        return {
            "observedFrames": len(self.frames),
            "observedMs": self.frames[-1]["ms"],
            "enteredFromBelow": rising,
            "observedQuarterTurnsDegrees": observed,
            "unwrappedRotationEstimateDegrees": angle,
            "mesh": "square-based pyramid, one apex and four corners",
            "progressiveGlyphIllumination": partial,
            "messageInBothEyes": MESSAGE,
            "distinctStereoViewsAtFullText": True,
            "stereoContourRowsAtFullText": full["stereoContourRows"],
            "fullyLitEyePngSha256": full["sha256"],
        }
