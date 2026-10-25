# Read-only device preflight

This is a separate physical-device session, not part of the completed offline
reconstruction. Notify the owner and end the turn before requiring the Go;
run only after the owner confirms availability in a subsequent turn. Connection
alone does not authorize rebooting or sending a payload.

The original collector uses Python's standard library and a pinned ADB binary.
Its expected serial is required explicitly; do not put the real identifier in
tracked files or command examples. Run from the repository root:

```powershell
$adbPath = (Get-Command adb.exe -ErrorAction Stop).Source
python tools/collect_readonly_preflight.py --adb $adbPath --expected-serial '<LOCAL-SERIAL>' --request-root
```

`--request-root` permits restarting adbd with `adb root` when necessary. It
does not reboot Android. Without the flag, a non-root connection fails closed.
All device commands are scoped to the explicit serial. Identity must match
the authorized ADB listing, reported serial and product `pacific`.

The collector captures Android boot state, battery, SoC identity, cmdline,
ordinary `/proc/iomem`, kernel version and the by-name directory. It does not
read debugfs, tzdbg, pstore or hardware registers. It never invokes reboot,
Fastboot, flashing, erasing, slot selection or a firmware runner.

Only `aboot_a`, `aboot_b`, `boot_a` and `boot_b` are read back. Before each
read, the resolved block node and sector count must match the preserved
inventory. Each read is limited to a known partition of at most 64 MiB and a
60-second subprocess timeout. Complete output length and SHA-256 must match
the original backup; a short read or mismatch is a failure. Partition bytes
are hashed in host memory and are not saved as new images.

Raw captures and the full report stay under ignored `local/`. They contain
identifying information and must not be committed. A reviewed, sanitized
summary can be retained under `docs/evidence/` without device identifiers.

## Recorded result, 2026-10-25

The session starting at 16:41:57 UTC returned `PASS-READONLY`:

- Product `pacific`; root obtained by restarting adbd; Android boot complete.
- Current slot `_a`; APQ8096pro, SoC ID 312, revision 1.1.
- Battery 18/100, USB powered, charging at capture time.
- Complete readbacks of all four allowed partitions matched their original
  backup hashes. This does not verify every partition or rehash every local dump.
- No headset reboot, firmware transfer or partition-write command issued.

The sanitized record is `evidence/readonly-preflight-20261025.json`. The raw
local report is identified there by SHA-256; its contents are not uploaded.
Physical recovery controls were not retested in this session.

`PASS-READONLY` is an integrity/connection observation only. It does not prove
EDK2 execution, reserve memory, validate inherited display/watchdog state or
clear any image for a physical boot. The full candidate remains
NOT-FOR-DEVICE-EXECUTION. Do not perform experimental boots with the recorded
low battery state; charging alone does not satisfy the other review gates.
