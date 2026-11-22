"""Correlate one emulated UFS device's firmware route with DMA to its owned page.
Only QEMU virt PCI root complexes with a direct SMMUv3 or ITS mapping are in scope.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from ufs_capacity_map_qemu import run
from ufs_data_qemu import LUN_BYTES


def need(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def pci_route(table, segment, rid):
    need(48 <= len(table) <= 16384 and table[:4] == b"IORT", "invalid IORT header")
    need(struct.unpack_from("<I", table, 4)[0] == len(table) and sum(table) % 256 == 0,
         "IORT length/checksum mismatch")
    count, offset = struct.unpack_from("<II", table, 36)
    need(48 <= offset <= len(table) and 0 < count <= (len(table)-offset)//16, "invalid node array")
    nodes = {}
    matches = []
    for _ in range(count):
        need(offset + 16 <= len(table), "short IORT node")
        kind, length, revision, identifier, nmap, maps = struct.unpack_from("<BHBIII", table, offset)
        node = table[offset:offset+length]
        need(length >= 16 and len(node) == length, "invalid IORT node length")
        nodes[offset] = (kind, identifier)
        if kind == 2:  # PCI root complex. Segment lives at byte 28.
            need(length >= 36 and revision == 3, "unsupported QEMU root complex")
            need(nmap and 36 <= maps and maps + nmap*20 <= length, "invalid RC mapping array")
            if struct.unpack_from("<I", node, 28)[0] == segment:
                for index in range(nmap):
                    first, span, out, ref, flags = struct.unpack_from("<5I", node, maps + index*20)
                    need(flags == 0 and max(first, out) + span <= 0xffffffff, "unsupported RC mapping")
                    if first <= rid <= first + span:  # NumIds encodes range length minus one.
                        matches.append((ref, first, first + span, out))
        offset += length
    need(offset == len(table) and len(matches) == 1, "UFS PCI requester lacks a unique mapping")
    ref, first, last, out = matches[0]
    need(ref in nodes, "IORT mapping references an absent node")
    kind, identifier = nodes[ref]
    need(kind in (0, 4), "unexpected QEMU IORT destination")
    return {"target": "SMMUv3" if kind == 4 else "ITS", "nodeIdentifier": identifier,
            "firstRequesterId": first, "lastRequesterId": last, "outputBase": out,
            "targetNodeOffset": ref, "sid": out + (rid - first) if kind == 4 else None}


def from_guest(log, slot):
    locations = re.findall(r"^UFS-ROUTE PCI (\d+) (\d+) (\d+) (\d+)$", log, re.M)
    need(len(locations) == 1, "missing or duplicate controller handle location")
    segment, bus, device, function = map(int, locations[0])
    need((segment, bus, device, function) == (0, 0, slot, 0), "wrong UFS PCI handle")
    rid = (bus << 8) | (device << 3) | function
    table = bytearray()
    for addr, raw in re.findall(r"^UFS-ROUTE IORT ([\da-fA-F]+) ([\da-fA-F]+)$", log, re.M):
        need(int(addr, 16) == len(table), "gap or overlap in IORT serial output")
        table.extend(bytes.fromhex(raw))
    if not table:
        need(log.splitlines().count("UFS-ROUTE NO IORT") == 1 and "UFS-ROUTE END" not in log,
             "guest did not report an absent IORT")
        return rid, {"target": "NO-IORT", "sid": None}
    need(log.splitlines().count("UFS-ROUTE END") == 1 and "UFS-ROUTE NO IORT" not in log,
         "incomplete or conflicting IORT serial output")
    route = pci_route(table, segment, rid)
    route["iortSha256"] = hashlib.sha256(table).hexdigest()
    return rid, route


def check_observations(trace, rows, route):
    # In these AAVMF fixtures the provider supplies an identity bus mapping.
    # Count the emulator's UFS endpoint events only within the corresponding SCSI request.
    # is_write in QEMU's disable/bypass events is a bool converted from a permission bitmask.
    # It is not a reliable direction field. Direction/data are checked by the EFI app.
    starts = [i for i, line in enumerate(trace) if line.startswith("ufs_exec_scsi_cmd ")]
    need(len(starts) in (2, 3), "unexpected count of endpoint commands")
    endpoint_commands = starts[-2:] + [len(trace)]
    results = []
    for idx, row in enumerate(rows):
        address = int(row["bus"], 16)
        need(address == int(row["cpu"], 16), "unexpected provider mapping in identity fixture")
        events = trace[endpoint_commands[idx]+1:endpoint_commands[idx+1]]
        found = []
        for line in events:
            if line.startswith("smmuv3_translate_success "):
                translated = re.search(r" iova=(0x[0-9a-f]+) ", line)
                need(translated and int(translated[1], 16) != address, "unexpected active translation for endpoint")
            match = re.fullmatch(r"smmuv3_translate_(disable|bypass) \S+ sid=0x([0-9a-f]+) "
                                 r"(?:bypass \(smmu disabled\)|STE bypass) iova:0x([0-9a-f]+) is_write=\d+", line)
            if match and int(match[3], 16) == address:
                found.append((match[1], int(match[2], 16)))
        if route["target"] == "SMMUv3":
            need(found and {val[1] for val in found} == {route["sid"]},
                 f"IORT SID and observed UFS endpoint differ for {row}: {found}")
            need(len({mode for mode, _ in found}) == 1, "inconsistent emulator routing")
            results.append({**row, "traceSid": found[0][1], "traceMode": found[0][0]})
        else:
            need(not any(line.startswith("smmuv3_translate_") for line in events),
                 "unexpected SMMU event for unadvertised route")
            results.append(row)
    return results


def exercise(folder, name, slot, machine, target):
    folder.mkdir()
    result = run(folder, LUN_BYTES, True, machine=machine, route_slot=slot)
    rid, route = from_guest((folder/"route-serial.log").read_text(), slot)
    need(route["target"] == target, f"unexpected {name} firmware route: {route}")
    trace = (folder/"trace").read_text().splitlines()
    rows = check_observations(trace, result["rows"], route)
    return {"name": name, "machine": machine, "uefiPciLocation": f"0000:00:{slot:02x}.0",
            "requesterId": rid, "firmwareRoute": route, "endpoints": rows,
            "readCapacityCommands": result["readCapacityCommands"], "ufsMediaReads": result["ufsMediaReads"],
            "ufsMediaWrites": result["ufsMediaWrites"], "tailRefusal": result["tailMappingRefusalVerified"],
            "efiSha256": result["efiSha256"], "firmwareSha256": result["firmwareSha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    base = "virt,acpi=on,gic-version=3,its=on"
    fixtures = [("slot-three", 3, base+",iommu=smmuv3", "SMMUv3"),
                ("slot-five", 5, base+",iommu=smmuv3", "SMMUv3"),
                ("only-its", 3, base, "ITS"),
                ("no-iort", 3, "virt-2.7,acpi=on,gic-version=2", "NO-IORT")]
    with tempfile.TemporaryDirectory() as directory:
        results = []
        for name, slot, machine, target in fixtures:
            result = exercise(Path(directory)/name, name, slot, machine, target)
            results.append(result)
            print(name, result["firmwareRoute"], result["endpoints"], flush=True)
    need(results[0]["firmwareRoute"]["sid"] != results[1]["firmwareRoute"]["sid"],
         "relocating the virtual UFS left the attributed SID unchanged")
    output = {"outcome": "PASS-QEMU-UFS-IORT", "qemu": subprocess.check_output(
        ["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
        "readOnlyLun": 4, "lunBytes": LUN_BYTES, "cases": results,
        "pacificUfsSidAfterLk": "UNKNOWN", "pacificSecPageBusAfterLk": "UNKNOWN"}
    args.report.write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
