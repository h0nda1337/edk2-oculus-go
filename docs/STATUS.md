# Status

Reconstruction started 2026-10-22. Offline verification extended 2026-10-25.

| Milestone | New tree |
| --- | --- |
| Device evidence/backups | Preserved locally in the preceding project |
| Allowed-source platform | Original board code + pinned official EDK2; compiler/link inputs audited |
| Standalone EDK2 build | PASS, DEBUG, 4 MiB FD |
| TrustMeBro protocol | PASS: 19 host checks; installed, located and queried from real DXE in QEMU EL1/EL2 |
| Direct-entry image without BootShim | PASS: header/FV/SEC structure; original Android container roundtrip/reproducibility |
| Early ARM64 entry in QEMU | PASS: 10 cases, stop before first BL |
| SEC to DXE in QEMU | PASS: EL1 and EL2, HOBs, memory setup, decompression and loaded DXE entry |
| Execution on Oculus Go | UNKNOWN; not tested |
| GOP/storage/USB/ACPI/Windows | Not implemented in this reconstruction |

The exact same FD passes the early-entry, SEC and DXE tests. No emulator-only
board addresses replace the production map. QEMU supplies ordinary RAM that
contains the selected addresses; tests stop after the diagnostic protocol,
before normal board-driver dispatch. This does not emulate Kryo, secure-world
handoff, the panel, watchdog or Go peripherals.

```text
FD: 4194304 bytes
SHA-256: a4acf898e51a814ad6ed4c84a9dacd8788120ad272c3fa528fb0b7579b698230
Android candidate: 487424 bytes
SHA-256: cbccd484b056f16ddb55f2bf9170673e92beba6d7456b37d779a6347d841426c
```

The Android candidate is local-only and marked NOT-FOR-DEVICE-EXECUTION.
Gzip decompression reproduces the complete FD and leaves exactly the original
365129-byte EVT DTB. Three locally generated containers have identical hashes.
No partition binary or generated device image is uploaded to GitHub.

Source audit covers 66 compiler dependency lists and 67 static archives:
5 original project inputs, 434 EDK2 inputs, and 144 generated files. The
official EDK2 commit/origin, tracked-file membership and clean tree are also
checked. No rejected input; optional Brotli code is not present or compiled.

M1 is reached for the new build. **M2 and M3 remain unconfirmed on hardware.**
No ADB/Fastboot command was issued during this reconstruction. The next step
that needs the headset starts with fresh read-only identity/state/integrity
checks, with the owner notified and this turn ended before device access.
The complete FD is not cleared for a physical execution test.

The previous experiment accepted one temporary diagnostic image and showed
only a static logo. It did not prove EDK2 execution. Android was recovered;
boot A/B and aboot A/B hashes matched the original backups. No partition-write
command was issued by the project. This is historical evidence, not a test of
the new implementation.
