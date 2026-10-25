# Next steps

Completed offline: standalone EDK2 build; integrated header/FV/SEC checks;
compiler/link-source audit; bounded entry cases; SEC and DXE through working
TrustMeBro in QEMU EL1/EL2; reproducible local Android container roundtrip.

1. Notify the owner and END THE TURN before requiring the physical Go. Do
   not issue ADB/Fastboot or assume connection/physical availability.
2. With the owner present in a later turn, start with read-only identity,
   Android/root state, battery and original-partition-integrity checks. No
   automatic reboot or payload is part of that initial check.
3. Complete a new physical diagnostic review: secure handoff, watchdog,
   exception visibility, load/scratch ranges and current recovery controls.
   Full firmware execution remains gated even though the emulator passes.
4. Once entry is demonstrated, add evidence-backed display inheritance/GOP,
   then storage/USB and maintainable ACPI before Windows loader work.

M2 is physical EDK2 execution, not successful image transfer or emulator
stepping. The old consumed test contract does not authorize another test.
