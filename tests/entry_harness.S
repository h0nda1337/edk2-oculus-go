/* QEMU-only state setup. Never packaged into the firmware or a device image.
 * SPDX-License-Identifier: BSD-2-Clause-Patent
 */
.text
.global QemuHarnessEl1
.global QemuHarnessEl2
QemuHarnessEl1:
  mrs x17, sctlr_el1
  ldr x19, =0x1005
  bic x17, x17, x19
  orr x17, x17, x18
  msr sctlr_el1, x17
  isb
  br x20
.balign 64
QemuHarnessEl2:
  mrs x17, sctlr_el2
  ldr x19, =0x1005
  bic x17, x17, x19
  orr x17, x17, x18
  msr sctlr_el2, x17
  isb
  br x20
.ltorg
