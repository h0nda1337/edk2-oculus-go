"""Report selected DMA/UFS build options from the preserved Pacific boot_a.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
from pathlib import Path
import re
import zlib

from android_boot import PAGE, check_stock, digest

SYMBOLS = (
    "CONFIG_ARM64", "CONFIG_IKCONFIG", "CONFIG_IKCONFIG_PROC",
    "CONFIG_SCSI_UFSHCD_PLATFORM", "CONFIG_SCSI_UFS_QCOM", "CONFIG_PHY_QCOM_UFS",
    "CONFIG_ARM64_DMA_USE_IOMMU", "CONFIG_ARM_SMMU", "CONFIG_SWIOTLB", "CONFIG_DMA_API_DEBUG",
)


def audit(stock):
    fields = check_stock(stock)
    # The Android kernel member has appended device trees after the gzip stream.
    image = zlib.decompress(stock[PAGE:PAGE + fields[1]], wbits=31)
    start = b"IKCFG_ST"
    if image.count(start) != 1:
        raise ValueError("Expected a unique embedded kernel configuration")
    payload = zlib.decompressobj(wbits=31)
    config = payload.decompress(image.split(start, 1)[1])
    if not payload.eof or not payload.unused_data.startswith(b"IKCFG_ED"):
        raise ValueError("Incomplete IKCONFIG")
    text = config.decode("ascii")
    options = {}
    for symbol in SYMBOLS:
        hits = re.findall(rf"^(?:{symbol}=(y|m|n)|# {symbol} is not set)$", text, re.M)
        if len(hits) != 1:
            raise ValueError(f"Missing or ambiguous Kconfig value for {symbol}")
        options[symbol] = hits[0] or "n"
    return {"scope": "Android kernel build options; runtime DMA selection is per device",
            "bootASha256": digest(stock), "kernelImageSha256": digest(image),
            "ikconfigSha256": digest(config), "config": options}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists() and args.report.samefile(args.boot):
        parser.error("The report must be separate from the firmware input")
    report = audit(args.boot.read_bytes())
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
