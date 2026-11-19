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
   The next image reserves a guarded 256 KiB stack in the loaded FD.
   Its positive and fault paths passed QEMU. The pending measurement is the
   temporary, attended SEC_STACK boot and subsequent Android readback.
   [Procedure and expected observation](SEC_STACK.md)
2. Establish a bounded allocator for page tables, HOBs and DXE workspace.
   Verify scanout through MMU setup and DXE before trying the GOP on the
   visor. Storage, USB and the required ACPI tables precede Windows Boot Manager.
3. The optional floating monitor can be prototyped offline over the BGR model
   with simulated orientation. [UEFI VR menu design](VR_MENU.md)
