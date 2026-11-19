# Hardware retained from unit evidence

| Item | Observed value | Status |
| --- | --- | --- |
| Product / DT model | pacific / Oculus Pacific EVT | CONFIRMED-DEVICE |
| SoC | APQ8096pro, Qualcomm platform msm8996 | CONFIRMED-DEVICE |
| SoC ID / revision | 312 (`0x138`), revision 1.1 | CONFIRMED-DEVICE |
| Board IDs | `<1 0>`, `<0x01000001 0>` | CONFIRMED-DEVICE DT |
| PMIC profile | `<0x20009 0x10013 0 0>` | CONFIRMED-DEVICE DT; no PMIC initialization ported |
| CPU | Four Kryo AArch64 cores; parts 0x201 / 0x205 | CONFIRMED-DEVICE |
| CPU affinity values in DT | 0, 1, 0x100, 0x101 | CONFIRMED-DEVICE DT; SEC accepts affinity zero only |
| GPU | Adreno 530 | CONFIRMED-DEVICE; acceleration deferred |
| Storage | UFS, LUN devices sda through sdf | CONFIRMED-DEVICE |
| PSCI | 1.0, SMC conduit | CONFIRMED-DEVICE DT/log; no new physical call made |
| Incoming payload EL, MMU/cache, timer access | Not measured for this implementation | UNKNOWN |
| Inherited display at SEC | The owner saw both marker groups. Blue flanked white and red flanked black in the packed framebuffer, consistent with BGR. | CONFIRMED-DEVICE for byte 0 (blue) and byte 2 (red). Panel scan direction remains UNKNOWN. The later SEC_DXE test confirmed output from early DXE Core. [DXE observation](evidence/sec-dxe-transfer-20261119.json) [Physical record](evidence/sec-c-transfer-20261118.json) |
| Watchdog state at SEC | Not measured | UNKNOWN |

Captures were made during the preceding project, initially 2026-08-24. The
reconstruction reuses measured facts and preserved backups, not its derived
platform code. After offline reconstruction, a read-only ADB session on
2026-10-25 reconfirmed product `pacific`, APQ8096pro, SoC ID 312 and revision
1.1. That session ended after the Android readbacks. The physical display
observation in the table comes from the November 18 SEC experiment.

The official kernel has separate CNC and EVT DT variants. The observed unit
selected APQ8096 Pro EVT ID 312. Do not substitute CNC pinmux/PHY/panel data.
Wi-Fi, Bluetooth, audio, sensors, buttons, regulators and thermal mappings
remain in the original local reconnaissance records; none is enabled in the
new firmware. Consult the unit evidence before implementing their drivers.
