"""One additional attended observation of the reviewed welcome image.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import json

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file
from run_welcome_once import (
    LEDGER as FIRST_LEDGER,
)
from run_welcome_once import (
    REVIEW as FIRST_REVIEW,
)
from run_welcome_once import (
    ROOT,
    verify,
)

REVIEW = "docs/evidence/welcome-repeat-review-20261120.json"
LEDGER = "local/physical-attempts/welcome-repeat-20261120.json"


def reviewed_repeat(root, review):
    require(
        review["scope"] == "pacific-welcome-repeat"
        and review["maxAttempts"] == 1
        and review["originalReview"]["file"] == FIRST_REVIEW
        and review["firstAttempt"]["file"] == FIRST_LEDGER,
        "Unexpected observation review",
    )
    _, original = checked_file(root, review["originalReview"], ("docs",))
    candidate = json.loads(original)
    image, unit = verify(root, candidate)
    _, first = checked_file(root, review["firstAttempt"], ("local",))
    _, evidence = checked_file(root, review["firstTrial"], ("docs",))
    _, recovery = checked_file(root, review["firstRecovery"], ("local",))
    attempt, trial, android = map(json.loads, (first, evidence, recovery))
    require(
        review["image"] == candidate["image"]
        and review["fd"] == candidate["fd"]
        and attempt["imageSha256"]
        == trial["imageSha256"]
        == candidate["image"]["sha256"]
        and attempt["status"] == "CONSUMED-BEFORE-SEND"
        and attempt["reviewSha256"]
        == trial["reviewSha256"]
        == review["originalReview"]["sha256"]
        and trial["recovery"]["reportSha256"] == review["firstRecovery"]["sha256"]
        and android["serial"] == unit
        and android["result"] == "PASS-READONLY",
        "Image or previous trial differs from the observation review",
    )
    return image, unit


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed_repeat, "welcome-repeat", measure)
