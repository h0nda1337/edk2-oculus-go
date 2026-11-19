# Next steps

DXE_TABLES passed in QEMU at EL1 and EL2. The next measurement requires an attended temporary boot of the reviewed image and observation of its two framebuffer bands. The next upstream DXE initializer requests more contiguous RAM than the current arena provides. Resolve ownership and alignment before driver dispatch and the GOP text console. [Candidate and evidence](DXE_TABLES.md) · [Last physical checkpoint](evidence/dxe-gcd-transfer-20261119.json)

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
2. SEC_MMU reached the red-center checkpoint with stage-1 translation active
   on the Go. The bounded in-FD workspace and compressed volume passed the SEC_DXE model.
   The physical SEC_DXE observation subsequently confirmed the handoff into DxeMain.
   [Attended MMU trial](evidence/sec-mmu-transfer-20261118.json)
3. The optional floating monitor can be prototyped offline over the BGR model
   with simulated orientation. [UEFI VR menu design](VR_MENU.md)
