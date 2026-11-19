/* Original terminal SEC stack-ownership experiment. SPDX-License-Identifier: BSD-2-Clause-Patent */
.text
.balign 8
.global _ModuleEntryPoint
.type _ModuleEntryPoint, %function
_ModuleEntryPoint:
  mrs x9, CurrentEL
  cmp x9, #4
  b.eq 1f
  cmp x9, #8
  b.ne StackEntryRejected
1:
  mrs x10, mpidr_el1
  ldr x15, =0xff00ffffff
  tst x10, x15
  b.ne StackEntryRejected
  cmp x9, #8
  b.eq 2f
  mrs x11, sctlr_el1
  b 3f
2:
  mrs x11, sctlr_el2
3:
  tst x11, #1
  b.ne StackEntryRejected
  tst x11, #4
  b.ne StackEntryRejected
  adr x15, _ModuleEntryPoint
  ldr x16, =_ModuleEntryPoint
  cmp x15, x16
  b.ne StackEntryRejected
  mov x15, #0x82000000
  cmp x0, x15
  b.ne StackEntryRejected
  mov x28, x30
  mov x27, sp
  mrs x13, daif
  msr daifset, #0xf
  adr x15, StackVectors
  cmp x9, #8
  b.eq 4f
  msr vbar_el1, x15
  b 5f
4:
  msr vbar_el2, x15
5:
  isb
  // Must match the reserved region *outside* FVCOMPACT in this profile.
  ldr x19, =0x8043f000
  ldr x20, =0x8047f000
  bl StackCheckGuards
  mov x4, x19
.Lpristine:
  ldr x6, [x4], #8
  cmn x6, #1
  b.ne StackMemoryRejected
  cmp x4, x20
  b.lo .Lpristine

  // Independent write/read passes. Each 64-bit word encodes its address;
  // the second pass inverts every bit and traverses the words in reverse.
  ldr x7, =0xc35480aa703619dc
  mov x4, x19
.LwriteUp:
  eor x5, x4, x7
  str x5, [x4], #8
  cmp x4, x20
  b.lo .LwriteUp
  dsb sy
.global StackVerifyUp
StackVerifyUp:
  mov x4, x19
.LreadUp:
  eor x5, x4, x7
  ldr x6, [x4], #8
  cmp x6, x5
  b.ne StackMemoryRejected
  cmp x4, x20
  b.lo .LreadUp
  mvn x7, x7
  mov x4, x20
.LwriteDown:
  sub x4, x4, #8
  eor x5, x4, x7
  str x5, [x4]
  cmp x4, x19
  b.hi .LwriteDown
  dsb sy
.global StackVerifyDown
StackVerifyDown:
  mov x4, x20
.LreadDown:
  sub x4, x4, #8
  eor x5, x4, x7
  ldr x6, [x4]
  cmp x6, x5
  b.ne StackMemoryRejected
  cmp x4, x19
  b.hi .LreadDown
  bl StackCheckGuards

  // Normal PrePi's 96-byte entry-state record, now on the tested stack.
  sub x15, x20, #96
  mov sp, x15
  stp x0, x1, [sp, #8]
  stp x2, x3, [sp, #24]
  stp x9, x10, [sp, #40]
  stp x11, x13, [sp, #56]
  stp x27, x28, [sp, #72]
  mov w15, #1
  stp w15, wzr, [sp, #88]
  ldr x15, =0x0060000131424d54
  str x15, [sp]
  mov x0, #3
  bl SecStackFrames
.global StackFramesReturn
StackFramesReturn:
  cbz w0, StackFrameRejected
  add x15, sp, #96
  cmp x15, x20
  b.ne StackFrameRejected
  ldr x14, [sp]
  ldr x15, =0x0060000131424d54
  cmp x14, x15
  b.ne StackFrameRejected
  ldp x12, x14, [sp, #72]
  cmp x12, x27
  b.ne StackFrameRejected
  cmp x14, x28
  b.ne StackFrameRejected
  ldp x0, x1, [sp, #8]
  ldp x2, x3, [sp, #24]
  mov sp, x27
  bl StackCheckGuards
  mov x30, x28

.global StackPaint
StackPaint:
  ldr x15, =0x836a4000
  mov w12, #2
.Lband:
  mov w16, #32
.Lrow:
  mov w4, #0
.Lblock:
  // Packed BGR: green / magenta / white / magenta / green.
  mov w5, #0
  mov w6, #255
  tbz w4, #0, .Leven
  mov w6, #0
  b .Lbright
.Leven:
  cmp w4, #2
  b.ne .Ldraw
.Lbright:
  mov w5, #255
.Ldraw:
  mov w17, #288
.Lpixel:
  strb w5, [x15], #1
  strb w6, [x15], #1
  strb w5, [x15], #1
  subs w17, w17, #1
  b.ne .Lpixel
  add w4, w4, #1
  cmp w4, #5
  b.ne .Lblock
  subs w16, w16, #1
  b.ne .Lrow
  subs w12, w12, #1
  b.eq .Ldrain
  ldr x15, =0x83bea000
  b .Lband
.Ldrain:
  dsb sy
.global StackComplete
StackComplete:
  b StackComplete

// The two 4 KiB guards come from the FD. They are only ever read by SEC.
StackCheckGuards:
  sub x4, x19, #4096
  ldr x5, [x4], #8
  ldr x6, =0x314b434154534f47
  cmp x5, x6
  b.ne StackGuardRejected
.Llower:
  ldr x5, [x4], #8
  cmn x5, #1
  b.ne StackGuardRejected
  cmp x4, x19
  b.lo .Llower
  mov x4, x20
  add x6, x20, #4096
.Lupper:
  ldr x5, [x4], #8
  cmn x5, #1
  b.ne StackGuardRejected
  cmp x4, x6
  b.lo .Lupper
  ret
.global StackEntryRejected, StackMemoryRejected, StackFrameRejected, StackGuardRejected, StackException
StackEntryRejected:  b StackEntryRejected
StackMemoryRejected: b StackMemoryRejected
StackFrameRejected:  b StackFrameRejected
StackGuardRejected:  b StackGuardRejected
StackException:      b StackException
.ltorg

.balign 2048
.global StackVectors
StackVectors:
  .rept 16
    b StackException
    .space 124
  .endr
