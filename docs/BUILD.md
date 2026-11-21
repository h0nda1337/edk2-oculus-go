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

Each successful build preserves the FD, EDK2 build report, GUID index,
structural result and compiler/link-source audit in a timestamped
`build/DEBUG-*` directory. Build
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

For the first direct FD, run the full suite from Linux/WSL:

```sh
python3 scripts/validate-offline.py --build-dir build/DEBUG-20261023-030354
```

This logs 19 driver checks, 8 format cases, 10 early-entry cases, two SEC/DXE
handoff cases and two real-DXE TrustMeBro cases. The latter execute the normal
DXE installation, then call real boot-services LocateProtocol and the actual
GetState implementation. They stop before returning to board-driver dispatch.
The full SEC/DXE harness pins the reviewed FD hashes and handoff callsites;
it deliberately rejects an unreviewed binary. The matching SEC/DXE symbol
files must come from the corresponding build.
Generated test logs/reports remain in `build/validation-<UTC timestamp>/`.

The source auditor rejects compiler inputs outside the project/upstream/
generated roots, untracked upstream inputs, wrong EDK2 origin/revision and
tracked source modifications. It also records the static archives, including
EDK2's own GCC LTO support archive. On Windows it translates WSL `/mnt/<drive>`
dependency paths explicitly, rather than assuming a particular drive letter.

The original container writer accepts the exact local stock boot and EVT DTB
hashes, validates the direct FD, and emits only below `local/`. Example with
operator-supplied local paths:

```sh
python tools/android_boot.py --fd build/<successful-run>/OCULUS_GO_DIRECT.fd \
  --dtb <original-local-EVT.dtb> --stock-boot <original-local-boot_a.img> \
  --output local/oculus-go-direct-OFFLINE-ONLY.img
```

This only creates a local file. Python/zlib versions are recorded because
gzip bitstreams may differ across runtimes. The normal FD remains quarantined.
A separate opt-in `SEC_VISUAL` diagnostic and one-attempt runner are covered
by [their own review](SEC_VISUAL_PHYSICAL_REVIEW.md); the runner defaults to
offline validation and cannot be used for the normal FD.

## Test the UEFI graphics protocol in QEMU

```powershell
.\scripts\build-edk2.ps1 -Mode GOP_MODEL -Target DEBUG -Jobs 8
wsl -d Debian -- python3 tests/gop_model_qemu.py
```

The test accepts `--report <new-file.json>` to save both runs. To test an
archived build, pass `--build-dir <directory>` pointing to its `FV/` image
and matching `AARCH64/` SEC and DXE symbols.

This profile maps a reserved 1440 × 2560 surface in emulated RAM and dispatches
the original `InheritedGopDxe` driver after TrustMeBro. UEFI applications can
find the protocol with `LocateProtocol`. The single `PixelBltOnly` mode
translates four-byte UEFI BLT pixels (blue, green, red, reserved) into three
bytes on the model surface (blue, green, red). Readback returns zero in the
reserved byte. On the Go, `SEC_C` identified byte 0 as blue and byte 2 as
red in the inherited SEC surface. [Physical record](evidence/sec-c-transfer-20261118.json)

The BGR firmware at revision `7f5380e` passed 22 calls at EL1 and 22 at
EL2. Uploading six marker pixels reproduced the SEC color groups in memory.
For readback, the test seeded a different address directly with primary and
mixed colors before calling the protocol. It also checked the guard bytes,
overlapping copies and error paths. With the earlier RGB firmware and its
matching symbols, the same test reached DXE and rejected the first mixed
fill: it read `c3 58 19` where it expected `19 58 c3`.
[BGR firmware hash, samples and test results](evidence/gop-bgr-qemu-20261118.json)

The earlier RGB control build produced FD
`39cca2b407587ce474e7f2780449acb5e0f840943e2cf77aaff0271adde490ab`.
Its input audit accepted 7 project files, 434 upstream files and 147 generated
files (report SHA-256 `64d344fc33e57f12923be48db61b2b7945c09cdea640b9df984f4fe92c98de46`).
The test made 20 calls at EL1 and 20 at EL2, covering mode queries, mode
setting, fill, upload, readback, overlapping on-screen copies and invalid
arguments. The outer guard bytes stayed intact. The local QEMU report SHA-256
is `bac0686eb46ea805eed644674fdbe0eb1fe7099f3219da415360acf8bb5ffb0c`.
The headless tests inspect memory. They do not establish that a visor retains
scanout through physical DXE or that a Windows display driver will bind.

The separate [SEC C build and tests](SEC_C.md) cover the November 18
measurement. Building either diagnostic leaves the normal DEBUG firmware
byte-identical to its November 13 baseline, as verified on November 18.

The `DXE_GOP` profile packages DevicePathDxe and InheritedGopDxe in the same firmware volume. Its offline check extracts the firmware from the Android boot container and observes the two drivers and the BGR scanout. [Commands and expected display](DXE_GOP.md)

The [DXE_TEXT trial](DXE_TEXT.md) exercises both output strings through the UEFI system table and exports a pixel crop in logical reading coordinates from each modeled exception level. For the current headset orientation use the [marked text trial and AArch64 scrolling test](DXE_TEXT_UPRIGHT.md).

The `DXE_APP` mode packages a separately linked AArch64 EFI application. The audit compares its compiled PE with the section returned by the running guest firmware volume. [Reproduction and results](DXE_APP.md)
