"""Validate the 3D welcome and centered Shell image before one attended RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import json

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_shell_once import ROOT, reviewed_inputs

REVIEW = "docs/evidence/welcome-review-20261120.json"
LEDGER = "local/physical-attempts/welcome-shell-20261120.json"


def verify(root, review):
    image, unit = reviewed_inputs(
        root,
        review,
        scope="pacific-welcome-shell",
        previous="docs/evidence/shell-centered-transfer-20261120.json",
    )
    for record in (review["pacificPrompt"], *review["model"].values()):
        _, raw = checked_file(root, record, ("docs",))
        scene = json.loads(raw)["welcome"]
        require(
            scene["enteredFromBelow"]
            and scene["progressiveGlyphIllumination"]
            and scene["observedQuarterTurnsDegrees"] == [0, 90, 180, 270, 360]
            and scene["mesh"] == "square-based pyramid, one apex and four corners"
            and 342 <= scene["unwrappedRotationEstimateDegrees"] <= 378
            and scene["messageInBothEyes"] == "Welcome to EDK2 Go!"
            and scene["distinctStereoViewsAtFullText"],
            "Missing observed welcome sequence",
        )
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, verify, "welcome-shell", measure)
