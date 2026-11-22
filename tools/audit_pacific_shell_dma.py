"""Audit stock boot trees for a device-owned DMA pool and compare with the Shell allocator."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

from android_boot import DTB_SHA, HEADER, PAGE
from audit_lk_prdt import inspect as inspect_prdt
from audit_lk_response_heap import inspect as inspect_heap
from audit_lk_ufs_dma import audit as inspect_lk
from audit_ufs_bus_pages import DT_SHA, UFS
from audit_ufs_stream_topology import cells, check, read_tree
from verify_fd import verify

EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence"
CNC_SHA = "123a7f5d1f2c8dc7f9ada0ef10233f0cf6ea9cbba14089423b5b17d8e1f6dbe3"
POOL = "/reserved-memory/oculus_dma_region"


def evidence(name):
    return json.loads((EVIDENCE / name).read_bytes())


def boot_trees(img, known_hash):
    check(hashlib.sha256(img).hexdigest() == known_hash, "boot partition digest mismatch")
    header = HEADER.unpack_from(img)
    check(header[0] == b"ANDROID!" and header[8] == PAGE and header[9] == 0, "unknown boot format")
    kernel_bytes = header[1]
    inflater = zlib.decompressobj(31)
    inflater.decompress(img[PAGE:PAGE + kernel_bytes])
    check(inflater.eof, "incomplete gzip kernel")
    trailer = inflater.unused_data
    offset = 0
    trees = {}
    for expected in (CNC_SHA, DTB_SHA):
        size, = struct.unpack_from(">I", trailer, offset + 4)
        blob = trailer[offset:offset + size]
        check(hashlib.sha256(blob).hexdigest() == expected, "different appended tree")
        trees[expected] = (PAGE + kernel_bytes - len(trailer) + offset, blob)
        offset += size
    check(offset == len(trailer), "unaccounted kernel trailer data")
    return trees


def tree_evidence(blob, expected_hash, arena):
    nodes = read_tree(blob, expected_sha=expected_hash)
    reserved = {path: props for path, props in nodes.items() if path.startswith("/reserved-memory/")}
    bus = nodes["/reserved-memory"]
    check(cells(bus["#address-cells"]) == cells(bus["#size-cells"]) == (2,) and bus["ranges"] == b"",
          "unexpected reserved-memory address format")
    fixed = []
    dynamic = []
    for path, props in reserved.items():
        if "reg" in props:
            for start, length in struct.iter_unpack(">QQ", props["reg"]):
                fixed.append((path, start, length))
        elif "size" in props:
            dynamic.append(path)
        else:
            raise ValueError("unclassified reservation")
    pool = reserved[POOL]
    check(pool["phandle"] == pool["linux,phandle"] and len(pool["phandle"]) == 4, "invalid pool handle")
    phandle, = cells(pool["phandle"])
    bindings = ("memory-region", "linux,contiguous-region")
    consumers = []
    for path, props in nodes.items():
        for name in bindings:
            if name in props and phandle in cells(props[name]):
                consumers.append({"node": path, "property": name})
    check(consumers == [{"node": "/soc/qcom,ion/qcom,ion-heap@30", "property": "memory-region"}],
          "unexpected Oculus pool consumer")
    ion = nodes[consumers[0]["node"]]
    check(cells(ion["reg"]) == (30,) and ion["qcom,ion-heap-type"] == b"DMA\0", "different ION heap")
    check(pool["compatible"] == b"shared-dma-pool\0" and "reg" not in pool, "different pool type")
    length, = struct.unpack(">Q", pool["size"])
    align, = struct.unpack(">Q", pool["alignment"])
    lo, span = struct.unpack(">QQ", pool["alloc-ranges"])
    keys = (*bindings, "iommus", "iommu-map", "dma-ranges")
    return {
        "model": nodes["/"]["model"].rstrip(b"\0").decode("ascii"), "sha256": expected_hash,
        "fixedRegRanges": len(fixed), "dynamicSizeReservations": len(dynamic),
        "fixedRegOverlapsWithShellArena": [p for p, start, size in fixed
                                          if start < arena[1] and arena[0] < start + size],
        "addressPropertiesOnUfsPath": {
            path: {key: list(cells(nodes[path][key])) for key in ("ranges", "dma-ranges") if key in nodes[path]}
            for path in ("/", "/soc", UFS)
        },
        "ufsDeviceAndDescendantBindings": {
            path: [key for key in keys if key in props]
            for path, props in nodes.items() if path == UFS or path.startswith(UFS + "/")
        },
        "oculusDmaRegion": {"node": POOL, "sizeBytes": length, "alignmentBytes": align,
                            "allocRangesBaseAndSize": [hex(lo), hex(span)], "hasReg": False,
                            "regionConsumers": consumers, "ionHeapId": 30}
    }


def audit(backups, runtime_fdt, normal_build):
    partitions = {p["name"]: p["sha256"] for p in evidence("partitions.json")["partitions"]}
    fd = (normal_build / "OCULUS_GO_DIRECT.fd").read_bytes()
    normal_hash = verify(fd)["sha256"]
    normal = evidence("ufs-platform-normal-qemu-20261122.json")
    check(normal_hash == normal["fdSha256"], "expected the reviewed NORMAL FD")
    report = (normal_build / "BUILD_REPORT.txt").read_text(encoding="utf-8")
    def pcd(name):
        entries = re.findall(rf"^\s*\*[A-Z] {name}\s+:\s+FIXED\s+\(UINT(?:32|64)\) = (0x[\da-fA-F]+)",
                             report, re.MULTILINE)
        check(len(set(entries)) == 1, "missing or inconsistent build PCD " + name)
        return int(entries[0], 16)
    start = pcd("PcdMemoryPoolBase")
    arena = (start, start + pcd("PcdMemoryPoolSize"))
    check(arena[1] == pcd("PcdFdBaseAddress") + len(fd), "unexpected normal arena layout")

    readouts = {}
    inputs = {}
    for name in ("boot_a", "boot_b"):
        trees = boot_trees((backups / (name + ".img")).read_bytes(), partitions[name])
        inputs[name] = {"sha256": partitions[name], "treeFileOffsets": {key: hex(pair[0]) for key, pair in trees.items()}}
        for key, (_, blob) in trees.items():
            if key not in readouts:
                readouts[key] = tree_evidence(blob, key, arena)
    readouts[DT_SHA] = tree_evidence(runtime_fdt.read_bytes(), DT_SHA, arena)

    lk = (backups / "aboot_a.img").read_bytes()
    replays = {
        "ufs-lk-dma-stock-20261121.json": inspect_lk(lk),
        "ufs-response-heap-stock-20261121.json": inspect_heap(lk),
        "ufs-native-prdt-stock-20261121.json": inspect_prdt(backups),
    }
    for name, replay in replays.items():
        check(replay == evidence(name), "stock audit disagreement: " + name)
    capacity = evidence("ufs-data-transfer-20261121.json")
    data = capacity["lkDataIn"]
    address = int(data["controlDataAddressFromReviewedFirmware"], 16)
    n = data["transferBytes"]
    return {
        "scope": "Offline stock partitions, archived running DT, published physical observations and NORMAL build",
        "bootPartitions": inputs, "treeObservations": list(readouts.values()),
        "stockLkAuditsReproduced": list(replays), "stockLkSha256": hashlib.sha256(lk).hexdigest(),
        "normalFdSha256": normal_hash, "normalCpuArenaExclusive": [hex(a) for a in arena],
        "previousPhysicalTransfer": {
            "reference": "ufs-data-transfer-20261121.json", "lun": capacity["capacity"]["lun"],
            "lkBufferBusRangeExclusive": [hex(address), hex(address + n)], "bytes": n,
            "intersectsNormalCpuArenaNumerically": address < arena[1] and arena[0] < address + n,
            "fdPagesTested": capacity["physicalFdPagesTested"],
        },
        "physicalShellCpuPageThisBoot": "UNKNOWN",
        "physicalShellUfsBusAddressThisBoot": "UNKNOWN",
        "newPhysicalOperation": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-directory", type=Path, required=True)
    parser.add_argument("--runtime-fdt", type=Path, required=True)
    parser.add_argument("--normal-build", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        inputs = [*args.backup_directory.glob("*.img"), args.runtime_fdt,
                  args.normal_build / "OCULUS_GO_DIRECT.fd", args.normal_build / "BUILD_REPORT.txt"]
        if any(p.is_file() and args.report.samefile(p) for p in inputs):
            parser.error("The report must be separate from the firmware and build inputs")
    result = audit(args.backup_directory, args.runtime_fdt, args.normal_build)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
