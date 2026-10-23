/* Original direct SEC entry for the Go. SPDX-License-Identifier: BSD-2-Clause-Patent */
#include <Library/PcdLib.h>

.text
.balign 8
.global _ModuleEntryPoint
.type _ModuleEntryPoint, %function
_ModuleEntryPoint:
  // Preserve the boot arguments until they have been recorded on our stack.
  mrs x9, CurrentEL
  cmp x9, #4
  b.eq 1f
  cmp x9, #8
  b.ne EntryRejected
1:
  mrs x10, mpidr_el1
  ldr x11, =0xff00ffffff
  tst x10, x11
  b.ne EntryRejected
  cmp x9, #8
  b.eq 2f
  mrs x11, sctlr_el1
  b 3f
2:
  mrs x11, sctlr_el2
3:
  // RAM stores require the inherited MMU and data cache to be disabled.
  // The official Go kernel ABI permits an enabled instruction cache.
  tst x11, #1
  b.ne EntryRejected
  tst x11, #4
  b.ne EntryRejected
  mrs x13, daif
  mov x12, sp
  mov x14, x30
  msr daifset, #0xf
  ldr x15, =(FixedPcdGet64 (PcdMemoryPoolBase) + FixedPcdGet32 (PcdMemoryPoolSize))
  sub x15, x15, #96
  mov sp, x15
  stp x0, x1, [sp, #8]
  stp x2, x3, [sp, #24]
  stp x9, x10, [sp, #40]
  stp x11, x13, [sp, #56]
  stp x12, x14, [sp, #72]
  mov w15, #1
  stp w15, wzr, [sp, #88]
  ldr x15, =0x0060000131424d54
  str x15, [sp]
  dsb sy

  adr x15, EntryVectors
  cmp x9, #8
  b.eq 4f
  msr vbar_el1, x15
  b 5f
4:
  msr vbar_el2, x15
5:
  isb
  // EDK2 supplies the architectural FP/cache routines; no board driver here.
  bl ArmEnableVFP
  bl ArmInvalidateInstructionCache
  bl ArmInvalidateTlb
  mov x29, xzr
  mov x0, sp
  bl OculusGoSecMain

EntryRejected:
  b EntryRejected

.balign 2048
EntryVectors:
  .rept 16
    b EntryException
    .space 124
  .endr
EntryException:
  b EntryException
.ltorg
