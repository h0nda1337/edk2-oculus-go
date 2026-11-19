# Next steps

**M2 is complete.** The stock loader accepted the reviewed temporary image
with both security indicators active. The owner saw the SEC pattern, Android
returned and each of the four boot partition hashes matched on readback.
[Physical evidence](evidence/sec-visual-transfer-20261118.json)

The DXE GOP driver passed 22 calls per exception level in QEMU using the
observed packed BGR layout. The Go's inherited framebuffer at SEC
displayed byte 0 as blue and byte 2 as red. The owner saw the C pattern after
the stack witness check. Android returned on slot A and all four partition
hashes matched the originals after the trial. The `SEC_C` attempt is consumed.
[Physical record](evidence/sec-c-transfer-20261118.json) · [BGR test results](evidence/gop-bgr-qemu-20261118.json)

1. The five-color `SEC_MEM` checkpoint was observed on the Go. Android
   recovered on slot A and all four hashes matched. Before enabling the
   normal stack and allocator, establish which RAM the firmware can own
   and write at handoff. The two completed loads cover 8 bytes each.
   [Trial record](evidence/sec-mem-transfer-20261118.json) · [Memory evidence](MEMORY_MAP.md)
   SEC_STACK subsequently verified two full-span patterns and nested C calls
   on a guarded 256 KiB stack inside the loaded image. The owner reported
   the five-color checkpoint. [Physical record](evidence/sec-stack-transfer-20261118.json)
2. Run the reviewed SEC_MMU trial on the visor. Its page tables fit inside
   the proven SEC_STACK region. A red center after translation distinguishes
   it from the initial monochrome signal. [Attended trial](SEC_MMU.md)
   Establish a bounded allocator for HOBs and the DXE workspace.
   Verify scanout through MMU setup and DXE before trying the GOP on the
   visor. Storage, USB and the required ACPI tables precede Windows Boot Manager.
3. The optional floating monitor can be prototyped offline over the BGR model
   with simulated orientation. [UEFI VR menu design](VR_MENU.md)
