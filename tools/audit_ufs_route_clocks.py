"""Identify Pacific's AGGRE2 clock controls in the original RPM tables.

This host utility reads only private backup files and published source. Its
report contains register/record metadata, never firmware contents.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KERNEL = "https://github.com/facebookincubator/oculus-linux-kernel/blob/9475755c1a328a7b873721897ef339a8ad35c86a/"
HEADER = "include/dt-bindings/clock/msm-clocks-hwio-8996.h"
HEADER_SHA256 = "0da65a12dcba76f40175f5ef1731776b7f3b5a6a3a55d208044000d8322e8f58"
GCC_BASE = 0x300000
BRANCHES = (
    ("gcc_aggre{}_snoc_axi_clk", "GCC_AGGRE0_SNOC_AXI_CBCR", 0x81008, 0x83008),
    ("gcc_aggre{}_cnoc_ahb_clk", "GCC_AGGRE0_CNOC_AHB_CBCR", 0x8100C, 0x8300C),
    ("gcc_smmu_aggre{}_axi_clk", "GCC_SMMU_AGGRE0_AXI_CBCR", 0x81014, 0x8301C),
    ("gcc_smmu_aggre{}_ahb_clk", "GCC_SMMU_AGGRE0_AHB_CBCR", 0x81018, 0x83020),
)


def check(condition, detail):
    if not condition:
        raise ValueError(detail)


def load_segments(image):
    check(image[:7] == b"\x7fELF\x01\x01\x01", "expected a little-endian ELF32")
    elf = struct.unpack_from("<HHIIIIIHHHHHH", image, 16)
    check(elf[0:2] == (2, 40) and elf[8] == 32, "wrong RPM machine or program header")
    loads = []
    for i in range(elf[9]):
        kind, offset, va, _, size, mem_size, _, _ = struct.unpack_from(
            "<8I", image, elf[4] + i * elf[8])
        if kind == 1:
            check(0 < size <= mem_size and offset + size <= len(image), "invalid ELF load")
            loads.append((offset, va, size))
    check(len(loads) == 2 and loads[0][1] == 0 and loads[1][1] == 0x90000,
          "unexpected RPM string/data segments")
    return loads


def named_record(image, segments, name, expected_offset):
    text_file, text_va, text_size = segments[0]
    data_file, _, data_size = segments[1]
    # A second copy of each clock name is used in a string-pointer list.
    # A valid record must instead pair a string VA with the expected register
    # in file-backed writable data. Never interpret physical ELF addresses as VAs.
    encoded = name.encode("ascii") + b"\0"
    records = []
    for match in re.finditer(re.escape(encoded), image[text_file:text_file + text_size]):
        name_va = text_va + match.start()
        key = struct.pack("<II", name_va, expected_offset)
        for ref in re.finditer(re.escape(key), image[data_file:data_file + data_size]):
            pos = data_file + ref.start()
            if pos % 4 == 0:
                records.append((pos, name_va))
    check(len(records) == 1, f"expected one typed record for {name}")
    return records[0]


def audit(rpm, header):
    image = rpm.read_bytes()
    inventory = json.loads((ROOT / "docs/evidence/partitions.json").read_bytes())
    stock, = [entry for entry in inventory["partitions"] if entry["name"] == "rpm_a"]
    digest = hashlib.sha256(image).hexdigest()
    check(len(image) == stock["size"] and digest == stock["sha256"], "unexpected rpm_a backup")
    segments = load_segments(image)
    clock_header = None
    if header is not None:
        content = header.read_bytes()
        check(hashlib.sha256(content).hexdigest() == HEADER_SHA256, "unexpected Go kernel header")
        clock_header = content.decode("ascii")

    branches = []
    controls = []
    for pattern, macro, aggre0, aggre2 in BRANCHES:
        local_records = []
        for fabric, register in ((0, aggre0), (2, aggre2)):
            name = pattern.format(fabric)
            pos, _ = named_record(image, segments, name, register)
            _, _, block, zero1, zero2, ops, tag = struct.unpack_from("<7I", image, pos)
            check((block, zero1, zero2, ops) == (register & ~0xfff, 0, 0, 0x9224c),
                  f"unexpected branch structure for {name}")
            check(tag >> 16 == 1, f"unexpected branch tag for {name}")
            local_records.append(pos)
            row = dict(name=name, rpmFileOffset=hex(pos), gccOffset=hex(register),
                       physicalAddress=hex(GCC_BASE + register))
            if fabric == 0:
                if clock_header is not None:
                    definition = re.search(rf"(?m)^#define[ \t]+{macro}[ \t]+\((0x[\da-fA-F]+)\)", clock_header)
                    check(definition and int(definition[1], 16) == register, f"header lacks {macro}")
                row["headerControl"] = macro
                controls.append(row)
            else:
                branches.append(row)
        # Each class contains the 0, 1 and 2 fabrics as consecutive 28-byte records.
        check(local_records[1] == local_records[0] + 2 * 28, "clock records are not contiguous")
        middle = local_records[0] + 28
        middle_offset, = struct.unpack_from("<I", image, middle + 4)
        check(named_record(image, segments, pattern.format(1), middle_offset)[0] == middle,
              "unexpected intermediate clock record")

    domains = []
    for fabric, register in ((0, 0x81004), (2, 0x83004)):
        name = f"VDD_AGGRE{fabric}_NOC"
        pos, _ = named_record(image, segments, name, register)
        _, _, methods_va, reserved = struct.unpack_from("<4I", image, pos)
        data_file, data_va, _ = segments[1]
        methods = methods_va - data_va + data_file
        check(methods == pos - 16 and reserved == 0, "unexpected VDD record")
        funcs = struct.unpack_from("<4I", image, methods)
        check(funcs[3] == 0 and all((x & 1) and x < segments[0][2] for x in funcs[:3]),
              "expected three Thumb callbacks in VDD control table")
        domains.append(dict(name=name, rpmFileOffset=hex(pos), gccOffset=hex(register),
                            physicalAddress=hex(GCC_BASE + register)))

    return dict(
        scope="Static Pacific RPM clock and power tables. Live handoff and DMA unmeasured.",
        stockRpmSha256=digest, gccBase=hex(GCC_BASE), aggre2Branches=branches, domains=domains,
        aggre0Controls=controls, kernelHeaderSha256=HEADER_SHA256 if clock_header is not None else None,
        registerFields={
            "CBCR": {"statusBits": "31:28", "on": [0, 2], "off": 8,
                     "other": "unclassified", "localEnableBit": 0},
            "GDSCR": {"powerOnBit": 31, "softwareCollapseVoteBit": 0},
        },
        sources={
            "gccRange": KERNEL + "arch/arm/boot/dts/qcom/msm8996.dtsi#L750-L753",
            "headerControls": KERNEL + HEADER + "#L462-L476",
            "aggre0GdscControl": KERNEL + "arch/arm/boot/dts/qcom/msm-gdsc-8996.dtsi#L207-L211",
            "branchEnable": KERNEL + "drivers/clk/msm/clock-local2.c#L67-L68",
            "branchStatus": KERNEL + "drivers/clk/msm/clock-local2.c#L668-L705",
            "domainBits": KERNEL + "drivers/clk/msm/gdsc.c#L28-L34",
            "domainVotes": KERNEL + "drivers/clk/msm/gdsc.c#L128-L137",
        },
        physicalUfsStreamId="UNKNOWN", busAddressForCpuPage80441000="UNKNOWN",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpm", type=Path, required=True, help="original private rpm_a.img")
    parser.add_argument("--header", type=Path, help="official pinned Go clock register header")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.rpm, args.header)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8", newline="\n")
