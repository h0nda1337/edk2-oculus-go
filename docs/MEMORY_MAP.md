# Memory evidence and candidate layout

Hardware evidence is retained in the preceding local project. This document
records data, not imported implementation. No new physical capture was made.

| Range / value | Evidence | Status |
| --- | --- | --- |
| DRAM `0x80000000..0x13eac0000` | Unit's runtime device tree | CONFIRMED-DEVICE |
| Low Linux System RAM `0x80000000..0x85800000` | Unit's `/proc/iomem` | CONFIRMED-DEVICE; contains splash reservations |
| High System RAM `0x91700000..0x13eac0000` | Same | CONFIRMED-DEVICE; contains further reservations |
| Initial usable window `0x91700000..0x9ff00000` | Runtime reservations subtracted from prior captures | Candidate subset; new handoff not tested |
| FD `0x80080000..0x80480000` | Exact stock `aboot_a` sets the ARM64 destination. The SEC_C exact-PC guard and its private stack witness passed on this unit | CONFIRMED-DEVICE for that executed SEC path. Stability of the entire range through DXE is UNKNOWN |
| FV `0x80081000..0x80480000` | New FD format at offset `0x1000` | Build-defined; validated structurally |
| HOB/decompression pool `0x94000000..0x98000000` | Inside selected high RAM window | HYPOTHESIS at physical handoff |
| Initial stack `0x97fc0000..0x98000000` | Top 256 KiB of pool, removed from HOB allocator | Build-defined; physical stability UNKNOWN |
| GIC distributor `0x09bc0000`, size `0x10000` | Runtime DT; official kernel `msm8996.dtsi` | CONFIRMED-DEVICE address; initialization untested |
| GIC redistributors `0x09c00000`, size `0x100000` | Runtime DT, stride `0x40000` | CONFIRMED-DEVICE address; initialization untested |
| Generic timer 19.2 MHz; GSIV 29/30/27/26 | Runtime DT and kernel | CONFIRMED-DEVICE; inherited EL access UNKNOWN |

All ends above are exclusive. The occupied FD is reserved. The normal
memory map excludes splash `0x83400000..0x85800000`, secure carve-outs
`0x85800000..0x91700000` and ramoops `0x9ff00000..0xa0000000`. Only the
`GOP_MODEL` emulation profile maps the entire 24-bit surface
`0x83401000..0x83e8d000` as normal non-cacheable memory and publishes a
reserved-memory resource HOB for it. It leaves the surrounding reservation
outside the map. FDT at the observed `0x82000000` is recorded as a pointer.
The pool is allocator memory, not a platform memory-size probe.

The firmware executes in place. The normal entry saves x0–x3 on its stack
before the first call. SEC later copies the saved record into a GUID HOB.
Exception vectors live inside the loaded SEC image. The normal path has
been exercised through DXE in QEMU. [Test scope](STATUS.md)

The operator saw the SEC pattern on November 18. The firmware targets two
bands, but their exact positions in the visor and coverage of each eye
were not measured. Scanout through DXE, DMA quiescence, watchdog
behavior and the allocator's high-RAM pool still require evidence.

## High RAM at the SEC handoff, reviewed November 18

Both local DTBs use two address and two size cells and have empty FDT header
reservation maps. Their `/reserved-memory` nodes still describe seven fixed
regions. None intersect the proposed 64 MiB pool `[0x94000000, 0x98000000)`.
The selected stock EVT DTB's `/memory/reg` is all zero. The preserved tree
that Android received instead contains base `0x80000000`, size `0xbeac0000`.
The Android I/O memory capture places the pool in System RAM.

Both trees also request four dynamic allocations. For ADSP, QSEECom, the
secure region and Oculus DMA the shared `alloc-ranges` tuple has base 0 and
length `0xffffffff`. The Android boot log placed them at `0xff800000`
(4 MiB), `0xfe400000` (20 MiB), `0xf4800000` (156 MiB) and `0xffc00000`
(2 MiB), respectively. It logged a CMA alignment error for the Oculus DMA
region and a separate 32 MiB CMA reservation at `0xf2800000`. These are
observations of Android's allocator in that boot.

LK's ELF load segment occupies `[0x91800000, 0x918e84ac)`. Its scratch base
is `0x91e00000`, and the 512 MiB download limit includes the proposed pool.
For the 487424-byte **SEC_C** Android image, the archived staging calculation
places the compressed image at `[0x91e00000, 0x91e77000)` and the 4 MiB
gzip output at `[0x91e78000, 0x92278000)`. The calculation starts gzip
output one 4 KiB page beyond the page-rounded input. These modeled spans
miss the pool. The QEMU GOP profile loads the FD directly and never runs LK.

The `SEC_MEM` pattern confirmed that the CPU completed one 8-byte load at
`0x94000000` and another at `0x97ffffa0` in its inherited memory view.
The code discarded both values. It constructed and checked the PHIT and
end marker inside the loaded image at `[0x80080200, 0x80080240)`.
The normal build would write the stack record at `[0x97ffffa0, 0x98000000)`
and construct its HOB list at `0x94000000`. The availability of the full
64 MiB for allocation, write access, DMA activity and scanout through normal DXE
remain unknown. [Physical SEC memory record](evidence/sec-mem-transfer-20261118.json)

The separate SEC_STACK profile reserves `[0x8043f000, 0x8047f000)` as its
256 KiB stack with 4 KiB guards immediately below and above. The bounds
are a choice in the FD layout. Two full-span patterns, the 96-byte entry
record and nested C/PI calls reached their visual checkpoint on the Go.
SEC_MMU subsequently verified its one-page translated stack and witnessed a write/read there. Stability through DXE is UNKNOWN.
[Footprint, origins and checks](SEC_STACK.md)

The separate terminal SEC_MMU image builds seven 4 KiB translation tables
at `[0x8043f000, 0x80446000)` and uses `[0x8047e000, 0x8047f000)` for its
stack. It maps four code pages, the stack page and 68 pages covering the
two scanout bands plus their final page tails. The walker uses the tables
physically. All 3,584 descriptor words and both scanout bands were checked
in QEMU. On the Go the operator saw the red center after validating the translated
stack and both band readbacks. Physical EL remains UNKNOWN. [Detailed map](SEC_MMU.md)

| Local evidence checked | SHA-256 |
| --- | --- |
| Selected stock EVT DTB | `70ae171c99befc564acec661f3afc4365a831ebd1d6e01ca0e53035a4d8b1f35` |
| Android runtime DTB | `0877ab5ba9149c29af776389796978268c665c51878834f2335405cabef01929` |
| Android `iomem.txt`, October 2 UTC capture | `12bc1c23f7d8cde6e06089ddaa238fbb48608082a379e98851f1f841d3e51248` |
| Android `dmesg.txt`, same capture | `5ac886825ffbdaf76cd4f07ec8b3965bb82920df30d26e801ffa907e068621f1` |
| Preserved `aboot_a` ELF | `6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74` |
| Historical `build/analysis/lk-audit.json`, all 133 instruction words rechecked against ELF | `ee0b422baac9f52eea490a5cec8a5db49e0c6e1eed98cc0485f18722552241d5` |
