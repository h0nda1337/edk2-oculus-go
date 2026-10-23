# Driver matrix

| Hardware | Android/Linux driver | Potential UEFI/Windows driver | Origin | Confidence / status |
| --- | --- | --- | --- | --- |
| ARM CPU/MMU | Official kernel ARM64 | EDK2 ArmPkg | Allowed EDK2 | Compiled integration; physical entry UNKNOWN |
| GICv3 | Official kernel GICv3 | EDK2 ArmGicDxe / Windows ACPI interrupt controller | Allowed EDK2 | Unit DT addresses confirmed; initialization untested |
| Generic timer | Official kernel arch_timer | EDK2 TimerDxe / Windows GTDT | Allowed EDK2 | 19.2 MHz confirmed; delivered EL permissions UNKNOWN |
| UFS | Official kernel Qualcomm UFS | UNKNOWN | No import | No Block I/O driver enabled |
| USB DWC3 | Official kernel Qualcomm/DWC3 | UNKNOWN | No import | No USB controller code enabled |
| Display | Official kernel MDSS/panel | Original future GOP | No import | Continued bootloader scanout UNKNOWN |
| Adreno 530 | Official kernel KGSL | UNKNOWN | No import | Deferred until framebuffer/GOP |
| Battery, audio, wireless, sensors | Official kernel, per-device evidence needed | UNKNOWN | No import | Deferred |

No binary driver is uploaded or installed. A Windows driver candidate must
match the real block/interface and licensing terms; another Snapdragon device
name alone does not establish compatibility.
