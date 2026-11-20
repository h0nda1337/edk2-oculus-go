/* Original terminal translation and scanout measurement. SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "Layout.h"
.text
.balign 8
.global _ModuleEntryPoint
.type _ModuleEntryPoint, %function
_ModuleEntryPoint:
  mrs x9, CurrentEL
  cmp x9, #4
  b.eq 1f
  cmp x9, #8
  b.ne MmuRejected
1:
  mrs x10, mpidr_el1
  ldr x15, =0xff00ffffff
  tst x10, x15
  b.ne MmuRejected
  cmp x9, #8
  b.eq 2f
  mrs x11, sctlr_el1
  b 3f
2:
  mrs x11, sctlr_el2
3:
  tst x11, #1
  b.ne MmuRejected
  tst x11, #4
  b.ne MmuRejected
  adr x15, _ModuleEntryPoint
  ldr x16, =_ModuleEntryPoint
  cmp x15, x16
  b.ne MmuRejected
  tbnz x11, #25, .Lreject              // Little-endian data and table walks.
  mov x15, #0x82000000
  cmp x0, x15
  b.ne MmuRejected
  msr daifset, #0xf
  mov x19, x9                             // CurrentEL encoding, preserved across C.
  adr x15, MmuVectors
  cmp x19, #8
  b.eq .Lel2vectors
  msr vbar_el1, x15
  b .Lworkspace
.Lel2vectors:
  msr vbar_el2, x15
  isb
  mrs x15, hcr_el2
  tbnz x15, #34, .Lreject              // Profile expects non-VHE EL2.
.Lworkspace:
  isb
  ldr x15, =(GO_TABLE_BASE - GO_PAGE_BYTES)
  ldr x10, [x15]
  ldr x11, =0x314b434154534f47            // GOSTACK1 in this FD.
  cmp x10, x11
  b.ne MmuRejected
  ldr x15, =GO_STACK_PAGE
  ldr x16, =GO_STACK_TOP
.LstackPristine:
  ldr x10, [x15], #8
  cmn x10, #1
  b.ne MmuRejected
  cmp x15, x16
  b.lo .LstackPristine
  mov sp, x16
#ifdef OCULUS_GO_SEC_DXE
  // Reserve the handoff on our known stack across the change of translation.
  sub sp, sp, #32
  mov x20, sp
  bl ArmEnableVFP
  mov x0, x20
  bl TrialPrepareDxe
  cbz w0, .Lreject
  ldp x1, x2, [x20]
#endif
  mov x0, x19
  bl MmuBuildTables
  cbz w0, .Lreject
#ifndef OCULUS_GO_SEC_DXE
  mov w0, #0
  mov w1, #0
  bl MmuSignal
#endif
  dsb sy
.global MmuBeforeEnable
MmuBeforeEnable:
  ldr x10, =GO_TABLE_BASE
  mov x11, #0x4400                       // MAIR Attr1 = Normal NC.
  ic iallu
  dsb sy
  isb
  cmp x19, #8
  b.eq .Lenable2
  ldr x12, =0x80993019                   // TTBR1 disabled, TG1=4 KiB, both TnSZ=25.
  msr mair_el1, x11
  msr tcr_el1, x12
  msr ttbr0_el1, x10
  isb
  tlbi vmalle1
  dsb sy
  isb
  mrs x12, sctlr_el1
  orr x12, x12, #1
  msr sctlr_el1, x12
  isb
  mrs x12, sctlr_el1
  b MmuTranslated
.Lenable2:
  ldr x12, =0x80803019                   // Non-VHE EL2; RES1 bits 31 and 23.
  msr mair_el2, x11
  msr tcr_el2, x12
  msr ttbr0_el2, x10
  isb
  tlbi alle2
  dsb sy
  isb
  mrs x12, sctlr_el2
  orr x12, x12, #1
  msr sctlr_el2, x12
  isb
  mrs x12, sctlr_el2
.global MmuTranslated
MmuTranslated:
  tbz x12, #0, .Lreject
  tbnz x12, #2, .Lreject
  // Validate actual stage-1 writable translations before using the stack
  // or writing pixels. Probe the unmapped guard too. AT never stores data.
  ldr x0, =GO_STACK_TOP
  bl .LtranslateWrite
  tbz x1, #0, .Lreject
  ldr x0, =GO_STACK_PAGE
  mov x2, #((GO_STACK_TOP-GO_STACK_PAGE)/4096)
  bl .LidentityRange
#ifdef OCULUS_GO_DXE_DEBUG
  ldr x0, =GO_DEBUG_PAGE
  mov x2, #1
  bl .LidentityRange
  ldr x0, =(GO_DEBUG_PAGE - GO_PAGE_BYTES)
  bl .LtranslateWrite
  tbz x1, #0, .Lreject
  ldr x0, =(GO_DEBUG_PAGE + GO_PAGE_BYTES)
  bl .LtranslateWrite
  tbz x1, #0, .Lreject
#endif
#ifdef OCULUS_GO_DXE_GOP
  ldr x0, =GO_FB_BASE
  ldr x2, =(GO_FB_SIZE / GO_PAGE_BYTES)
  bl .LidentityRange
  ldr x0, =(GO_FB_BASE - GO_PAGE_BYTES)
  bl .LtranslateWrite
  tbz x1, #0, .Lreject
  ldr x0, =(GO_FB_BASE + GO_FB_SIZE)
  bl .LtranslateWrite
  tbz x1, #0, .Lreject
#else
  ldr x0, =GO_BAND_ONE
  mov x2, #GO_BAND_PAGES
  bl .LidentityRange
  ldr x0, =GO_BAND_TWO
  mov x2, #GO_BAND_PAGES
  bl .LidentityRange
#endif
  ldr x3, =0x534d4d553634434b
  str x3, [sp, #-16]!
  dsb sy
  ldr x4, [sp], #16
  cmp x3, x4
  b.ne MmuRejected
#ifdef OCULUS_GO_SEC_DXE
  bl TrialPreBranch
  ldp x16, x0, [x20, #16]
.global TrialDxeBranch
TrialDxeBranch:
  blr x16
  b MmuRejected
#else
  mov w0, #0
  mov w1, #1
  bl MmuSignal                            // Read entire monochrome pattern back through the MMU.
  cbz w0, .Lreject
.global MmuRepaint
MmuRepaint:
  mov w0, #1
  mov w1, #0
  bl MmuSignal
  dsb sy
  mov w0, #1
  mov w1, #1
  bl MmuSignal
  cbz w0, .Lreject
.global MmuSeal
MmuSeal:
  mov w0, #2                             // Turn the validated black center red.
  mov w1, #0
  bl MmuSignal
  dsb sy
.global MmuComplete
MmuComplete:
  b MmuComplete
#endif

.LidentityRange:
  mov x17, x30
.LnextPage:
  bl .LtranslateWrite
  tbnz x1, #0, .Lreject
  ubfx x3, x1, #12, #36
  cmp x3, x0, lsr #12
  b.ne MmuRejected
  lsr x3, x1, #56
  cmp x3, #0x44
  b.ne MmuRejected
  add x0, x0, #4096
  subs x2, x2, #1
  b.ne .LnextPage
  ret x17
.LtranslateWrite:
  cmp x19, #8
  b.eq .Lat2
  at s1e1w, x0
  b .Lpar
.Lat2:
  at s1e2w, x0
.Lpar:
  isb
  mrs x1, par_el1
  ret
.global MmuRejected, MmuException
.Lreject:
MmuRejected:  b MmuRejected
MmuException: b MmuException
.ltorg

.balign 2048
.global MmuVectors
MmuVectors:
  .rept 16
    b MmuException
    .space 124
  .endr
