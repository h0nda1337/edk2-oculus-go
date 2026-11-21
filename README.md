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

DXE_MEM reached its green-center checkpoint on the Go. Upstream DXE Boot Services allocated two pages and a 257-byte pool. The diagnostic verified all 8,449 bytes and checked that the pages returned to conventional memory after release. Android booted on slot A, and the four bootloader and boot partition hashes matched the preflight and original backups. [Physical record](docs/evidence/dxe-mem-transfer-20261119.json) · [Diagnostic and QEMU results](docs/DXE_MEM.md)

The Go completed `DXE_GCD`. The operator saw a light-blue center between purple bands and white ends. DXE Core looked up its Loaded Image protocol, verified the relocated HOB list and its original GUID page, and confirmed ownership of the 1.5 MiB arena and reserved 64 KiB stack in the GCD memory map. [Physical record](docs/evidence/dxe-gcd-transfer-20261119.json) · [Checkpoint definitions](docs/DXE_GCD.md)

`DXE_TABLES` passed 52 model cases at EL1 and EL2. DXE Core ran its five library constructors, published the migrated HOB list and DXE Services, and used the published services to inspect the active stack. The Go reached the same terminal checkpoint during an attended RAM boot with Secure Boot active. [Physical record](docs/evidence/dxe-tables-transfer-20261119.json) [Results and image review](docs/DXE_TABLES.md)

`DXE_DEBUG` uses one aligned page inside the loaded FD for the debugger locator. QEMU followed its CRC-checked system table pointer to the registered DXE Core image in EL1 and EL2. The operator observed the terminal red bands and cyan center on the Go during a RAM boot with Secure Boot active. [Physical record](docs/evidence/dxe-debug-transfer-20261119.json) · [QEMU evidence and scope](docs/DXE_DEBUG.md)

`DXE_DISPATCH` continued past this checkpoint in QEMU at EL1 and EL2. The
dispatcher scheduled upstream DevicePathDxe from the firmware volume. Its
published Device Path Utilities protocol answered a call from DXE Core.
The same image reached the final checkpoint on the Go. The operator saw white,
orange, green, orange and white after the driver's GetDevicePathSize call.
[Physical record](docs/evidence/dxe-dispatch-transfer-20261119.json)
[Results and visual checkpoints](docs/DXE_DISPATCH.md)

In `DXE_GOP`, InheritedGopDxe starts second after DevicePathDxe publishes its protocol. At EL1 and EL2 in QEMU, DXE called the published GOP 24 times to fill and read back two bands. The resulting packed BGR pattern is blue, red, yellow, red, blue. On November 20 the owner saw the same pattern in the Go, confirming M3, visible UEFI graphics through GOP. [Physical observation](docs/evidence/dxe-gop-transfer-20261120.json) [Reproduction and visual checkpoints](docs/DXE_GOP.md)

The `DXE_TEXT` diagnostic publishes the graphical console on the GOP handle. ARM64 DXE calls `SystemTable->ConOut->OutputString()` twice. The QEMU framebuffer shows “EDK2 GO” in white and “UEFI 42” in cyan in both eye views. On the Go, the owner read both lines after turning the headset. Text appeared upside down in the normal wearing position. [Physical observation](docs/evidence/dxe-text-transfer-20261120.json) [Capture and reproduction](docs/DXE_TEXT.md) The corrected image ran on the Go. Wearing it normally and checking both eyes separately, the owner read “1 EDK2 GO 2” on top and “3 UEFI 42 4” below. [Corrected console](docs/DXE_TEXT_UPRIGHT.md)

In the `DXE_APP` profile, DXE loads ConsoleProbe.efi by its firmware-volume file path and starts it through UEFI Boot Services. In QEMU the application's own ConOut call writes “5 APP EFI 6” in green in both views and returns to the launcher. On the Go, the owner read the white DXE line and the green application line. [Application trial](docs/DXE_APP.md)

The normal boot path now selects the Go text console in BDS and starts the upstream ARM64 Shell from the embedded firmware volume. QEMU displayed `Shell>` in both eyes using the Pacific firmware recovered from its Android boot image. On the Go the operator read `hell>` at the left edge and saw part of the console through the right lens. Android returned on slot A and both boot and aboot copies matched their original hashes. [Physical trial](docs/evidence/shell-transfer-20261120.json) · [Prompt capture and reproduction](docs/SHELL_BOOT.md)


The owner is notified before physical work and separately
authorizes partition writes. [Build instructions](docs/BUILD.md) · [Platform status](docs/STATUS.md)

The planned VR boot menu puts the boot entries, UEFI Shell, settings and
diagnostics on a floating stereo monitor. The first compositor can be tested
in software with simulated orientation. [Menu design and dependencies](docs/VR_MENU.md)
