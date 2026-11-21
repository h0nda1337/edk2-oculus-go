/* Host-only QEMU fixture. Run the unmodified Pacific FD at EL1 with its
 * documented GIC IPAs backed by the virt machine's GICv3. Never in a Go FV.
 * SPDX-License-Identifier: BSD-2-Clause-Patent */
.text
.balign 16
.global _start
_start:
  mrs x0, CurrentEL
  cmp x0, #8
  b.ne stopped
  msr daifset, #15
  // The ELF's BSS is zeroed by the QEMU ELF loader.
  adr x0, root
  adr x1, low_l2
  orr x1, x1, #3
  str x1, [x0]
  adr x1, ram_l2
  orr x1, x1, #3
  str x1, [x0, #16]                 // 0x80000000 at L1 index 2

  adr x0, low_l2
  adr x1, dist_l3
  orr x1, x1, #3
  str x1, [x0, #((0x09bc0000 >> 21) * 8)]
  adr x1, redist_l3
  orr x1, x1, #3
  str x1, [x0, #((0x09c00000 >> 21) * 8)]
  // S2 device-nGnRnE, RW, AF, XN, page descriptor.
  ldr x4, =0x400000000004c3
  adr x0, dist_l3
  add x0, x0, #(((0x09bc0000 >> 12) & 511) * 8)
  mov x1, #0x08000000
  mov x2, #16
  bl map_pages
  adr x0, redist_l3
  ldr x1, =0x080a0000
  mov x2, #256
  bl map_pages

  // Identity map normal RAM for the image, scanout and boot DTB. L2 blocks.
  adr x0, ram_l2
  ldr x1, =0x800007fd               // normal WB, RW, inner shareable, AF
  mov x2, #32
1:
  str x1, [x0], #8
  add x1, x1, #0x200000
  subs x2, x2, #1
  b.ne 1b

  dsb sy
  adr x0, root
  msr vttbr_el2, x0
  ldr x0, =0x80023559               // 39-bit IPA, L1, 4 KiB, 40-bit PA
  msr vtcr_el2, x0
  isb
  tlbi vmalls12e1is
  dsb ish
  isb
  // Give EL1 the physical timer and GIC system-register interface. Interrupts
  // are delivered to EL1; QEMU models the backing peripherals.
  mrs x0, cnthctl_el2
  orr x0, x0, #3
  msr cnthctl_el2, x0
  msr cntvoff_el2, xzr
  mrs x0, ICC_SRE_EL2
  orr x0, x0, #1
  orr x0, x0, #8                    // SRE + Enable (no EL1 access trap)
  msr ICC_SRE_EL2, x0
  isb
  ldr x0, =0x80000001               // AArch64 EL1, stage two enabled
  msr hcr_el2, x0
  msr cptr_el2, xzr
  isb
  ldr x0, =0x80080000
  msr elr_el2, x0
  mov x0, #0x3c5
  msr spsr_el2, x0                  // masked EL1h
  ldr x0, =0x82000000               // DTB fixture supplied by QEMU loader
  mov x1, xzr
  mov x2, xzr
  mov x3, xzr
  eret
map_pages:
  orr x3, x1, x4
  str x3, [x0], #8
  add x1, x1, #4096
  subs x2, x2, #1
  b.ne map_pages
  ret
stopped:
  wfe
  b stopped
.ltorg
.bss
.balign 4096
root:      .skip 4096
low_l2:    .skip 4096
ram_l2:    .skip 4096
dist_l3:   .skip 4096
redist_l3: .skip 4096
