"""Verify the Pacific Shell candidate or perform a single attended RAM boot.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""

import json
import re
import zlib
from pathlib import Path

from android_boot import DTB_SHA, HEADER, PAGE, verify_container
from attended_terminal import attended_main, measure_once
from run_sec_c_once import require
from run_sec_visual_once import checked_file, sha
from verify_fd import SHELL_FD_SIZE, verify

ROOT = Path(__file__).resolve().parents[1]
REVIEW = "docs/evidence/shell-review-20261120.json"
LEDGER = "local/physical-attempts/normal-shell-20261120.json"
PREVIOUS = "docs/evidence/dxe-app-transfer-20261120.json"


def reviewed_inputs(root, review, *, scope="pacific-normal-shell", previous=PREVIOUS):
    require(
        review["scope"] == scope
        and review["decision"] == "ONE-ATTENDED-TEMPORARY-BOOT"
        and review["maxAttempts"] == 1,
        "Unexpected physical trial",
    )
    image_path, image = checked_file(root, review["image"], ("local",))
    fd_path, fd = checked_file(root, review["fd"], ("build",))
    require(
        fd_path.parent.name.startswith("DEBUG-NORMAL-")
        and len(fd) == SHELL_FD_SIZE
        and len(image) == review["image"]["size"]
        and len(fd) == review["fd"]["size"],
        "Unexpected device build",
    )
    verify(fd)
    kernel = image[PAGE : PAGE + HEADER.unpack_from(image)[1]]
    decoder = zlib.decompressobj(31)
    require(
        decoder.decompress(kernel, len(fd) + 1) == fd
        and decoder.eof
        and sha(decoder.unused_data) == DTB_SHA,
        "FD or selected EVT tree differs",
    )
    verify_container(image, fd, decoder.unused_data)
    _, sources = checked_file(root, review["sourceAudit"], ("build",))
    audit = json.loads(sources)
    require(
        audit["result"] == "PASS"
        and not audit["rejected"]
        and audit["upstreamTreeClean"]
        and audit["upstreamInputsTracked"]
        and audit["edk2"] == json.loads((root / "sources.lock.json").read_bytes())["edk2"],
        "Device source audit failed",
    )
    _, raw = checked_file(root, review["physicalStatic"], ("docs",))
    static = json.loads(raw)
    require(
        static["fdSha256"] == sha(fd)
        and static["shellFileGuid"] == "7c04a583-9e3e-4f1c-ad65-e05268d0b4d1"
        and re.fullmatch("[0-9a-f]{64}", static["shellPeSha256"])
        and static["shellPeBytes"] > 0
        and static["flashBackedStorageDrivers"] == [],
        "Unexpected Pacific firmware volume",
    )
    _, raw = checked_file(root, review["arena"], ("docs",))
    arena = json.loads(raw)
    require(
        arena["fdSha256"] == sha(fd)
        and len(arena["cases"]) == 12
        and {(r["el"], r["case"]) for r in arena["cases"]}
        == {
            (el, c)
            for el in (1, 2)
            for c in (
                "clean",
                "first-marker",
                "middle",
                "last-marker",
                "last-word",
                "overlapping-dtb",
            )
        }
        and all(
            r["stoppedAt"] == ("ArmEnableVFP" if r["case"] == "clean" else "EntryRejected")
            for r in arena["cases"]
        ),
        "Missing SEC qualification for the actual device FD",
    )
    _, raw = checked_file(root, review["pacificPrompt"], ("docs",))
    prompt = json.loads(raw)
    require(
        prompt["pacificFdAtEl1"]
        and prompt["el"] == 1
        and prompt["fdSha256"] == sha(fd)
        and prompt["shellPeSha256"] == static["shellPeSha256"]
        and prompt["dtbSha256"] == DTB_SHA
        and prompt["eyesMatch"]
        and "Shell>" in prompt["screenRows"],
        "The model did not show the Shell prompt with the packaged device FD",
    )
    centered = scope in ("pacific-centered-shell", "pacific-welcome-shell")
    if centered:
        require_centered_prompt(prompt)
    for el in (1, 2):
        _, raw = checked_file(root, review["model"][str(el)], ("docs",))
        run = json.loads(raw)
        require(
            run["el"] == el
            and run["eyesMatch"]
            and "Shell>" in run["screenRows"]
            and run["fdSha256"] == review["modelFdSha256"],
            "Missing QEMU prompt evidence",
        )
        if centered:
            require_centered_prompt(run)
            require(run["eyePngSha256"] == prompt["eyePngSha256"], "Different centered console render")
    _, raw = checked_file(root, review["priorReadback"], ("local",))
    previous_record = json.loads((root / previous).read_bytes())
    require(sha(raw) == previous_record["recovery"]["reportSha256"], "Prior device recovery differs")
    unit = json.loads(raw)["serial"]
    require(re.fullmatch("[A-Za-z0-9]+", unit), "Unexpected unit identity")
    return image_path, unit


def require_centered_prompt(run):
    geometry = run["eyeGeometry"]
    x, y, width, height = geometry["promptCellBoundsXYWH"]
    require(
        geometry["perEyeDimensions"] == [1280, 1440]
        and geometry["viewportXYWH"] == [448, 492, 384, 456]
        and (x, width, height) == (448, 96, 38)
        and 570 <= y <= 832,
        "Prompt outside the reviewed central viewport",
    )


def measure(root, image, tool, serial, preflight, report, output):
    measure_once(root, LEDGER, image, tool, serial, preflight, report, output)


if __name__ == "__main__":
    attended_main(ROOT, REVIEW, LEDGER, reviewed_inputs, "normal-shell", measure)
