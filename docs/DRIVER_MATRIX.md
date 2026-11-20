# Driver matrix

| Hardware | Android/Linux driver | Potential UEFI/Windows driver | Origin | Confidence / status |
| --- | --- | --- | --- | --- |
| ARM CPU/MMU | Official kernel ARM64 | EDK2 ArmPkg | Allowed EDK2 | Direct physical SEC entry observed; establishing translation in the normal firmware remains untested on the unit |
| GICv3 | Official kernel GICv3 | EDK2 ArmGicDxe / Windows ACPI interrupt controller | Allowed EDK2 | Unit DT addresses confirmed; initialization untested |
| Generic timer | Official kernel arch_timer | EDK2 TimerDxe / Windows GTDT | Allowed EDK2 | 19.2 MHz confirmed; delivered EL permissions UNKNOWN |
| UFS | Official kernel Qualcomm UFS | UNKNOWN | No import | No Block I/O driver enabled |
| USB DWC3 | Official kernel Qualcomm/DWC3 | UNKNOWN | No import | No USB controller code enabled |
| Display | Official kernel MDSS/panel | Original InheritedGopDxe | No import | The two-driver DXE profile passed packed BGR fill and readback through the published GOP at EL1 and EL2 in QEMU. The GOP drew the blue/red/yellow/red/blue signal on the physical panel during the attended DXE_GOP trial. [Physical GOP](evidence/dxe-gop-transfer-20261120.json) [Two-driver trial](DXE_GOP.md) · [Physical DXE dispatch](evidence/dxe-dispatch-transfer-20261119.json) [SEC color observation](evidence/sec-c-transfer-20261118.json) · [GOP tests](evidence/gop-bgr-qemu-20261118.json) |
| Adreno 530 | Official kernel KGSL | UNKNOWN | No import | Deferred until framebuffer/GOP |
| Battery, audio, wireless, sensors | Official kernel, per-device evidence needed | UNKNOWN | No import | Deferred |

No binary driver is uploaded or installed. A Windows driver candidate must
match the real block/interface and licensing terms; another Snapdragon device
name alone does not establish compatibility.

### Windows PE ARM64 candidates from Renegade

| Hardware / mode | Windows package examined | Assessment for Pacific EVT |
| --- | --- | --- |
| USB host | MSM8998 `QcXhciFilter8998`, ARM64, model `ACPI\QCOM2430` | UNKNOWN. This is a lower filter on the Microsoft xHCI stack. Compare the controller revision, PHY, ACPI resources and power dependencies before considering a test. |
| USB Type-C controller | MSM8998 `qcusbc8998`, ARM64, model `ACPI\QCOM00D5` | No matching controller established. This package addresses a different function from the host filter. |
| Internal UFS and Adreno 530 | No package verified for either block on APQ8096pro | UNKNOWN. Keep UFS identification separate from Windows driver compatibility. Continue with inherited GOP for the initial display. |

The examined component tree contains AnySoC, MSM8998 and SDM845 groups.
These findings concern Windows Plug and Play after firmware handoff. The
UEFI Shell uses firmware protocols. Package provenance and the exact INF
files are listed in [the reference register](REFERENCES.md#renegade-windows-driver-packages).
