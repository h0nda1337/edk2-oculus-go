# Candidate boot flow

```text
Existing Qualcomm bootloader (unchanged on headset)
  -> temporary Android boot-v0 container, decompressed by existing bootloader
  -> ARM64 header at 0x80080000: B +0x1000
  -> upstream GenFv reset vector in FV at 0x80081000
  -> original OculusGoPkg SEC entry, executing in place
  -> EL / affinity / MMU / data-cache checks before any RAM store
  -> private stack record of incoming x0-x3, SP/LR and architectural state
  -> vectors within the SEC image and upstream ARM architectural routines
  -> HOB construction, original memory-map handoff, upstream EDK2 MMU library
  -> decompression of the inner FV using EDK2 libraries
  -> EDK2 DXE core
  -> TrustMeBro protocol
```

There is no second copy/relocation bootstrap between the bootloader and SEC.
The two branch instructions are the integrated image/FV entry format. They
preserve x0-x3. Unlike the former package, FD and SEC execute where the
bootloader loaded them; the compile-time FD base is therefore `0x80080000`.

Only EL1/EL2 and primary affinity zero are accepted. MMU or data-cache-enabled
entry stops before stack writes. Instruction-cache-enabled entry is allowed
by the official Go kernel ABI and invalidated through EDK2's architectural
routine. This is a documented ABI choice, not evidence of the delivered
physical state. Unaccepted states and exceptions stop in local branch loops.

TrustMeBro is a boot-services-only diagnostic protocol with a revision,
GUID, GetState method and a 96-byte versioned snapshot. It reports DXE only
after validating the SEC-produced HOB. Missing, truncated, incompatible or
incomplete state prevents installation. No storage is written by it.

DebugLib is enabled, but SerialPortLib is the upstream null instance. The
DEBUG message alone does not provide visible output. Display inheritance,
GOP and an accessible physical debug channel still require implementation.
The current FV contains no BDS/Windows boot path or board storage/USB driver.
