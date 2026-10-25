# ACPI work boundary

No tables from another device are imported. Initial Windows-facing work will
need a device-backed FADT, MADT, GTDT and DSDT, with only verified CPU/timer/
interrupt and platform data. These tables are not yet emitted by this build.

PPTT requires verified CPU/cache topology. SPCR and DBG2 require an accessible
and working debug UART. IORT requires real IOMMU/stream mappings; MCFG requires
evidenced PCI configuration space. Do not add them merely to match another
port. Keep future ASL maintainable and record every constant's provenance.
