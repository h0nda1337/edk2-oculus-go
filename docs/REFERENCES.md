# Allowed sources and evidence

| Origin | Revision / file | Use | Confidence |
| --- | --- | --- | --- |
| https://github.com/tianocore/edk2 | `e7aac7fc137e247edad22f7ee53b9a1fba227397` | PI HOB/FV/DXE implementation; ARM CPU/MMU/GIC/timer libraries; build rules | Upstream code, pinned |
| Same | `ArmVirtPkg/ArmVirtQemuKernel.fdf`, `ArmVirtRules.fdf.inc` | Integrated Linux-header/FV structure and standard FFS rules | Structural reference; QEMU addresses not imported |
| Same | `BaseTools/Source/C/GenFv/GenFvInternalLib.c`, `UpdateArmResetVectorIfNeeded` | In-place AArch64 FV reset-vector generation | Source-verified |
| Same | `ArmPlatformPkg/PrePi/PrePi.c`, `EmbeddedPkg/Library/PrePiLib` | Public PI interfaces and direct-to-DXE sequence | Source-verified; new board SEC authored independently |
| https://github.com/facebookincubator/oculus-linux-kernel | `9475755c1a328a7b873721897ef339a8ad35c86a`, `Documentation/arm64/booting.txt` | Image header fields, EL1/EL2 entry, MMU off, instruction cache may be enabled | Official Go kernel documentation |
| Owner GitHub | Authenticated login `h0nda1337`, 2026-10-22 | Establish permitted repository owner | CONFIRMED via connector and local CLI |
| Own device capture | Original `aboot_a`, SHA-256 `6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74` | ARM64 destination and FDT destination; evidence only, binary not linked/uploaded | Static binary evidence |
| Own device capture | Runtime DT and `/proc/iomem`, captured 2026-08-24 | RAM, reserved regions, GIC and timer | CONFIRMED-DEVICE for capture; new handoff state UNKNOWN |

No user-repository source or external driver has been imported. Any future
import must extend `sources.lock.json` and this document with file/license/
changes. A repository appearing under the user's account is not sufficient
evidence that a driver matches this hardware.
