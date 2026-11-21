"""Correlate Pacific snapshots offline. Emit only UFS metadata and the four page addresses.
Run under WSL with fdtget. SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zlib

from android_boot import STOCK_SHA, check_stock

ROOT = Path(__file__).resolve().parents[1]
DT_SHA = "0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929"
UFS = "/soc/ufshc@624000"
ANOC2 = "/soc/arm,smmu-anoc2@1680000"
WINDOW = 0x80440000
CONFIG_KEYS = ("IKCONFIG", "IKCONFIG_PROC", "ARM_SMMU", "ARM64_DMA_USE_IOMMU", "SWIOTLB",
               "DMA_API_DEBUG", "IOMMU_DEBUG_TRACKING", "IOMMU_TESTS", "SCSI_UFSHCD_PLATFORM",
               "SCSI_UFSHCD_PCI", "SCSI_UFS_QCOM")
def sha(data):
    return hashlib.sha256(data).hexdigest()

def audit(boot, dt, iomem):
    stock = boot.read_bytes()
    check_stock(stock)
    if sha(dt.read_bytes()) != DT_SHA:
        raise ValueError("different Pacific runtime device tree")
    size, = struct.unpack_from("<I",stock,8)
    page, = struct.unpack_from("<I",stock,36)
    image = zlib.decompress(stock[page:page+size],31)
    start = image.index(b"IKCFG_ST")+8
    end = image.index(b"IKCFG_ED",start)
    if image.count(b"IKCFG_ST") != 1 or image.count(b"IKCFG_ED") != 1:
        raise ValueError("ambiguous embedded configuration")
    cfg = zlib.decompress(image[start:end],31)
    opts = {}
    for key in CONFIG_KEYS:
        rows = re.findall(rf"^(?:CONFIG_{key}=(\w+)|(# CONFIG_{key} is not set))$",cfg.decode(),re.M)
        if len(rows)!=1:
            raise ValueError(f"unknown config state: {key}")
        opts[key] = rows[0][0] or "n"
    def prop(node, key, kind="s"):
        return subprocess.check_output(["fdtget","-t",kind,dt,node,key],text=True).split()
    def fields(node):
        return set(subprocess.check_output(["fdtget","-p",dt,node],text=True).split())
    paths = ("/","/soc",UFS)
    props = {node:fields(node) for node in paths}
    mapping_keys = ("iommus","iommu-map","dma-ranges")
    interested = {node:{key:key in attrs for key in mapping_keys} for node,attrs in props.items()}
    vectors = [int(t,16) for t in prop(UFS,"qcom,msm-bus,vectors-KBps","x")]
    cases = int(prop(UFS,"qcom,msm-bus,num-cases","u")[0])
    count = int(prop(UFS,"qcom,msm-bus,num-paths","u")[0])
    if cases*count*4 != len(vectors):
        raise ValueError("malformed bandwidth votes")
    edges = sorted({(vectors[i],vectors[i+1]) for i in range(0,len(vectors),4)})
    code = re.findall(r"^\s*([\da-fA-F]+)-([\da-fA-F]+)\s*:\s*Kernel code\s*$",
                      iomem.read_text(encoding="utf-8-sig"),re.M)
    if len(code)!=1:
        raise ValueError("missing or ambiguous Android kernel code region")
    lower, upper = (int(v,16) for v in code[0])
    captured = json.loads((ROOT/"docs/evidence/ufs-lk-map-transfer-20261121.json").read_bytes())
    block = captured["physicalPanel"]["retainedCpuBlocks"]["FD"]
    low = int(block["cpuBlockStart"],16)
    high = int(block["cpuBlockEndExclusive"],16)
    pages=[]
    for p in range(4):
        addr=WINDOW+4096*p
        if not (lower<=addr<=addr+4095<=upper and low<=addr<addr+4096<=high):
            raise ValueError("window not within both witnessed CPU ranges")
        pages.append(dict(cpuBase=hex(addr),identityBusCandidate=hex(addr),physicalBus="UNKNOWN"))
    return dict(stockBootSha256=STOCK_SHA,embeddedConfigSha256=sha(cfg),config=opts,runtimeFdtSha256=DT_SHA,
                androidIomemSha256=sha(iomem.read_bytes()),androidKernelCodeInclusive=[hex(lower),hex(upper)],
                lkCpuDescriptor=block["descriptor"],ufsCompatible=prop(UFS,"compatible"),
                mappingProperties=interested,bandwidthMasterSlavePairs=edges,bandwidthCases=cases,
                anoc2=dict(node=ANOC2,compatible=prop(ANOC2,"compatible"),status=prop(ANOC2,"status"),
                           regCellsHex=prop(ANOC2,"reg","x"),clocks=prop(ANOC2,"clock-names"),
                           skipInit="qcom,skip-init" in fields(ANOC2)),
                pages=pages,physicalUfsStreamId="UNKNOWN",physicalTransfersIssued=0)

if __name__=="__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("boot","runtime-fdt","iomem","report"):
        ap.add_argument("--"+key,type=Path,required=True)
    args = ap.parse_args()
    result = audit(args.boot,args.runtime_fdt,args.iomem)
    args.report.write_text(json.dumps(result,indent=2)+"\n")
