# One bounded EDK2 SEC measurement: review, not an execution result

**Attempt consumed, November 18.** The stock loader accepted the reviewed
temporary image. The commands below describe the protocol used for that
attempt. [Transfer evidence](evidence/sec-visual-transfer-20261118.json)

The October 25 review covers the terminal SEC visual diagnostic. The
[November 18 host revision](evidence/sec-visual-review-20261118.json) pins the
same firmware, image, source audit and model reports. The host parser now
requires both `getvar secure` = `yes` and the OEM `Secure boot` field =
`true` before reserving the attempt. Both responses come from the original
loader and the recorded values describe what it reports. The earlier
[review](evidence/sec-visual-review-20261025.json) records the previous parser.
Both manifests use the same FD-keyed attempt ledger. No attempt has been consumed by
offline validation. The previous project's consumed probe ledger is untouched.

## Why this experiment is bounded

The image contains the newly authored, allowed-source platform. It enters its
actual EDK2 SEC through the integrated header/FV, not a separate BootShim or
the older standalone probe. The opt-in SEC path runs its existing EL/affinity/
MMU/data-cache guards, adds an exact-PC guard, masks interrupts and then writes
only two splash-RAM bands. It loops before stack, C, MMU setup and drivers.
The complete FD remains present in the container, but the diagnostic's normal
control-flow graph cannot dispatch the unused firmware modules.

New static/data review checks the original unit's exact aboot hash and the
runtime-DT reservation; actual instruction/data observations confirm base and
geometry. Byte-for-byte ELF/FD prefix checking decodes 62 instructions, with
no call or indirect branch and only three STRB store sites. Literal reads stay
inside the occupied FD. The only target RAM intervals, exclusive ends, are:

```text
0x836a4000 .. 0x836c5c00
0x83bea000 .. 0x83c0bc00
```

They total 276480 bytes, inside the statically documented splash surface.
No MMIO, bootloader patch, persistent checkpoint, SMC, reset call, GPIO,
clock, PMIC, watchdog or storage sequence is added. The default platform
does not enable this path.

The exact FD passed 12 QEMU cases: eight accepted EL1/EL2 entries varying
I-cache/debug-mask state, and four rejecting enabled D-cache or relocated
entry. Both full bands and boundary sentinels were checked, as were preserved
x0-x3/SP/LR and an untouched stack-record sentinel. The independent
[EL1 translation test](../tests/sec_visual_mmu_el1.py) later exercised the
same FD with the MMU enabled and observed rejection before either band.
Secondary-core execution, Kryo, stage 2 and physical scanout remain outside
this coverage.

Both original-packager outputs have the same SHA-256. Decompression reproduces
the complete 4 MiB FD and exact original EVT DTB; original stock boot hash,
Android header/padding and component identifier are validated. Source audit
found 5 original inputs, 434 EDK2 inputs and 144 generated files, no rejects.

## What remains uncertain

Live handoff, security state, address translation, system-cache coherency,
exception delivery, inherited watchdog and scanout remain UNKNOWN. A new
colored pattern would confirm the bounded path reached the new platform's
SEC stores. No pattern would not distinguish those unknowns. There is no
claim that this redesign diagnoses the earlier static-logo observation.

No physical timer expires the loop. The 20-second host-command timeout only
limits the PC process; it cannot stop code on the visor. Possible outcomes
include a static logo, black screen, lost USB, reboot or a visible pattern.
No known persistent operation is reachable in this diagnostic, but the
stock recovery procedure is not a guarantee against every hardware state.
Hard-brick/EDL recovery is not validated. The battery percentage is not used
as a threshold, at the owner's explicit request.

## Operator and command

On 2026-10-25 the owner revalidated Power-off from Android, physical USB Update
Mode entry, Power-off from that menu and Boot device returning to Android.
The post-recovery readback at 17:34:18 UTC again matched the original boot A/B
and aboot A/B hashes, report SHA-256
`fcc17b0817ffd0e1b6e4db34b77ae37f33c09d7697c0254e41ffdb54e2e9fa9d`.
That report is historical and cannot serve as a current one-hour preflight.

Notify the owner and end the turn before requiring the visor for this new
measurement. Require current presence/observation, fresh read-only integrity
evidence and current Fastboot identity/lock state. Keep buttons released
during transfer. Never select Factory Reset or Sideload Update.

The one native payload command, after those checks, is:

```powershell
fastboot -s <verified-local-serial> boot "C:\Users\Angelo\Documents\Codex\2026-08-24\OculusGo_EDK2_UEFI\local\OculusGo-SEC-VISUAL-20261025-MEASUREMENT.img"
```

```text
Image: 487424 bytes
SHA-256: 07eb55d5ac04c175c5101789672d45e0f584118d7a478898cea7193eefb4be14
FD: 4194304 bytes
SHA-256: 5cd4fc047a44df5f4322fc7634dbcb0a730261d4f94bb881f69382504dc51db0
```

Use the original restricted runner, not an ad-hoc repeat or old runner:

```powershell
# Offline validation only; no device contact and no ledger consumption:
python tools/run_sec_visual_once.py --review docs/evidence/sec-visual-review-20261118.json
# Only in a later, confirmed operator session, with explicit local paths:
python tools/run_sec_visual_once.py --review docs/evidence/sec-visual-review-20261118.json --fastboot '<PINNED-FASTBOOT-EXE>' --expected-serial '<LOCAL-SERIAL>' --preflight '<FRESH-LOCAL-REPORT.json>' --execute --operator-present
```

The runner requires clean committed work and pins artifact/source/report
hashes. It issues only fixed read queries followed by one `boot` command,
reserving an exclusive FD-keyed ledger before sending. Failure, timeout or
no visible pattern does not permit retry, repackaging or a normal-FD fallback.
The generic packager manifest remains an offline record; this separate
review permits only the exact diagnostic measurement under these conditions.

Observe about 15 seconds, recording any white/black/green/magenta bands and
which eye(s). This is a human observation window, not a hardware timeout.
Fastboot OKAY is command acceptance, not SEC execution. Then disconnect USB
and use only Power until off, releasing at off or 20 seconds. If it does not
switch off, stop and report; do not escalate to EDL or persistent operations.
After off, Power + volume down should reach the stock menu as just tested;
Boot device should return to Android. Recheck original hashes afterwards.

This review clears neither the normal FD nor DXE/GOP/Windows execution and
does not change any UNKNOWN hardware claim to CONFIRMED.
