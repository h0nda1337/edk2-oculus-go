# Memory evidence and candidate layout

Hardware evidence is retained in the preceding local project. This document
records data, not imported implementation. No new physical capture was made.

| Range / value | Evidence | Status |
| --- | --- | --- |
| DRAM `0x80000000..0x13eac0000` | Unit's runtime device tree | CONFIRMED-DEVICE |
| Low Linux System RAM `0x80000000..0x85800000` | Unit's `/proc/iomem` | CONFIRMED-DEVICE; contains splash reservations |
| High System RAM `0x91700000..0x13eac0000` | Same | CONFIRMED-DEVICE; contains further reservations |
| Initial usable window `0x91700000..0x9ff00000` | Runtime reservations subtracted from prior captures | Candidate subset; new handoff not tested |
| FD `0x80080000..0x80480000` | Exact stock `aboot_a` fixes ARM64 kernel destination at `0x80080000`; official kernel image ABI | HYPOTHESIS staging for new 4 MiB FD |
| FV `0x80081000..0x80480000` | New FD format at offset `0x1000` | Build-defined; validated structurally |
| HOB/decompression pool `0x94000000..0x98000000` | Inside selected high RAM window | HYPOTHESIS at physical handoff |
| Initial stack `0x97fc0000..0x98000000` | Top 256 KiB of pool, removed from HOB allocator | Build-defined; physical stability UNKNOWN |
| GIC distributor `0x09bc0000`, size `0x10000` | Runtime DT; official kernel `msm8996.dtsi` | CONFIRMED-DEVICE address; initialization untested |
| GIC redistributors `0x09c00000`, size `0x100000` | Runtime DT, stride `0x40000` | CONFIRMED-DEVICE address; initialization untested |
| Generic timer 19.2 MHz; GSIV 29/30/27/26 | Runtime DT and kernel | CONFIRMED-DEVICE; inherited EL access UNKNOWN |

All ends above are exclusive. No low RAM except the occupied FD is exposed
to the UEFI allocator. Splash `0x83400000..0x85800000`, secure carve-outs
`0x85800000..0x91700000`, and ramoops `0x9ff00000..0xa0000000` remain outside
the map. FDT at the observed `0x82000000` is recorded as a pointer, not read.
The pool is allocator memory, not a platform memory-size probe.

The new image has no firmware relocation/copy stage. Removal of that stage
invalidates the old 4 MiB-copy emulation results. New entry tests are required.
The C code records a HOB snapshot of initial x0-x3 before any C/library call;
there is no external fixed checkpoint page. Exception vectors live inside
the occupied SEC image and do not consume another physical region.

Watchdog, secure monitor delivery, DMA quiescence and continued scanout remain
UNKNOWN. A build success cannot establish any of these physical conditions.
