"""Exercise the non-secure ANOC2 snapshot in the real terminal SEC image.
Only the register values in the ROM fixture are synthetic. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import subprocess

from ufs_route_clocks_fd_qemu import run_panel_suite


GUID = "561537ce-d1cf-4251-a732-23809d46b55f"
NODE = "/soc/arm,smmu-anoc2@1680000"
# First five readings from the attended UFS_ROUTE_CLOCKS panel.
REGS = [(0x383004, "DOM", 0xa0222000), (0x383008, "NAX", 1),
        (0x38300c, "NAH", 0x20008001), (0x38301c, "SAX", 0x2000c221),
        (0x383020, "SAH", 0x20008001), (0x1680020, "ID0", 0x68000808),
        (0x1680024, "ID1", 0x20020008), (0x1680028, "ID2", 0x00001022),
        (0x1680000, "CR0", 0x400)]

# Modify a copy of the captured board tree. The positive rewrite checks the tool path.
REWRITE_REG = ("-t", "x", NODE, "reg", "1680000", "20000")
DT_MUTATIONS = {
    "wrong-reg": ("-t", "x", NODE, "reg", "1690000", "20000"),
    "wrong-compatible": ("-t", "s", NODE, "compatible", "arm,smmu-v3"),
    "wrong-range": ("-t", "x", "/soc", "ranges", "0", "0", "1000", "ffffffff"),
    "disabled-node": ("-t", "s", NODE, "status", "disabled"),
    "static-cb": (NODE, "qcom,enable-static-cb"),
    "secure-alias": (NODE, "calxeda,smmu-secure-config-access"),
    "missing-skip-init": ("-d", NODE, "qcom,skip-init"),
}
CASES = [
    ("active", 9, {}, "ROUTE"), ("dt-positive-rewrite", 9, {}, "ROUTE"), ("clientpd-set", 9, {8: 1}, "ROUTE"),
    ("cr0-zero", 9, {8: 0}, "ROUTE"),
    ("domain-off", 1, {0: 0}, "STOP"),
    ("collapse-request", 1, {0: 0x80000001}, "STOP"),
    *[(f"gated-{REGS[i][1].lower()}", i + 1, {i: 0x80000001}, "STOP") for i in range(1, 5)],
    ("zero-clock", 5, {4: 0}, "STOP"), ("transition", 4, {3: 0x10000001}, "STOP"),
    ("no-stages", 6, {5: 0}, "INVALID"), ("no-banks", 7, {6: 0}, "INVALID"),
    ("invalid-bank-count", 7, {6: 0x00030002}, "INVALID"),
    ("invalid-id2", 8, {7: 0xffffffff}, "INVALID"), ("invalid-cr0", 9, {8: 0xffffffff}, "INVALID"),
    ("abort-id0", 6, {}, "FAULT"), ("abort-cr0", 9, {}, "FAULT"),
    ("wrong-board", 0, {}, ""), *[(name, 0, {}, "") for name in DT_MUTATIONS],
]


def tree_for_case(data, name, tmp):
    args = REWRITE_REG if name == "dt-positive-rewrite" else DT_MUTATIONS.get(name)
    if args is None:
        return data
    fixture = tmp / "route.dtb"
    fixture.write_bytes(data)
    # fdtput options precede its file, followed by node and property.
    pos = args.index(NODE) if NODE in args else args.index("/soc")
    subprocess.run(["fdtput", *args[:pos], str(fixture), *args[pos:]], check=True)
    return fixture.read_bytes()


def expected_panel(regs, count, state, values):
    topic = "SAMPLED" if state == "ROUTE" else regs[count - 1][1]
    lines = [("UFS " + state).ljust(14) + topic, "", "", "", "", "", "UFS SID UNKNOWN", "FD BUS UNKNOWN"]
    for i in range(count - (state == "FAULT")):
        row, column = 1 + i // 2, (i % 2) * 15
        lines[row] = lines[row].ljust(column) + f"{regs[i][1]:4}{values[i]:08X}"
    return lines


if __name__ == "__main__":
    run_panel_suite(guid=GUID, regs=REGS, cases=CASES, panel=expected_panel,
                    outcome="PASS-QEMU-ROUTE-VIEW", make_tree=tree_for_case)
