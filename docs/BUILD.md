# Reproducible local build

Required tools: Git, Python 3, GCC/binutils for AArch64, host GCC/G++, GNU make,
libuuid development headers and WSL Debian on Windows. QEMU is a test tool,
not an imported firmware component. Python tools use only the standard library.

```powershell
python scripts/setup-edk2.py
.\scripts\build-edk2.ps1 -Target DEBUG -Jobs 8
```

On Linux/WSL, run `bash scripts/build.sh DEBUG 8` from any directory. The
workspace contains just this repository and its pinned official EDK2 checkout.
No edk2-platforms or former edk2-msm checkout is searched. BaseTools builds
only the required applications rather than fetching optional submodules.
See THIRD_PARTY_NOTICES.md for the unused DEC include-directory workaround.

Each successful build preserves the FD, EDK2 build report, GUID index and
structural verifier result in a timestamped `build/DEBUG-*` directory. Build
logs remain under `logs/`. Outputs are excluded from Git. The verifier checks
ARM64 header, length, both in-place branches and the FV header checksum.

```sh
bash scripts/test-host.sh
```

The host tests compile the actual TrustMeBro driver against official EDK2
headers and mocked boot services. They test HOB validation, install gating,
size negotiation, invalid arguments, copying and entry-register preservation.
Synthetic Python format tests exercise corruption rejection and Android
container roundtripping; they do not stand in for a device test.

The original container writer accepts the exact local stock boot and EVT DTB
hashes, validates the direct FD, and emits only below `local/`. Example with
operator-supplied local paths:

```sh
python tools/android_boot.py --fd build/<successful-run>/OCULUS_GO_DIRECT.fd \
  --dtb <original-local-EVT.dtb> --stock-boot <original-local-boot_a.img> \
  --output local/oculus-go-direct-OFFLINE-ONLY.img
```

This only creates a local file. Python/zlib versions are recorded because
gzip bitstreams may differ across runtimes. No command in this new tree
executes the image on the headset.
