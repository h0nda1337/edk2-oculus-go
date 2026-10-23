# Permitted-source reuse

| Component | Source | Classification | Current use |
| --- | --- | --- | --- |
| PI HOB, FV and DXE machinery | Official EDK2, pinned in sources.lock.json | A | Compiled upstream |
| ARM MMU, cache, exception, GIC and timer libraries | Official EDK2 | B | Generic libraries; board addresses from unit evidence |
| Integrated ARM64/FV layout | Official Go kernel ABI and EDK2 ArmVirt format | C | New header data; no QEMU hardware constants |
| SEC entry and memory HOB setup | Original implementation in this repository | A | Newly authored |
| TrustMeBro protocol/driver | Original implementation in this repository | A | Newly authored |
| Android container writer | Original Python implementation | A | Newly authored; no external mkbootimg |
| User-owned repositories | h0nda1337 | Pending per-file review | No import |
| Additional compatible drivers | To be identified by hardware block | Pending | No import |
| Former platform/BootShim-derived code | Previous local experiment | Excluded by current policy | Outside new tree and build graph |

A means directly reusable; B needs adaptation/validation; C is a format or
conceptual reference. Upstream licensing and contributor identity are retained.
