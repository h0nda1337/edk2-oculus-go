"""Review the stock-emblem candidate or submit one attended RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import json

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_shell_once import ROOT, reviewed_inputs

REVIEW = "docs/evidence/oculus-logo-review-20261120.json"
LEDGER = "local/physical-attempts/oculus-logo-20261120.json"


def verify(root, review):
    image, unit = reviewed_inputs(
        root,
        review,
        scope="pacific-oculus-logo",
        previous="docs/evidence/welcome-repeat-transfer-20261120.json",
    )
    for reference in (review["pacificPrompt"], *review["model"].values()):
        _, raw = checked_file(root, reference, ("docs",))
        run = json.loads(raw)
        geometry = run["eyeGeometry"]
        x, y, width, height = geometry["promptCellBoundsXYWH"]
        require(
            geometry["viewportXYWH"] == [315, 557, 650, 325]
            and (x, width, height) == (315, 60, 25)
            and 570 <= y <= 845,
            "Unexpected wide console geometry",
        )
        emblem, welcome = run["oculusEmblem"], run["welcome"]
        require(
            emblem["exactPixelsBothEyes"]
            and emblem["size"] == [68, 42]
            and (emblem["welcomeTopInTile"], emblem["shellTopInEye"]) == (355, 699)
            and emblem["shellLeftInEye"] == 606
            and emblem["reducedLumaSha256"]
            == "a0d59cc433f7a73f5e410aa3f0f67322312167950e5c1d74e18b8d2bb628cd7d"
            and welcome["observedQuarterTurnsDegrees"] == [0, 90, 180, 270, 360]
            and welcome["messageInBothEyes"] == "Welcome to EDK2 Go!",
            "Expected the stock emblem under the stereo greeting and Shell",
        )
    _, raw = checked_file(root, review["noSplashPrompt"], ("docs",))
    blank = json.loads(raw)
    require(
        blank["fdSha256"] == review["fd"]["sha256"]
        and blank["eyesMatch"]
        and "Shell>" in blank["screenRows"]
        and blank["stockEmblemAbsent"] and "oculusEmblem" not in blank,
        "Missing normal boot without a recognized emblem",
    )
    _, raw = checked_file(root, review["diskReadTest"], ("docs",))
    disk = json.loads(raw)
    require(
        disk["cases"] == {"splash": "PASS", "other": "MISSING"}
        and disk["splashSha256"] == "d8ba4434e87f8bfc55f33091c2d78401fcea22a068105942285edb2da6869d4a",
        "Missing positive and negative GPT read evidence",
    )
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, verify, "oculus-logo", measure)
