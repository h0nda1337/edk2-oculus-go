/* Terminal SEC memory handoff measurement. SPDX-License-Identifier: BSD-2-Clause-Patent */
.text
.balign 8
.global _ModuleEntryPoint
.type _ModuleEntryPoint, %function
_ModuleEntryPoint:
  mrs x9, CurrentEL
  cmp x9, #4
  b.eq .Lprimary
  cmp x9, #8
  b.ne SecMemEntryRejected
.Lprimary:
  mrs x10, mpidr_el1
  ldr x11, =0xff00ffffff
  tst x10, x11
  b.ne SecMemEntryRejected
  cmp x9, #8
  b.eq .Lel2
  mrs x11, sctlr_el1
  b .Lstate
.Lel2:
  mrs x11, sctlr_el2
.Lstate:
  tst x11, #1
  b.ne SecMemEntryRejected
  tst x11, #4
  b.ne SecMemEntryRejected
  // GenFv fixes this literal to the final SEC entry in the FD. A relocated
  // copy computes a different PC. The static and QEMU tests check both.
  adr x15, _ModuleEntryPoint
  ldr x16, =_ModuleEntryPoint
  cmp x15, x16
  b.ne SecMemEntryRejected
  mov x16, #0x82000000
  cmp x0, x16
  b.ne SecMemEntryRejected
  msr daifset, #0xf
  adr x15, SecMemVectors
  cmp x9, #8
  b.eq .LvectorEl2
  msr vbar_el1, x15
  b .LvectorsReady
.LvectorEl2:
  msr vbar_el2, x15
.LvectorsReady:
  isb
  mov x12, sp
  ldr x15, =0x80081000
  mov sp, x15
  stp x0, x1, [sp, #-48]!
  stp x2, x3, [sp, #16]
  stp x12, x30, [sp, #32]
  bl OculusGoSecMemValidateFdt
.global SecMemFdtReturn
SecMemFdtReturn:
  tbz w0, #0, .LfdtFailure
  bl SecMemConstructHob
.global SecMemHobReturn
SecMemHobReturn:
  tbz w0, #0, .LhobFailure
  mov w8, #0
  b .Lrestore
.LfdtFailure:
  mov w8, #1
  b .Lrestore
.LhobFailure:
  mov w8, #2
.Lrestore:
  ldp x0, x1, [sp]
  ldp x2, x3, [sp, #16]
  ldp x12, x30, [sp, #32]
  mov sp, x12
  cmp w8, #1
  b.eq SecMemFdtRejected
  cmp w8, #2
  b.eq SecMemHobRejected

  // Sample the first normal HOB address and the normal SEC stack record
  // only after the FDT and in-image HOB checks returned. Neither value
  // controls execution, leaves the CPU, or is written back.
  mov x14, #0x94000000
.global SecMemPoolRead
SecMemPoolRead:
  ldr x9, [x14]
  dsb sy
  ldr x14, =0x97ffffa0
.global SecMemStackRead
SecMemStackRead:
  ldr x9, [x14]
  dsb sy
  mov x9, xzr

.global SecMemPaint
SecMemPaint:
  mov w12, #2
  ldr x15, =0x836a4000
.Lband:
  mov w16, #32
.Lrow:
  mov w6, #0
.Lblock:
  // The two tested scanout bands use packed BGR. All five blocks contain
  // green. Cyan and yellow flank the white center in either orientation.
  mov w9, #255
  mov w10, #255
  mov w11, #0
  cmp w6, #2
  b.eq .Lwhite
  tbz w6, #0, .Ldraw
  mov w9, #0
.Lwhite:
  mov w11, #255
.Ldraw:
  mov w17, #288
.Lpixel:
  strb w9, [x15], #1
  strb w10, [x15], #1
  strb w11, [x15], #1
  subs w17, w17, #1
  b.ne .Lpixel
  add w6, w6, #1
  cmp w6, #5
  b.ne .Lblock
  subs w16, w16, #1
  b.ne .Lrow
  subs w12, w12, #1
  b.eq .Ldrain
  ldr x15, =0x83bea000
  b .Lband
.Ldrain:
  dsb sy
.global SecMemComplete
SecMemComplete:
  b SecMemComplete
.global SecMemEntryRejected
SecMemEntryRejected:
  b SecMemEntryRejected
.global SecMemFdtRejected
SecMemFdtRejected:
  b SecMemFdtRejected
.global SecMemHobRejected
SecMemHobRejected:
  b SecMemHobRejected
.global SecMemException
SecMemException:
  b SecMemException
.ltorg

.balign 2048
.global SecMemVectors
SecMemVectors:
  .rept 16
    b SecMemException
    .space 124
  .endr
