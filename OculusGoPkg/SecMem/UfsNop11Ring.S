/* Only peripheral store in the NOP probe: ring transfer slot 1 once.
 * SPDX-License-Identifier: BSD-2-Clause-Patent */
.text
.balign 4
.global GoUfsRingNopSlot
.type GoUfsRingNopSlot, %function
GoUfsRingNopSlot:
  ldr x0, =0x00624058
  mov w1, #2
  dsb sy
  str w1, [x0]
  dsb sy
  ret
.ltorg
