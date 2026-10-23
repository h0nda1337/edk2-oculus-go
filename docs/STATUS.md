# Status

2026-10-22: source-policy reconstruction started in an independent repository.

| Milestone | New tree |
| --- | --- |
| Device evidence/backups | Preserved locally in the preceding project |
| Allowed-source platform | In progress |
| Standalone EDK2 build | Pending |
| TrustMeBro protocol | In progress |
| Direct-entry image without BootShim | In progress |
| Execution on Oculus Go | UNKNOWN; not tested |
| GOP/storage/USB/ACPI/Windows | Not implemented in this reconstruction |

The previous experiment accepted one temporary diagnostic image and showed
only a static logo. It did not prove EDK2 execution. Android was recovered;
boot A/B and aboot A/B hashes matched the original backups. No partition-write
command was issued by the project. This is historical evidence, not a test of
the new implementation.
