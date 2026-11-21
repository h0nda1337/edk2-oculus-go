"""Reviewed temporary boot for the centered two-eye Shell console.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

from functools import partial

from attended_terminal import attended_main, measure_once
from run_shell_once import ROOT, reviewed_inputs

REVIEW = "docs/evidence/shell-centered-review-20261120.json"
LEDGER = "local/physical-attempts/centered-shell-20261120.json"
PRIOR_TRIAL = "docs/evidence/shell-transfer-20261120.json"


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    verify = partial(reviewed_inputs, scope="pacific-centered-shell", previous=PRIOR_TRIAL)
    attended_main(ROOT, REVIEW, LEDGER, verify, "centered-shell", measure)
