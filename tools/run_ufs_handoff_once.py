"""Verify the passive Pacific UFS snapshot or submit its reviewed temporary RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
from pathlib import Path

from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from terminal_review import verify_terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
REVIEW = "docs/evidence/ufs-handoff-review-20261121.json"
LEDGER = "local/physical-attempts/ufs-handoff-20261121.json"
PREVIOUS = "docs/evidence/oculus-logo-transfer-20261120.json"
SEC = {"OculusGoPkg/Include/Display/Framebuffer.h", "OculusGoPkg/Include/third-party/edk2/ConsoleFont.h",
       *("OculusGoPkg/SecMem/" + n for n in ["Fdt.c", "UfsEntry.S", "UfsHandoff.c"])}
REQUIRED = SEC | {"OculusGoPkg/SecMem/UfsHandoff.inf", "OculusGoPkg/OculusGoPkg.dsc",
                  "OculusGoPkg/OculusGoPkg.fdf", "scripts/build.sh", "tests/ufs_handoff_qemu.py",
                  "tests/ufs_handoff_static.py", "tests/entry_harness.S", "tests/sec_mem_qemu.py",
                  "tests/sec_c_qemu.py", "tests/sec_dxe_static.py", "tools/android_boot.py",
                  "tools/verify_fd.py", "tools/audit_build_sources.py", "tools/terminal_review.py",
                  "tools/attended_terminal.py", "tools/collect_readonly_preflight.py",
                  "tools/run_sec_c_once.py", "tools/run_sec_visual_once.py", "tools/inspect_fastboot.py",
                  "tools/emulate_entry.py", "tools/emulate_sec_handoff.py", "tools/run_ufs_handoff_once.py"}


def verify_reports(model, static, digest):
    require(model["fdSha256"] == static["fdSha256"] == digest and model["outcome"] == "PASS-QEMU"
            and static["status"] == "PASS-STATIC" and static["secOnly"] == "5bc15fed-b682-4b88-b6a2-5d4c84c3a90e"
            and static["vectorsVerified"] == 16 and len(static["registerAddresses"]) == 13,
            "Unexpected probe or evidence")
    expected = {"active", "power-off", "collapse-request", "reset", "ahb-off", "axi-transition",
                "noc-off", "aggre-off", "bad-version", "bus-ones", "hce-off", "load-abort", "wrong-board"}
    cases = model["cases"]
    require(len(cases) == 2 * len(expected) and {(c["el"], c["case"]) for c in cases} ==
            {(el, case) for el in (1, 2) for case in expected}
            and all(c["peripheralStores"] == 0 and c["expectedScreenVerified"] for c in cases),
            "Incomplete watchpoint or stereo display evidence")


def reviewed(root, record):
    return verify_terminal_inputs(root, record, scope="terminal-ufs-handoff", build_prefix="DEBUG-UFS_HANDOFF-",
                                  sec_sources=SEC, required=REQUIRED, previous_record=PREVIOUS,
                                  validate_reports=verify_reports)


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed, "ufs-handoff", measure)
