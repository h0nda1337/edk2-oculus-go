# Dependencies

Original platform, protocol, container writer and local scripts: project
contributors, BSD-2-Clause-Patent (see LICENSE).

The sole firmware source dependency is upstream TianoCore EDK2 at
`e7aac7fc137e247edad22f7ee53b9a1fba227397`, acquired independently from
https://github.com/tianocore/edk2.git. EDK2 retains its own License.txt and
per-file notices, including those of in-tree compression/compiler routines.
The platform uses ArmPkg, ArmPlatformPkg's HOB-pointer library, EmbeddedPkg,
MdePkg, MdeModulePkg and ArmVirtPkg's FFS build rules. No other platform
repository is a build dependency. No EDK2 submodule is required by this target.
Setup creates an empty optional Brotli include directory because the upstream
DEC validates its existence even when no Brotli module is selected. No Brotli
source, headers, substitute implementation or submodule is downloaded.

The official Oculus Go kernel is used as hardware/boot-ABI documentation;
no kernel C/assembly implementation is linked. Device-derived DTB and boot
headers remain local and excluded from Git. Packaging those inputs locally
does not grant redistribution rights over them.

No external driver or user-repository code is imported at this revision.
Future imports must record original copyright, license, repository, commit,
file and changes here before being built.

The DXE_DISPATCH trial links upstream DevicePathDxe unchanged from
[TianoCore at the pinned revision](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf).
The driver sources are `MdeModulePkg/Universal/DevicePathDxe/DevicePath.c`
and `DevicePathDxe.inf`, under BSD-2-Clause-Patent. The platform selects
Device Path Utilities and disables the optional text conversion interfaces.

## Console font

The 95 printable ASCII bitmaps and 50 standard UEFI drawing glyphs in `OculusGoPkg/Include/third-party/edk2/ConsoleFont.h` come from TianoCore EDK2, commit `e7aac7fc137e247edad22f7ee53b9a1fba227397`, file `MdeModulePkg/Universal/Console/GraphicsConsoleDxe/LaffStd.c`. Copyright (c) 2006–2008, Intel Corporation. Licensed under BSD-2-Clause-Patent. The adaptation keeps the 19 bitmap bytes per glyph for U+0020 through U+007E and the 50 UEFI drawing characters, removes the HII metadata and orders the drawing entries by code point. The font test compares every byte with the pinned source. The text protocol, rotation and dual-view renderer are original to this project. [Original bitmaps](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/MdeModulePkg/Universal/Console/GraphicsConsoleDxe/LaffStd.c) · [License](https://github.com/tianocore/edk2/blob/e7aac7fc137e247edad22f7ee53b9a1fba227397/License.txt)
