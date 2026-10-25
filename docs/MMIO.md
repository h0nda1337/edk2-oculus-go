# MMIO evidence used by this reconstruction

| Resource | Base | Size | Evidence | Enabled use |
| --- | --- | --- | --- | --- |
| GIC distributor | `0x09bc0000` | `0x10000` | Unit runtime DT | EDK2 driver integration, offline only |
| GIC redistributors | `0x09c00000` | `0x100000` | Unit runtime DT, stride `0x40000` | Same |
| Generic timer | Architectural registers | n/a | Unit DT, 19.2 MHz | EDK2 timer library/driver |
| UFS host | `0x00624000` | `0x2500` | Unit runtime DT | None |
| USB DWC3 child | `0x06a00000` | `0xc8d0` | Unit runtime DT | None |
| MDSS/MDP | `0x00900000` | `0x90000` | Unit runtime DT | None |

The address map permits no other peripheral access. No PMIC, GPIO, regulator,
clock, panel, storage or USB register sequence has been copied from another
device. Confirmed resource addresses do not establish that a write sequence
is correct or that a driver is compatible. Windows ACPI identifiers and IOMMU
stream mappings remain UNKNOWN until separately evidenced.
