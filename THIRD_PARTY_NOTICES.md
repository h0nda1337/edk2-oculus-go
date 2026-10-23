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
