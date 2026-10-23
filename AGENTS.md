# Working rules

Use only original project code, repositories owned by h0nda1337, upstream
TianoCore EDK2, official Oculus Go kernel material and documented drivers.
Read docs/SOURCE_POLICY.md before adding dependencies. Record commit, path,
license and changes for imports. Do not import BootShim or other platform
code under the driver exception. Do not copy the old project's derived SEC
or memory libraries into this reconstruction.

Keep device dumps, DTBs and generated images under ignored local/build paths.
Do not upload them, credentials or device identifiers in routine commits.

The owner requires notification and an ended turn BEFORE any action needing
the physical Oculus Go. Do not issue ADB/Fastboot commands in an offline
development session. Never flash, erase, repartition, change slots or use EDL
without explicit disclosure and separate authorization.

Use small commits and push progress to the existing private origin. Preserve
the previous experimental project's code, backups and consumed-test ledger.
Distinguish source/build/emulator evidence from physical execution.
