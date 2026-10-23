# OculusGo_EDK2_UEFI

Reconstruction of the Oculus Go (`pacific`) ARM64 UEFI platform, started
2026-10-22 under the owner's restricted source policy.

Permitted sources are original project code, repositories owned by
`h0nda1337`, upstream TianoCore EDK2, the official Oculus Go kernel, and
individually documented compatible drivers. No driver is imported yet.

The new tree has independent Git history. The previous experimental project,
its backups and physical-test records remain local, outside this repository.
Its earlier successful compilation does not validate this reconstruction.

The firmware will enter SEC directly from an integrated ARM64 image header.
No BootShim, firmware copying stage, edk2-msm dependency, external platform
package, or external Android-image packager is part of this build.

The diagnostic UEFI interface is named **TrustMeBro**, using
`OCULUS_GO_TRUST_ME_BRO_PROTOCOL` and `Protocol/TrustMeBro.h`.

Build and test results are recorded in `docs/STATUS.md`. No execution on the
headset is claimed. Before any step requiring the physical headset, work
stops and the owner is notified. Partition writes remain separately gated.
