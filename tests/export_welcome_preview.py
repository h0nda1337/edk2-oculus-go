"""Export a one-eye QEMU capture of the welcome and Shell transition (Pillow, host only).
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import argparse
import hashlib
import json
from io import BytesIO
from itertools import pairwise
from pathlib import Path

from PIL import Image


def export(run, output):
    report = json.loads((run / "result.json").read_bytes())
    samples = json.loads((run / "welcome/samples.json").read_bytes())
    if (
        len(samples) != report["welcome"]["observedFrames"]
        or "Shell>" not in report["screenRows"]
    ):
        raise ValueError("Incomplete QEMU run")
    frames, times = [], []
    for i, sample in enumerate(samples):
        data = (run / "welcome" / f"frame-{i:03}.png").read_bytes()
        if hashlib.sha256(data).hexdigest() != sample["sha256"]:
            raise ValueError("Changed QEMU frame")
        with Image.open(BytesIO(data)) as crop:
            if crop.size != (352, 400):
                raise ValueError("Unexpected scene size")
            canvas = Image.new("RGB", (384, 456))
            canvas.paste(crop, (16, 28))
        frames.append(canvas)
        times.append(sample["ms"])

    data = (run / "eye.png").read_bytes()
    if hashlib.sha256(data).hexdigest() != report["eyePngSha256"]:
        raise ValueError("Shell capture mismatch")
    with Image.open(BytesIO(data)) as eye:
        # The Shell capture is a full eye at half scale; keep the same viewport.
        frames.append(
            eye.crop((224, 246, 416, 474)).resize((384, 456), Image.Resampling.NEAREST)
        )
    durations = [max(1, b - a) for a, b in pairwise(times)] + [110, 1400]
    frames[0].save(
        output,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        lossless=True,
        method=4,
        loop=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.run, args.output)
