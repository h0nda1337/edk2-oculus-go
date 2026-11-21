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
#if defined (OCULUS_GO_SEC_C)
  // Require the reviewed load location before changing SP or writing RAM.
  adr x15, _ModuleEntryPoint
  ldr x16, =0x80088000
  cmp x15, x16
  b.ne EntryRejected
  msr daifset, #0xf
  mov x12, sp
  // The upper half of the image-header padding belongs to this terminal build.
  // Its upper bound equals FV start; all stack writes are below that address.
  ldr x15, =0x80081000
  mov sp, x15
  stp x0, x1, [sp, #-48]!
  stp x2, x3, [sp, #16]
  stp x12, x30, [sp, #32]
.global SecCCall
SecCCall:
  bl OculusGoSecColorCheckpoint
.global SecCReturn
SecCReturn:
  cmp w0, #1
  ldp x0, x1, [sp]
  ldp x2, x3, [sp, #16]
  ldp x12, x30, [sp, #32]
  mov sp, x12
  b.ne EntryRejected
  dsb sy
.global SecCComplete
SecCComplete:
  b SecCComplete
#elif FixedPcdGetBool (PcdSecVisualDiagnostic)
  // Original terminal SEC measurement, not a bootstrap or the legacy probe.
  // Binary/DT facts and physical limits: docs/SEC_VISUAL_DIAGNOSTIC.md.
  // Reject relocation before the first store. The exact linked entry is
  // independently checked by the diagnostic emulator before any device test.
  adr x15, _ModuleEntryPoint
  ldr x16, =0x80088000
  cmp x15, x16
  b.ne EntryRejected
  msr daifset, #0xf
  mov x14, #2
  ldr x15, =(0x83401000 + 640 * 4320)
SecVisualBand:
  mov x16, #32
SecVisualRow:
  mov x17, #0
SecVisualPixel:
  cmp x17, #360
  b.lo SecVisualWhite
  cmp x17, #720
  b.lo SecVisualBlack
  cmp x17, #1080
  b.lo SecVisualGreen
  // Magenta; all selected colors are invariant to R/B byte-order swapping.
  mov w9, #255
  mov w10, #0
  mov w11, #255
  b SecVisualStore
SecVisualWhite:
  mov w9, #255
  mov w10, #255
  mov w11, #255
  b SecVisualStore
SecVisualBlack:
  mov w9, #0
  mov w10, #0
  mov w11, #0
  b SecVisualStore
SecVisualGreen:
  mov w9, #0
  mov w10, #255
  mov w11, #0
SecVisualStore:
  strb w9, [x15], #1
  strb w10, [x15], #1
  strb w11, [x15], #1
  add x17, x17, #1
  cmp x17, #1440
  b.lo SecVisualPixel
  subs x16, x16, #1
  b.ne SecVisualRow
  subs x14, x14, #1
  b.eq SecVisualDrain
  ldr x15, =(0x83401000 + 1920 * 4320)
  b SecVisualBand
SecVisualDrain:
  dsb sy
.global SecVisualComplete
SecVisualComplete:
  b SecVisualComplete
#endif
#if defined (OCULUS_GO_BOOT_CONSOLE)
  // Compare the actual entry PC with the reset branch in the fixed FV.
  // Until both arena markers and every filler word match, leave SP untouched.
  adr x12, _ModuleEntryPoint
  ldr x15, =FixedPcdGet64 (PcdFvBaseAddress)
  cmp x12, x15
  b.lo EntryRejected
  ldr x16, =FixedPcdGet64 (PcdMemoryPoolBase)
  cmp x12, x16
  b.hs EntryRejected
  ldr w13, [x15]
  lsr w14, w13, #26
  cmp w14, #0x5
  b.ne EntryRejected
  sbfx x13, x13, #0, #26
  add x15, x15, x13, lsl #2
  cmp x12, x15
  b.ne EntryRejected
  // Reject a supplied DTB in the destination before claiming any pages.
  cbz x0, 6f
  ldr x13, =FixedPcdGet64 (PcdFdBaseAddress)
  cmp x0, x13
  b.lo 6f
  ldr x14, =(FixedPcdGet64 (PcdFdBaseAddress) + FixedPcdGet32 (PcdFdSize))
  cmp x0, x14
  b.lo EntryRejected
6:
  ldr x13, [x16], #8
  ldr x14, =0x31414e4552414f47
  cmp x13, x14
  b.ne EntryRejected
  ldr x15, =(FixedPcdGet64 (PcdMemoryPoolBase) + FixedPcdGet32 (PcdMemoryPoolSize) - 4096)
7:
  ldr x13, [x16], #8
  cmn x13, #1
  b.ne EntryRejected
  cmp x16, x15
  b.lo 7b
  ldr x13, [x16], #8
  ldr x14, =0x32414e4552414f47
  cmp x13, x14
  b.ne EntryRejected
  add x15, x15, #4096
8:
  ldr x13, [x16], #8
  cmn x13, #1
  b.ne EntryRejected
  cmp x16, x15
  b.lo 8b
#endif
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
