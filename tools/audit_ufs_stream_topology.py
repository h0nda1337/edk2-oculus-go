"""Resolve interconnect and IOMMU phandles in the pinned Pacific runtime tree.
The report contains aggregate binding counts and hardware metadata only.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from audit_ufs_bus_pages import ANOC2, DT_SHA, UFS, sha


BUS = "/soc/ad-hoc-bus/"
MASTER = BUS + "mas-ufs"
SLAVE = BUS + "slv-a2noc-snoc"


def cells(data):
    return tuple(word[0] for word in struct.iter_unpack(">I", data))


def check(condition, message):
    if not condition:
        raise ValueError(message)


def read_tree(image, *, expected_sha=DT_SHA):
    check(sha(image) == expected_sha, "unsupported FDT digest")
    magic, total, start, strings_at, _, version, _, _, names_len, struct_len = struct.unpack_from(">10I", image)
    check(magic == 0xd00dfeed and total == len(image) and version == 17 and
          start + struct_len <= strings_at <= total - names_len, "invalid FDT sections")
    tokens = image[start:start + struct_len]
    names = image[strings_at:strings_at + names_len]
    nodes, stack = {}, []
    offset = 0
    while offset < len(tokens):
        token, = struct.unpack_from(">I", tokens, offset)
        offset += 4
        if token == 1:  # BEGIN_NODE, padded C string
            end = tokens.index(0, offset)
            name = tokens[offset:end].decode("ascii")
            path = stack[-1].rstrip("/") + "/" + name if stack else "/"
            check(path not in nodes, "duplicate node")
            nodes[path] = {}
            stack.append(path)
            offset = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, key = struct.unpack_from(">II", tokens, offset)
            offset += 8
            prop = names[key:names.index(0, key)].decode("ascii")
            node = nodes[stack[-1]]
            check(prop not in node and length <= len(tokens) - offset, "invalid FDT property")
            node[prop] = tokens[offset:offset + length]
            offset = (offset + length + 3) & ~3
        elif token == 9 and not stack and offset == len(tokens):
            return nodes
        elif token != 4:  # NOP
            raise ValueError("unexpected FDT structure token")
    raise ValueError("unterminated FDT structure")


def audit(dt):
    nodes = read_tree(dt.read_bytes())
    handles = {}
    for path, props in nodes.items():
        ids = {cells(props[k]) for k in ("phandle", "linux,phandle") if k in props}
        if ids:
            check(len(ids) == 1, "conflicting phandles")
            handle, = ids.pop()
            check(handle not in (0, 0xffffffff) and handle not in handles, "invalid phandle")
            handles[handle] = path

    providers = Counter()
    consumers = set()
    for path, props in nodes.items():
        if "iommus" not in props:
            continue
        refs = cells(props["iommus"])
        i = 0
        while i < len(refs):
            provider = handles[refs[i]]
            arity, = cells(nodes[provider]["#iommu-cells"])
            check(arity <= len(refs) - i - 1, "incomplete IOMMU specifier")
            providers[provider] += 1
            consumers.add(path)
            i += 1 + arity
    check((len(nodes), len(consumers), sum(providers.values()), len(providers)) == (1867, 29, 71, 9),
          "unexpected coverage of pinned runtime tree")
    def follow(path, prop):
        return [handles[id_] for id_ in cells(nodes[path][prop])]

    paths = {
        "masterFabric": follow(MASTER, "qcom,bus-dev"),
        "masterConnections": follow(MASTER, "qcom,connections"),
        "bridgeFabric": follow(SLAVE, "qcom,bus-dev"),
        "bridgeConnections": follow(SLAVE, "qcom,connections"),
    }
    check(paths == {"masterFabric": [BUS + "fab-a2noc"], "masterConnections": [SLAVE],
                    "bridgeFabric": [BUS + "fab-snoc"], "bridgeConnections": [BUS + "mas-a2noc-snoc"]},
          "unexpected interconnect graph")
    fabric_ids = {k: list(cells(nodes[MASTER][k])) for k in ("cell-id", "qcom,qport", "qcom,mas-rpm-id")}
    anoc = nodes[ANOC2]
    other_routes = ("mmu-masters", "iommu-map", "iommu-map-mask", "dma-ranges")
    route_counts = {key: sum(key in props for props in nodes.values()) for key in other_routes}
    binding_names = ("iommus", *other_routes)
    bindings = {p: [n for n in binding_names if n in nodes[p]] for p in ("/", "/soc", UFS)}
    check(UFS not in consumers and ANOC2 not in providers and not any(bindings.values()),
          "unexpected DMA binding")
    flags = {k: k in anoc for k in ("qcom,register-save", "qcom,skip-init", "phandle", "linux,phandle")}
    return {
        "source": "archived Pacific /sys/firmware/fdt at Android runtime",
        "runtimeFdtSha256": DT_SHA, "nodes": len(nodes), "iommuConsumerNodes": len(consumers),
        "iommuReferences": providers.total(), "referencedProviders": dict(sorted(providers.items())),
        "otherRoutePropertyNodeCounts": route_counts, "ufsAncestorBindingsPresent": bindings, "master": MASTER, "interconnectIds": fabric_ids,
        "interconnectEdges": paths,
        "anoc2": {"node": ANOC2, "status": anoc["status"].rstrip(b"\0").decode("ascii"),
                  "compatible": anoc["compatible"].rstrip(b"\0").decode("ascii"),
                  "reg": [hex(v) for v in cells(anoc["reg"])], "iommuCells": cells(anoc["#iommu-cells"])[0],
                  "flags": flags, "iommuReferences": providers[ANOC2]},
        "physicalUfsStreamIdAfterLk": "UNKNOWN", "physicalBusForPage80441000": "UNKNOWN",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-fdt", type=Path, required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.runtime_fdt)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    print(report["nodes"], "nodes,", report["iommuReferences"], "IOMMU references")


if __name__ == "__main__":
    main()
