# Recovery boundary

No new experimental firmware test has occurred in this reconstruction. Stock
button recovery was revalidated with the owner on 2026-10-25: Power off from
Android, physical Power + volume down entry to USB Update Mode, Power off
from that menu, re-entry and Boot device back to Android. Read-only Android
and Fastboot identity/lock-state checks were also recorded. This is not proof
of recovery from the reconstructed payload. See
`evidence/stock-recovery-session-20261025.json` for scope and raw report hashes.

The previous local project holds original partition dumps and SHA-256
manifests. Do not replace
those originals with regenerated or newly built files.

Historical stock recovery was verified with the owner: long Power switched
off the device, and Power + volume down from off entered USB Update Mode.
Selecting Boot device returned to Android. This describes that observed
recovery, not a guarantee that arbitrary future firmware can be recovered.

Original readback hashes from the previous experiment:

```text
boot_a  cde63f886a379f51d328d7c01a65884ead57bf3b295755f0303e19876ce754be
boot_b  f459689d282d02d0041f219b29b368702ff48fd44032a3ae5e34dcd2ca36fb1a
aboot_a 6a564482e8cd6bbefe662bb76c0b5b24c736ad7804800fa1909f38200c890b74
aboot_b bc6cd8ef0e73798e159c756bacb5a08743d3d67b4dd4534d5b46c3a954030a89
```

Before any future physical step, notify the owner and end the turn as
requested. Require a new assessment of exact image, current device state,
watchdog/debug observability and RAM ranges. The former one-attempt probe
contract is consumed and must not be replayed or edited to bypass its ledger.

Do not touch bootloader, TrustZone, RPM, security, calibration, persist,
partition tables or slot selection as part of this build. No EDL programmer
or hard-brick recovery path is validated. Permanent restoration commands
remain outside the current authorization and must be disclosed individually
with exact partition, original image/hash, risk and recovery route.
