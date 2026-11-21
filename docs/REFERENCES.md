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
| [SEC memory physical record](evidence/sec-mem-transfer-20261118.json) | SEC_MEM image SHA-256 `cdcc745e718ed53cb6542f20e4a438d445dc5a1b853ea878a2ce7ef39c848138` | Owner saw all five marker colors in order on the Go after the private PHIT check and the two loads | CONFIRMED-DEVICE for that SEC path. High RAM ownership and normal DXE remain unmeasured |
| https://github.com/facebookincubator/oculus-linux-kernel | `9475755c1a328a7b873721897ef339a8ad35c86a`, `Documentation/arm64/booting.txt` | Image header fields, EL1/EL2 entry, MMU off, instruction cache may be enabled | Official Go kernel documentation |
| Owner GitHub | Authenticated login `h0nda1337`, 2026-10-22 | Establish permitted repository owner | CONFIRMED via connector and local CLI |
| [Guarded stack measurement](SEC_STACK.md) | Project revision `52700ed`, `OculusGoPkg/OculusGoPkg.fdf`, `SecMem/StackEntry.S`, `SecMem/Stack.c` and `SecMem/Hob.c`; same pinned upstream PI constructor as SEC_MEM | FD-tail reservation, two address-dependent patterns, real PrePi record and nested C calls | CONFIRMED in the FD, QEMU and on this unit via the [physical checkpoint](evidence/sec-stack-transfer-20261118.json) |
| Own device capture | Original `aboot_a`, SHA-256 `6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74` | ARM64 destination and FDT destination; evidence only, binary not linked/uploaded | Static binary evidence |
| Own device capture | Runtime DT and `/proc/iomem`, captured 2026-08-24 | RAM, reserved regions, GIC and timer | CONFIRMED-DEVICE for capture; new handoff state UNKNOWN |

No user-repository source or external driver has been imported. Any future
import must extend `sources.lock.json` and this document with file/license/
changes. A repository appearing under the user's account is not sufficient
evidence that a driver matches this hardware.

## SEC_MMU sources

| Source | Revision and file | Contribution and confidence |
| --- | --- | --- |
| [Arm, Learn the Architecture, AArch64 memory management](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/LearnTheArchitecture-MemoryManagement-101811_0100_00_en.pdf) | 101811_0100_00, v1.0, sections on translation tables and translation control | Primary architectural reference for stage 1, SCTLR, TCR, TTBR and MAIR. CONFIRMED architecture |
| [TianoCore AArch64Mmu.h](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/ArmPkg/Include/Chipset/AArch64Mmu.h) | Pinned EDK2, BSD-2-Clause-Patent. Included unmodified by `OculusGoPkg/SecMmu/Tables.c` | Descriptor flags, attributes and permissions. CONFIRMED build input |
| [TianoCore ArmMmuLibCore](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/ArmPkg/Library/ArmMmuLib/AArch64/ArmMmuLibCore.c) | Same pin and license, `ArmConfigureMmu` | Reviewed EL2 TCR RES1 bits, EL1 TG1 with EPD1, output width and MAIR. Reference for the original terminal sequence. CONFIRMED source |
| [SEC_MMU evidence](evidence/sec-mmu-review-20261118.json) | Project `f39869d`, `OculusGoPkg/SecMmu/{Entry.S,Layout.h,Tables.c,Signal.c}` | Layout is derived from physical SEC_STACK and scanout evidence. Activation is CONFIRMED in QEMU and on this unit via the [red-center checkpoint](evidence/sec-mmu-transfer-20261118.json) |

## Local reconstruction evidence, verified 2026-10-25

| Record | Revision / hash | Information | Confidence |
| --- | --- | --- | --- |
| New firmware sources | Own commit `68f8264358cb81a1de1f27f8c01c37443e578dd9`, `OculusGoPkg/` | Independently authored SEC, memory handoff and TrustMeBro with only EDK2 libraries | CONFIRMED-SOURCE |
| Validation tools | Own commit `e35e5479f8561d4e2f34cc7e0a1bc07c93dc3538` | Original container writer, tracked-source audit, QEMU entry/SEC/DXE tests | CONFIRMED-LOCAL-TEST |
| `docs/evidence/source-audit-20261025.json` | SHA-256 `3a42da4b7946c678bf555ed91d306e1277d5b36a3e87fc56f42d946df2093704` | Compiler/link inputs, relative original paths and individual SHA-256 values; EDK2 clean/pinned/tracked checks; canonical LF publication from `db0abad4ec8b06fcfb3d89d2c468a3bec98e5cea` | CONFIRMED-BUILD-INPUTS |
| `docs/evidence/offline-validation-20261025.json` | FD SHA-256 `a4acf898e51a814ad6ed4c84a9dacd8788120ad272c3fa528fb0b7579b698230` | Artifact hashes, test scopes, local report hashes and hardware limits | CONFIRMED-BUILD / CONFIRMED-EMULATOR; physical UNKNOWN |
| `docs/evidence/partitions.json` | Source backup-manifest SHA-256 `12ee626968c09da21dc3e4465537962574b71abf1eca64960a865be9564eb12c` | All 50 original backup names, block paths, sizes and hashes; no binary contents | HISTORICAL-DEVICE-EVIDENCE; not a new rehash |

### SEC_DXE handoff

Pinned EDK2 revision `e7aac7fc137e247edad22f7ee53b9a1fba227397`. The build links upstream files directly under their original licenses. The checkpoint library, platform layout and host tests are original project source.

| File at pinned revision | Evidence | Confidence |
| --- | --- | --- |
| [PrePiHobLib/Hob.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/EmbeddedPkg/Library/PrePiHobLib/Hob.c) and [PrePiMemoryAllocationLib/MemoryAllocationLib.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/EmbeddedPkg/Library/PrePiMemoryAllocationLib/MemoryAllocationLib.c) | PHIT construction, end marker and descending page allocations | CONFIRMED-SOURCE |
| [PrePiLib/FwVol.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/EmbeddedPkg/Library/PrePiLib/FwVol.c) and [PrePiLib/PrePiLib.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/EmbeddedPkg/Library/PrePiLib/PrePiLib.c) | Section extraction, FV HOB and PE/COFF load and relocation | CONFIRMED-SOURCE |
| [DxeCoreEntryPoint.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Library/DxeCoreEntryPoint/DxeCoreEntryPoint.c) and [DxeMain.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/DxeMain/DxeMain.c) | DXE entry, setup of exception vectors, invocation of DebugAgentLib with the PHIT before memory services | CONFIRMED-SOURCE |
| [SEC_MMU physical observation](evidence/sec-mmu-transfer-20261118.json) and [current trial](SEC_DXE.md) | Prior MMU/scanout evidence and source of the diagnostic FD layout | Physical evidence for the prior profile only |

### DXE_MEM

Pinned TianoCore EDK2 commit `e7aac7fc137e247edad22f7ee53b9a1fba227397`. These files are compiled or inspected directly in the permitted upstream checkout. The platform resource test, terminal instrumentation and observer are original project code.

| Upstream source at the pinned commit | What it establishes | Confidence |
| --- | --- | --- |
| [Gcd/Gcd.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Gcd/Gcd.c) | CoreInitializeMemoryServices calls CoreInitializePool, requires tested RAM and considers the page-aligned free PHIT interval before publishing the first conventional descriptor | CONFIRMED-SOURCE |
| [DxeMain/DxeMain.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/DxeMain/DxeMain.c) | Initializer, runtime table allocations and order of the image-services call; Boot Services function table and its real page and pool operations | CONFIRMED-SOURCE |
| [Mem/Page.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Mem/Page.c) and [Mem/Pool.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Mem/Pool.c) | Page ownership transitions, memory-map stride/key and pool allocation/free behavior | CONFIRMED-SOURCE |
| [SEC_DXE on the Go](evidence/sec-dxe-transfer-20261119.json) | Preceding physical checkpoint, tested stack/framebuffer path and original hash comparison | CONFIRMED-DEVICE for SEC_DXE |

### DXE_GCD

| Source and revision | File or section | Contribution | Confidence |
| --- | --- | --- | --- |
| TianoCore EDK2 `e7aac7fc137e247edad22f7ee53b9a1fba227397` | [Image/Image.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Image/Image.c) | Core image handle and Loaded Image registration before GCD | CONFIRMED-SOURCE |
| Same upstream revision | [Gcd/Gcd.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Gcd/Gcd.c) and [DxeMain.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/DxeMain/DxeMain.c) | Order of initialization, resource ownership and HOB migration | CONFIRMED-SOURCE |
| Same upstream revision | [Dispatcher/Dispatcher.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Dispatcher/Dispatcher.c#L1306) | The dispatcher reads the core file GUID saved by Image.c from the original HOB page | CONFIRMED-SOURCE |
| UEFI Forum, UEFI 2.10 | [§9.1 EFI Loaded Image Protocol](https://uefi.org/specs/UEFI/2.10/09_Protocols_EFI_Loaded_Image.html) | Protocol identity, image address, size and memory types | CONFIRMED-SPEC |
| UEFI Forum, PI 1.8 Errata A, volume II | [§7.2 GCD services](https://uefi.org/specs/PI/1.8A/V2_Services_DXE_Services.html) | GCD address maps and resource types | CONFIRMED-SPEC |
| OculusGo_EDK2_UEFI, DXE_MEM | [Physical trial](evidence/dxe-mem-transfer-20261119.json) | Memory services in the bounded arena | CONFIRMED-DEVICE for DXE_MEM |

### DXE_TABLES

| Fuente y revisión | Archivo | Aportación | Confianza |
| --- | --- | --- | --- |
| UEFI Forum, UEFI 2.10 §4.6 | [EFI Configuration Table](https://uefi.org/specs/UEFI/2.10/04_EFI_System_Table.html#efi-configuration-table-properties-table) | Formato de las entradas y unicidad del GUID | CONFIRMED-SPEC |
| UEFI Forum, PI 1.8A, vol. II §7.2 | [Servicios GCD](https://uefi.org/specs/PI/1.8A/V2_Services_DXE_Services.html) | Consulta de un recurso por dirección, longitud, tipo y propietario | CONFIRMED-SPEC |
| TianoCore EDK2 `e7aac7fc137e247edad22f7ee53b9a1fba227397` | [DxeMain.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/DxeMain/DxeMain.c), [InstallConfigurationTable.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Misc/InstallConfigurationTable.c) | Orden de constructores y publicaciones, crecimiento de la tabla y estado inicial del servicio CRC32 | CONFIRMED-SOURCE |
| Misma revisión de TianoCore | [UefiLib.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Library/UefiLib/UefiLib.c), [DxeExtractGuidedSectionLib.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Library/DxeExtractGuidedSectionLib/DxeExtractGuidedSectionLib.c) | Consulta por GUID y asignaciones de los manejadores de secciones guiadas | CONFIRMED-SOURCE |
| Misma revisión de TianoCore | [MdePkg.dec](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/MdePkg.dec), [MdeModulePkg.dec](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/MdeModulePkg.dec) | Valores de los tres GUID que el observador decodifica de la RAM del invitado | CONFIRMED-SOURCE |
| Misma revisión de TianoCore | [DebugImageInfo.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Misc/DebugImageInfo.c) | El siguiente inicializador pide 1.025 páginas contiguas para obtener una estructura alineada a 4 MiB | CONFIRMED-SOURCE |
| OculusGo_EDK2_UEFI | [Prueba física anterior](evidence/dxe-gcd-transfer-20261119.json) | El visor alcanzó el retorno de los servicios de imagen y GCD con la arena de 1,5 MiB y la pila reservada | CONFIRMED-DEVICE para DXE_GCD |

### DXE_DEBUG

| Fuente y revisión | Archivo y aportación | Confianza |
| --- | --- | --- |
| UEFI Forum, UEFI 2.10 Errata A | [§18.4, EFI Debug Support Table](https://uefi.org/specs/UEFI/2.10_A/18_Protocols_Debugger_Support.html). Alineación del localizador, CRC32 de toda la estructura y recorrido por las entradas de depuración. | CONFIRMED-SPEC |
| TianoCore EDK2 `e7aac7fc137e247edad22f7ee53b9a1fba227397` | [DebugImageInfo.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Misc/DebugImageInfo.c), [DebugImageInfoTable.h](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Include/Guid/DebugImageInfoTable.h). Solicitud de 1.025 páginas, GUID, cabecera, indicador de actualización y registro de la imagen. | CONFIRMED-SOURCE |
| Misma revisión | [DxeMain.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/DxeMain/DxeMain.c), [Gcd.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Gcd/Gcd.c), [Page.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Mem/Page.c), [CheckSum.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Library/BaseLib/CheckSum.c). Orden de inicialización y servicios originales para admitir, asignar y verificar la página. Código enlazado sin cambios, bajo BSD-2-Clause-Patent. | CONFIRMED-SOURCE |
| OculusGo_EDK2_UEFI, DXE_TABLES | [Registro de la prueba](evidence/dxe-tables-transfer-20261119.json) y [mapa de memoria](MEMORY_MAP.md). Origen del FD y punto de partida en el visor. La página de depuración es una decisión del nuevo diseño. | CONFIRMED-DEVICE para DXE_TABLES |

### Renegade Windows driver packages

| Source and revision | File / contribution | Confidence |
| --- | --- | --- |
| edk2-porting/WOA-Drivers, `524346372da2091e905164841317f35c35947a82` | [components](https://github.com/edk2-porting/WOA-Drivers/tree/524346372da2091e905164841317f35c35947a82/components) groups the packages under AnySoC, MSM8998 and SDM845. | CONFIRMED-SOURCE for this revision |
| Same revision, Qualcomm INF | [QcXhciFilter8998.inf_](https://github.com/edk2-porting/WOA-Drivers/blob/524346372da2091e905164841317f35c35947a82/components/MSM8998/Platform/minimal/USB/XhciFilter/QcXhciFilter8998.inf_) declares an NTARM64 host filter for QCOM2430, includes usbxhci.inf and registers a lower filter. | CONFIRMED-SOURCE, Pacific compatibility UNKNOWN |
| Same revision, Qualcomm INF | [qcusbc8998.inf_](https://github.com/edk2-porting/WOA-Drivers/blob/524346372da2091e905164841317f35c35947a82/components/MSM8998/Platform/minimal/USB/USBC/qcusbc8998.inf_) declares an NTARM64 USB Type-C driver for QCOM00D5. | CONFIRMED-SOURCE, Pacific compatibility UNKNOWN |
| Microsoft Learn, online documentation | [Hardware IDs](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/hardware-ids) describes how the enumerator and INF model entries participate in Plug and Play matching. | CONFIRMED-DOCUMENTATION |

Both INF files carry Qualcomm copyright notices. This review records metadata
only. Any binary distribution requires review of the individual package terms.

### DXE_DISPATCH

| Fuente fijada de TianoCore | Aportación | Confianza |
| --- | --- | --- |
| [DxeMain.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/DxeMain/DxeMain.c) y [Event.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Event/Event.c) | Orden de los servicios de eventos, publicación de volúmenes, extracción de secciones y entrada al despachador. | CONFIRMED-SOURCE |
| [Dispatcher.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Dispatcher/Dispatcher.c) y [Dependency.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Dispatcher/Dependency.c) | Descubrimiento por notificación de FV2, evaluación de DEPEX y llamadas del despachador a CoreLoadImage y CoreStartImage. | CONFIRMED-SOURCE |
| [Image.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Image/Image.c) | Carga y relocalización PE/COFF, mantenimiento de caché y llamada al punto de entrada de la imagen. | CONFIRMED-SOURCE |
| [DevicePathDxe.inf](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf) y [DevicePath.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/DevicePathDxe/DevicePath.c) | GUID del archivo, DEPEX y publicación de EFI_DEVICE_PATH_UTILITIES_PROTOCOL. Código de TianoCore sin cambios, BSD-2-Clause-Patent. | CONFIRMED-SOURCE |
| [AArch64Mmu.h](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/ArmPkg/Include/Chipset/AArch64Mmu.h) | Bits de permiso y atributos de la traducción. La ubicación de la tabla L3 y de las páginas de código procede del diseño del FD y del PE relocalizado. | CONFIRMED-SOURCE |

### DXE_GOP

| Fuente y revisión | Qué aporta | Confianza |
| --- | --- | --- |
| [GraphicsOutput.h](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Include/Protocol/GraphicsOutput.h) | Orden Blue, Green, Red, Reserved del píxel BLT, semántica de VideoFill, VideoToBltBuffer y PixelBltOnly. EDK2 sin cambios. | CONFIRMED-SOURCE |
| [DevicePathUtilities.h](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Include/Protocol/DevicePathUtilities.h) y [Dependency.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Dispatcher/Dependency.c) | AppendDeviceNode construye la ruta del GOP. El despachador evalúa el GUID de protocolo de la expresión DEPEX. EDK2 sin cambios. | CONFIRMED-SOURCE |
| [Verificador local de las capturas Pacific](../tools/verify_sec_visual_data.py) y [ensayo SEC_C](evidence/sec-c-transfer-20261118.json) | Capturas originales de aboot y del árbol en ejecución cotejadas por hash. Sustentan la geometría, base y stride. La observación en el visor distingue azul y rojo. | CONFIRMED para esta unidad y esta ruta de arranque |

### DXE_TEXT

| Fuente | Aportación | Confianza |
| --- | --- | --- |
| [EDK2 SimpleTextOut.h](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Include/Protocol/SimpleTextOut.h) | ABI de `EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL`, orden de los métodos, modos, atributos y estados. | CONFIRMED-SOURCE |
| [EDK2 GraphicsConsoleDxe.inf](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf) y [LaffStd.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/Console/GraphicsConsoleDxe/LaffStd.c) | Dependencias HII y Driver Binding de la consola genérica, y bitmaps estrechos 8×19 de los 95 caracteres ASCII imprimibles y los 50 caracteres gráficos de UEFI. | CONFIRMED-SOURCE |
| [Captura anterior de GOP en el Go](evidence/dxe-gop-transfer-20261120.json) | Salida física del segundo driver y orden BGR observados en la unidad Pacific. La colocación del texto y su orientación bajo las lentes se comprobarán en el visor. | CONFIRMED-DEVICE para el GOP, HYPOTHESIS para la orientación óptica |

### DXE_APP

| Fuente y versión | Qué aporta | Confianza |
| --- | --- | --- |
| [UEFI 2.10, §7.4 Image Services](https://uefi.org/specs/UEFI/2.10/07_Services_Boot_Services.html#image-services) | Contrato de LoadImage, StartImage y retorno de una aplicación. | CONFIRMED-SPEC |
| [EDK2 Image.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Core/Dxe/Image/Image.c) y [DxeServicesLib.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Library/DxeServicesLib/DxeServicesLib.c) | Carga por ruta del volumen, lectura de la sección PE32, ejecución, CoreExit y descarga. | CONFIRMED-SOURCE |
| [EDK2 ArmVirtRules.fdf.inc](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/ArmVirtPkg/ArmVirtRules.fdf.inc) y [ApplicationEntryPoint.c](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdePkg/Library/UefiApplicationEntryPoint/ApplicationEntryPoint.c) | Regla FFS de aplicación y punto de entrada que llama al código propio. | CONFIRMED-SOURCE |
| [Consola del Go en ambos ojos](evidence/dxe-text-upright-transfer-20261120.json) | Identifica el modo y la orientación ya observados en esta unidad. | CONFIRMED-DEVICE para el dibujo previo |

## Shell en el arranque normal

| Fuente y revisión | Archivos | Evidencia | Confianza |
| --- | --- | --- | --- |
| [TianoCore EDK2](https://github.com/tianocore/edk2/tree/e7aac7fc137e247edad22f7ee53b9a1fba227397) `e7aac7fc137e247edad22f7ee53b9a1fba227397` | `MdeModulePkg/Core/Dxe/DxeMain/DxeMain.c`, `MdeModulePkg/Core/Dxe/Image/Image.c` | El despachador completa los protocolos arquitectónicos y llama al BDS de la plataforma. Los servicios de imágenes leen el PE de la ruta FV. | CONFIRMED-SOURCE |
| [Aplicación Shell](https://github.com/tianocore/edk2/tree/e7aac7fc137e247edad22f7ee53b9a1fba227397/ShellPkg/Application/Shell) misma revisión | `Shell.inf`, `Shell.c`, `Shell.uni`, `ShellPkg/ShellPkg.dec` | GUID, tipo de aplicación, banner y prompt producidos por `DoShellPrompt()` antes de leer la consola. | CONFIRMED-SOURCE |
| [ConSplitter](https://github.com/tianocore/edk2/tree/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/Console/ConSplitterDxe) misma revisión | `ConSplitter.c` | Handle de entrada virtual y evento de espera sin teclas físicas conectadas. | CONFIRMED-SOURCE |
| [Variables de EDK2](https://github.com/tianocore/edk2/tree/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/Variable/RuntimeDxe) misma revisión | `VariableNonVolatile.c`, `VariableDxe.c` | `PcdEmuVariableNvModeEnable` selecciona almacenamiento en RAM y evita la dependencia del protocolo flash. | CONFIRMED-SOURCE |
| [QEMU Arm virt](https://www.qemu.org/docs/master/system/arm/virt.html) | DTB de la máquina de la prueba, generada por QEMU con `virt,gic-version=3` | Direcciones de GIC y PL011 del modelo. Los valores de Pacific se documentan en [MEMORY_MAP.md](MEMORY_MAP.md). | CONFIRMED-MODEL |

### Campo de visión y lectura de la Shell en el Go

La sección *Head Mounted Displays* del estudio experimental con Oculus Go y Quest informa de unos 100° de campo binocular y un LCD de 2560 × 1440 para el Go. DOI 10.3389/frvir.2021.582156, versión publicada en 2021. Confianza alta para la descripción del modelo. La zona legible de este usuario, la distorsión por lente y una conversión de grados a píxeles del GOP siguen sin medir. [Artículo original](https://www.frontiersin.org/journals/virtual-reality/articles/10.3389/frvir.2021.582156/full)

La observación local de la primera Shell sitúa el recorte en la primera columna. La aplicación de prueba anterior permitió leer filas cortas cerca del centro de cada lente con glifos de 16 × 38 píxeles. El modo de consola de 24 × 12 celdas conserva ese tamaño de letra y centra la ventana como hipótesis de trabajo. [Lectura de la aplicación anterior](evidence/dxe-app-transfer-20261120.json) · [Registro de la primera Shell](evidence/shell-transfer-20261120.json)
