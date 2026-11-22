"""Measure DMA addresses returned by the EFI UFS host controller in AAVMF.
Only the ESP is bootable. The UFS LUN is a read-only, content-free capacity fixture.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ufs_splash_qemu import EFI, digest
from ufs_data_qemu import CAPACITY, LUN_BYTES, unit_args
from ufs_nop11_bus import PAGE, WINDOW

def run(tmp, size, owned=False):
    firmware = Path("/usr/share/AAVMF/AAVMF_CODE.fd")
    nvram = tmp / "vars.fd"
    shutil.copyfile("/usr/share/AAVMF/AAVMF_VARS.fd", nvram)
    esp = tmp / "esp"
    boot = esp / "EFI/BOOT"
    boot.mkdir(parents=True)
    app = "UfsOwnedPage.efi" if owned else "UfsCapacityMap.efi"
    modules = {app:boot/"BOOTAA64.EFI",
               "UfsPciHcDxe.efi":esp/"UfsPciHcDxe.efi", "UfsPassThruDxe.efi":esp/"UfsPassThruDxe.efi"}
    for name, dest in modules.items():
        shutil.copyfile(EFI/name, dest)
    events, trace = tmp/"events", tmp/"trace"
    forbidden = ("scsi_disk_dma_command_READ", "scsi_disk_dma_command_WRITE")
    events.write_text("\n".join(("ufs_exec_scsi_cmd", *forbidden))+"\n")
    cmd = ["qemu-system-aarch64", "-machine","virt", "-cpu","cortex-a57", "-m","1536M",
           "-nodefaults","-display","none","-serial","stdio","-monitor","none","-no-reboot",
           "-drive",f"if=pflash,format=raw,readonly=on,file={firmware}",
           "-drive",f"if=pflash,format=raw,file={nvram}",
           "-drive",f"if=none,id=esp,format=raw,readonly=on,file=fat:ro:{esp}",
           "-device","virtio-blk-pci,drive=esp,bootindex=1",
           "-device","ufs,mcq=off", *unit_args(size), "-trace",f"events={events},file={trace}"]
    result = subprocess.run(cmd, capture_output=True, timeout=90, check=True)
    log = result.stdout.decode(errors="replace")
    commands = trace.read_text().splitlines()
    allowed = re.compile(r"ufs_exec_scsi_cmd slot [0-9]+, lun 0x4, opcode 0x25")
    if not all(allowed.fullmatch(c) for c in commands):
        raise ValueError(f"unexpected UFS or disk access: {commands}")
    rows = [dict(page=int(p),cpu=hex(int(host,16)),bus=hex(int(bus,16)),payload=raw.lower())
            for p,host,bus,raw in re.findall(r"UFS-MAP PAGE (\d+) CPU ([0-9A-Fa-f]+) BUS ([0-9A-Fa-f]+) DATA ([0-9a-fA-F]{16})",log)]
    positive = size == LUN_BYTES
    expected = "Success" if positive else "Volume Corrupt"
    offsets = [PAGE, 2*PAGE-8] if owned else [i*PAGE for i in range(4)]
    if f"UFS-MAP RESULT {expected}" not in log or len(rows)!=(len(offsets) if positive else 0):
        raise RuntimeError(f"unexpected terminal result, commands={commands}: {log[-1400:]}")
    if positive and owned:
        counts = re.findall(r"UFS-MAP TAIL REFUSED MAPPED (\d+)", log)
        if counts != [str(len(commands))]:
            raise ValueError("SCSI trace differs from accepted maps or missing tail refusal")
    if not (len(rows)+(1 if not positive else 0) <= len(commands) <= (len(offsets)+1 if positive else 2)):
        raise ValueError(f"unexpected transfer count: {commands}")
    if positive:
        if [(row['page'],row['cpu'],row['payload']) for row in rows] != [
                (offset//PAGE,hex(WINDOW+offset),CAPACITY.hex()) for offset in offsets]:
            raise ValueError(rows)
    return dict(provider="EDKII_UFS_HOST_CONTROLLER_PROTOCOL.Map / EFI_PCI_IO_PROTOCOL.Map",
                firmwareSha256=digest(firmware),efiSha256={name:digest(dest) for name,dest in modules.items()},
                lun=4,lunBytes=size,logicalBlockBytes=PAGE,rows=rows,readCapacityCommands=len(commands),
                ufsMediaReads=0,ufsMediaWrites=0,terminal=expected,
                **({"tailMappingRefusalVerified":positive} if owned else {}))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report",required=True,type=Path)
    ap.add_argument("--owned-page", action="store_true", help="reserve the guarded page and sample both ends")
    args=ap.parse_args()
    results={}
    with tempfile.TemporaryDirectory() as folder:
        for name,size in (("matched",LUN_BYTES),("different-last-lba",LUN_BYTES-PAGE)):
            tmp=Path(folder)/name
            tmp.mkdir()
            results[name]=run(tmp,size,args.owned_page)
            print(name,results[name]["rows"],results[name]["terminal"],flush=True)
    report=dict(outcome="PASS-QEMU-UEFI-MAP",qemu=subprocess.check_output(
        ["qemu-system-aarch64","--version"],text=True).splitlines()[0], results=results,
        physicalPacificBusPages=["UNKNOWN"]*4)
    if args.owned_page:
        report.update(outcome="PASS-QEMU-OWNED-PAGE", pageCpu=hex(WINDOW+PAGE), pageBytes=PAGE,
                      endpointOffsets=[0,PAGE-8], pacificDirectBus="UNKNOWN")
    args.report.write_text(json.dumps(report,indent=2)+"\n")

if __name__=="__main__":
    main()
