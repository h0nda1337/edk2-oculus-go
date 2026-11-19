/* QEMU EL1 test fixture. Never linked into the firmware or sent to the Go.
 * SPDX-License-Identifier: BSD-2-Clause-Patent
 */
.text
.global TestStart
TestStart:
  msr daifset, #0xf
  adr x12, IdentityTable
  msr ttbr0_el1, x12
  mov x12, #0x44                 // Attr0: normal, noncacheable.
  msr mair_el1, x12
  // 39-bit TTBR0 VA, 4 KiB granule, inner-shareable walks, TTBR1 disabled,
  // 40-bit output addresses. Translation starts at level 1.
  ldr x12, =0x200803519
  msr tcr_el1, x12
  isb
  tlbi vmalle1
  dsb sy
  isb
  mrs x12, sctlr_el1
  bic x12, x12, #4
  bic x12, x12, #0x1000
  orr x12, x12, #1
  msr sctlr_el1, x12
  isb
  mrs x22, sctlr_el1
  br x20                        // x20 is the reviewed FD's header address.
.ltorg

.balign 4096
IdentityTable:
  .quad 0
  .quad 0x40000701              // Identity map QEMU RAM, 1 GiB per entry.
  .quad 0x80000701              // AF=1, inner shareable, EL1 read/write.
  .zero 4096 - 24
