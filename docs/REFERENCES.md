# Allowed sources and evidence

| Origin | Revision / file | Use | Confidence |
| --- | --- | --- | --- |
| https://github.com/tianocore/edk2 | `e7aac7fc137e247edad22f7ee53b9a1fba227397` | PI HOB/FV/DXE implementation; ARM CPU/MMU/GIC/timer libraries; build rules | Upstream code, pinned |
| Same | `ArmVirtPkg/ArmVirtQemuKernel.fdf`, `ArmVirtRules.fdf.inc` | Integrated Linux-header/FV structure and standard FFS rules | Structural reference; QEMU addresses not imported |
| Same | `BaseTools/Source/C/GenFv/GenFvInternalLib.c`, `UpdateArmResetVectorIfNeeded` | In-place AArch64 FV reset-vector generation | Source-verified |
| [TianoCore EDK2 graphics protocol](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Include/Protocol/GraphicsOutput.h) | `e7aac7fc137e247edad22f7ee53b9a1fba227397`, `MdePkg/Include/Protocol/GraphicsOutput.h` | GOP mode, BLT operation and pixel interfaces for the original model driver | CONFIRMED-SOURCE |
| [Terminal SEC physical record](evidence/sec-visual-transfer-20261118.json) | Firmware/test revision `907be1e5fd53001cdf298f9a6b1ae6d1b07a6521` | Device-reported boot state, owner-observed SEC colors, pre/post Android readback hashes | CONFIRMED for this trial, red/blue channel order UNKNOWN |
| TianoCore EDK2 | `e7aac7fc137e247edad22f7ee53b9a1fba227397`, `ArmPlatformPkg/PrePi/PrePi.c`, `EmbeddedPkg/Library/PrePiLib` | Public PI interfaces and direct-to-DXE sequence | Source-verified. New board SEC authored independently |
| [SEC C review](evidence/sec-c-review-20261118.json) | Project platform `514a09208b07db901b4551227a9d5297ba8dce3f`, `OculusGoPkg/PrePi/Entry.S` and `SecMain.c` | In-image stack, direct C call and placement of the red/blue markers. Static and model report hashes pin the reviewed binary | CONFIRMED in the ELF/FD and QEMU |
| [SEC C physical record](evidence/sec-c-transfer-20261118.json) | Reviewed image SHA-256 `3cd2cbfd824ca726029e8810abbfb12a90f5b1653155c972a109a68ccc5d5055` | Owner saw red–black–red and blue–white–blue. First pixel byte blue, third red in the inherited framebuffer | CONFIRMED-DEVICE for the C drawing after the stack check. Compatible with BGR. Physical scan direction UNKNOWN |
| [Upstream PI HOB constructor](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/EmbeddedPkg/Library/PrePiHobLib/Hob.c) | `e7aac7fc137e247edad22f7ee53b9a1fba227397`, `HobConstructor`, BSD-2-Clause-Patent | SEC_MEM calls the unmodified library in the image's scratch arena and checks the PHIT and end marker | CONFIRMED in the linked diagnostic and QEMU |
| [Runtime and stock memory evidence](MEMORY_MAP.md) | Runtime DTB SHA-256 `0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929`, stock EVT DTB SHA-256 `70ae171c99befc564acec661f3afc4365a831ebd1d6e01ca0e53035a4d8b1f35`, `/memory/reg` and `/reserved-memory` | Bounded input checks in the original SEC_MEM reader. The two sample addresses come from the platform's normal HOB base and first stack record | CONFIRMED for the captures. Memory ownership at handoff remains UNKNOWN |
| https://github.com/facebookincubator/oculus-linux-kernel | `9475755c1a328a7b873721897ef339a8ad35c86a`, `Documentation/arm64/booting.txt` | Image header fields, EL1/EL2 entry, MMU off, instruction cache may be enabled | Official Go kernel documentation |
| Owner GitHub | Authenticated login `h0nda1337`, 2026-10-22 | Establish permitted repository owner | CONFIRMED via connector and local CLI |
| Own device capture | Original `aboot_a`, SHA-256 `6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74` | ARM64 destination and FDT destination; evidence only, binary not linked/uploaded | Static binary evidence |
| Own device capture | Runtime DT and `/proc/iomem`, captured 2026-08-24 | RAM, reserved regions, GIC and timer | CONFIRMED-DEVICE for capture; new handoff state UNKNOWN |

No user-repository source or external driver has been imported. Any future
import must extend `sources.lock.json` and this document with file/license/
changes. A repository appearing under the user's account is not sufficient
evidence that a driver matches this hardware.

## Local reconstruction evidence, verified 2026-10-25

| Record | Revision / hash | Information | Confidence |
| --- | --- | --- | --- |
| New firmware sources | Own commit `68f8264358cb81a1de1f27f8c01c37443e578dd9`, `OculusGoPkg/` | Independently authored SEC, memory handoff and TrustMeBro with only EDK2 libraries | CONFIRMED-SOURCE |
| Validation tools | Own commit `e35e5479f8561d4e2f34cc7e0a1bc07c93dc3538` | Original container writer, tracked-source audit, QEMU entry/SEC/DXE tests | CONFIRMED-LOCAL-TEST |
| `docs/evidence/source-audit-20261025.json` | SHA-256 `3a42da4b7946c678bf555ed91d306e1277d5b36a3e87fc56f42d946df2093704` | Compiler/link inputs, relative original paths and individual SHA-256 values; EDK2 clean/pinned/tracked checks; canonical LF publication from `db0abad4ec8b06fcfb3d89d2c468a3bec98e5cea` | CONFIRMED-BUILD-INPUTS |
| `docs/evidence/offline-validation-20261025.json` | FD SHA-256 `a4acf898e51a814ad6ed4c84a9dacd8788120ad272c3fa528fb0b7579b698230` | Artifact hashes, test scopes, local report hashes and hardware limits | CONFIRMED-BUILD / CONFIRMED-EMULATOR; physical UNKNOWN |
| `docs/evidence/partitions.json` | Source backup-manifest SHA-256 `12ee626968c09da21dc3e4465537962574b71abf1eca64960a865be9564eb12c` | All 50 original backup names, block paths, sizes and hashes; no binary contents | HISTORICAL-DEVICE-EVIDENCE; not a new rehash |
