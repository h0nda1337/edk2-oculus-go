# OculusGo_EDK2_UEFI

Reconstruction of the Oculus Go (`pacific`) ARM64 UEFI platform, started
2026-10-22 under the owner's restricted source policy.

Permitted sources are original project code, repositories owned by
`h0nda1337`, upstream TianoCore EDK2, the official Oculus Go kernel, and
individually documented compatible drivers. No driver is imported yet.

The new tree has independent Git history. The previous experimental project,
its backups and physical-test records remain local, outside this repository.
Its earlier successful compilation does not validate this reconstruction.

The firmware enters SEC directly from an integrated ARM64 image header.
No BootShim, firmware copying stage, edk2-msm dependency, external platform
package, or external Android-image packager is part of this build.

The diagnostic UEFI interface is named **TrustMeBro**, using
`OCULUS_GO_TRUST_ME_BRO_PROTOCOL` and `Protocol/TrustMeBro.h`.

The DEBUG firmware compiles. The same FD passes bounded entry tests and runs
SEC, memory setup, FV decompression and DXE through **TrustMeBro installation,
LocateProtocol and GetState**, in both EL1 and EL2 under QEMU. A reproducible
Android boot container is prepared locally with an original packager.

```powershell
python scripts/setup-edk2.py
.\scripts\build-edk2.ps1 -Target DEBUG -Jobs 8
```

**M2 reached on the Oculus Go, November 18, 2026.** The original loader
reported `Secure boot: true` and temporarily booted the terminal EDK2 SEC
diagnostic. The owner saw its four colors. Android booted again on slot A
and all four full `boot` and `aboot` readbacks matched the original backups.
[Measurement and recovery evidence](docs/evidence/sec-visual-transfer-20261118.json)

A second temporary image, `SEC_C`, drew its markers from C after checking a
witness on its private stack. The owner saw blue on both sides of white and
red on both sides of black. This identifies byte 0 as blue and byte 2 as red
in the inherited packed framebuffer, consistent with BGR.
[Physical SEC C observation](docs/evidence/sec-c-transfer-20261118.json)

On the same Go, the five-color `SEC_MEM` signal confirmed that SEC constructed
and checked the initial PI handoff table within the firmware image and
completed two 8-byte reads at the proposed HOB and stack addresses.
[Physical memory trial](docs/evidence/sec-mem-transfer-20261118.json)

The Go reached upstream DxeMain in the SEC_DXE trial. The operator saw white, green, purple, green, white after the relocated DXE Core validated the HOB list. [Physical DXE record](docs/evidence/sec-dxe-transfer-20261119.json)

The next candidate exercises DXE memory services in QEMU through the Boot Services table. Four positive boots observed the two allocated pages return to conventional memory. Physical memory services, driver dispatch, GOP, Shell and Windows boot remain future milestones. [DXE_MEM trial](docs/DXE_MEM.md) The owner is notified before physical work and separately
authorizes partition writes. [Build instructions](docs/BUILD.md) · [Platform status](docs/STATUS.md)

The planned VR boot menu puts the boot entries, UEFI Shell, settings and
diagnostics on a floating stereo monitor. The first compositor can be tested
in software with simulated orientation. [Menu design and dependencies](docs/VR_MENU.md)
