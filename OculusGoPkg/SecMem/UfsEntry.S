/* Terminal LK snapshot. No driver dispatch. SPDX-License-Identifier: BSD-2-Clause-Patent */
.text
.balign 8
.global _ModuleEntryPoint
.type _ModuleEntryPoint, %function
_ModuleEntryPoint:
  mrs x9, CurrentEL
  cmp x9, #4
  b.eq 1f
  cmp x9, #8
  b.ne UfsStop
  mrs x11, sctlr_el2
  b 2f
1:
  mrs x11, sctlr_el1
2:
  tst x11, #1                     // translation off
  b.ne UfsStop
  tst x11, #4                     // data cache off
  b.ne UfsStop
  mrs x10, mpidr_el1
  ldr x15, =0xff00ffffff
  tst x10, x15
  b.ne UfsStop
  adr x15, _ModuleEntryPoint
  ldr x16, =_ModuleEntryPoint
  cmp x15, x16
  b.ne UfsStop
  mov x15, #0x82000000
  cmp x0, x15
  b.ne UfsStop
  ldr x15, =0x8043e000
  ldr x14, [x15]
  ldr x16, =0x314b434154534f47   // GOSTACK1, inside loaded FD
  cmp x14, x16
  b.ne UfsStop
  ldr x15, =0x8047f000
  ldr x14, [x15]                 // upper guard
  cmn x14, #1
  b.ne UfsStop
  msr daifset, #15
  msr spsel, #1
  mov sp, x15
  adr x15, UfsVectors
  cmp x9, #8
  b.eq 3f
  msr vbar_el1, x15
  b 4f
3:
  msr vbar_el2, x15
4:
  isb
  bl GoUfsSnapshot
.global UfsStop
UfsStop:
  wfe
  b UfsStop

// Only this instruction accesses the whitelisted peripheral registers.
// Return false on a synchronous same-EL data abort precisely at this load.
.global GoUfsRead32
.type GoUfsRead32, %function
GoUfsRead32:
  ldr w2, [x0]
  str w2, [x1]                    // caller's private stack
  mov w0, #1
  ret
UfsFault:
  mov w0, #0
  ret
UfsSync:
  mrs x3, CurrentEL
  cmp x3, #8
  b.eq 5f
  mrs x3, esr_el1
  mrs x4, elr_el1
  b 6f
5:
  mrs x3, esr_el2
  mrs x4, elr_el2
6:
  lsr x3, x3, #26
  cmp w3, #0x25
  b.ne UfsStop
  adr x3, GoUfsRead32
  cmp x4, x3
  b.ne UfsStop
  adr x4, UfsFault
  mrs x3, CurrentEL
  cmp x3, #8
  b.eq 7f
  msr elr_el1, x4
  eret
7:
  msr elr_el2, x4
  eret
.ltorg
.balign 2048
UfsVectors:
  .rept 4
    b UfsStop
    .space 124
  .endr
  b UfsSync                       // synchronous exception at current EL, SPx
  .space 124
  .rept 11
    b UfsStop
    .space 124
  .endr
