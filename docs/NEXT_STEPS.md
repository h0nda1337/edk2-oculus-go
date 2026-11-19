# Next steps

**M2 is complete.** The stock loader accepted the reviewed temporary image
with both security indicators active. The owner saw the SEC pattern, Android
returned and each of the four boot partition hashes matched on readback.
[Physical evidence](evidence/sec-visual-transfer-20261118.json)

1. Exercise the original DXE graphics driver through UEFI graphics operations
   in emulated RAM. Use asymmetric red and blue test pixels so the channel
   convention is observable.
2. The next physical measurement should distinguish the visible SEC checkpoint
   from a later stage. Establish a bounded stack and a distinguishable signal
   before testing normal memory initialization or DXE on the Go. The first
   color observation did not identify red/blue order.
3. Review a new image and its recovery procedure separately and notify the
   owner before physical work. Both previous one-attempt trials are consumed.
4. Bring up a physical GOP, storage/USB and the required ACPI tables before
   attempting Windows Boot Manager.
