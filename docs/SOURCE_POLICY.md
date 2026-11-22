# Source policy

Owner instruction, 2026-10-22: rebuild without external code except code in
the owner's GitHub repositories, the official Go kernel, EDK2 and drivers.
Authenticated GitHub owner verified as `h0nda1337`.

1. New board-specific implementation is authored in this project.
2. EDK2 means `https://github.com/tianocore/edk2.git` at the pinned commit.
   Only required in-tree packages are put in PACKAGES_PATH. No other
   platform repository is accepted implicitly.
3. Official kernel source is
   `https://github.com/facebookincubator/oculus-linux-kernel.git`, commit
   `9475755c1a328a7b873721897ef339a8ad35c86a`. It is hardware/ABI evidence;
   no GPL kernel implementation is linked into the initial firmware.
4. User-owned repositories must have an explicit commit, source file and
   license entry before any code is imported. Ownership does not erase
   upstream copyright or license requirements.
5. Drivers require individual origin, license, hardware compatibility and
   change records. This exception is not used to import an entire platform
   or a boot shim. Initially there are no external driver imports.
6. BootShim, edk2-msm, Lumia/Surface Duo platform code, EFIDroid, SimpleInit,
   CAF LK code and AOSP mkbootimg are excluded from the new build and tree.
   Prior third-party-derived PrePi/memory-init files are not copied here.
7. GCC/binutils, Python standard library, Git and WSL are build tools.
   Their implementation is not vendored into the platform. EDK2's compiler
   support libraries and BaseTools retain their upstream notices.
8. The platform and emulator use the same generated EDK2 UFS pass-through
   module. The [unit-enumeration patch](../tests/UfsSplashApp/ufs-sparse-units.patch)
   validates sparse units. The [capacity patch](../patches/edk2-ufs-capacity.patch)
   reports the bus address used by a completed LUN 4 capacity request. Both
   retain EDK2's BSD-2-Clause-Patent notices. The PCI host provider belongs
   to the emulator. The [lock file](../sources.lock.json) records upstream
   paths, commit, patch order and SHA-256 digests of both patches and all
   generated files. The build atomically publishes this module from Git
   blobs in a directory keyed by the output manifest digest. Simultaneous
   builds read immutable copies and a changed recipe can publish a new
   source tree while an earlier build is still running.
   PacificUfsDxe, GoUfsHcDxe, the Pacific FDT validation and the controller-scoped
   DMA protocol are original project code. The FDT parser calls the pinned
   EDK2 FdtLib at `e7aac7fc137e247edad22f7ee53b9a1fba227397`.
   Upstream paths are `EmbeddedPkg/Library/FdtLib/{FdtLib.inf,fdt*.c,libfdt_internal.h}` and
   `EmbeddedPkg/Include/{fdt.h,libfdt.h,libfdt_env.h}`. They are compiled unchanged.
   The EDK2 integration retains BSD-2-Clause-Patent, and the dual-licensed
   libfdt files retain their BSD alternative and notices. The upstream
   `MdeModulePkg/Library/NonDiscoverableDeviceRegistrationLib` is used
   unchanged under BSD-2-Clause-Patent. The emulator-only board fixture supplies its DMA interface
   using QEMU's PCI device. It is outside the normal Pacific firmware.
9. QEMU 10.0.13 is a host test tool. The project maintains a narrow
   [emulator patch](../tests/qemu/ufs-idle-task-list-10.0.13.patch) for the
   idle legacy task-list run bit and clearing idle run bits at HCI disable.
   It applies to upstream `hw/ufs/ufs.c` (Samsung, GPL-2.0-or-later) under
   the same license. The [build script](../scripts/build-qemu-ufs-handoff.sh)
   pins the archive and the hashes of the original and patched file. The QEMU
   executable and these changes stay on the host.
10. Device captures and partition backups are evidence, not imported source.
   They remain local and are never uploaded by this repository's scripts.

The initial EDK2 commit is retained to avoid changing compiler compatibility
at the same time as replacing platform code. It is obtained directly from
TianoCore, independently of the previous project's source dependency graph.

No physical operation is authorized by a successful offline build. The owner
requested notification and an ended turn before the headset is needed.
