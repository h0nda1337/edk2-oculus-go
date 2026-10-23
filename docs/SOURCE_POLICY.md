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
8. Device captures and partition backups are evidence, not imported source.
   They remain local and are never uploaded by this repository's scripts.

The initial EDK2 commit is retained to avoid changing compiler compatibility
at the same time as replacing platform code. It is obtained directly from
TianoCore, independently of the previous project's source dependency graph.

No physical operation is authorized by a successful offline build. The owner
requested notification and an ended turn before the headset is needed.
