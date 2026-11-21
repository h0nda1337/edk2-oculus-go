/* Host-only board glue for the production UFS 1.1 exchange under QEMU TCG.
 * SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "../OculusGoPkg/SecMem/UfsPanel.h"
#define BOX ((volatile UINT32 *)(UINTN)0x40300000)
#define BAR 0x10000000U
VOID GoUfsModelWindowNop (UINT64 BusBase, UINTN Bytes, UINTN Page);

BOOLEAN GoUfsRead32 (UINTN Addr, UINT32 *Value)
{
  if (Addr >= 0x624000 && Addr < 0x625000) {
    UINTN Off = Addr - 0x624000;
    // QEMU presents a newer PCI HCI and does not implement task-list run.
    if (Off == 0 || Off == 8 || Off == 0x80) {
      *Value = Off == 0 ? 0x0107001f : Off == 8 ? 0x00010100 : 1;
      return TRUE;
    }
    Addr = BAR + Off;
  }
  *Value = *(volatile UINT32 *)Addr;
  return TRUE;
}
VOID GoUfsRingNopSlot (VOID)
{
  BOX[6]++;
  __asm__ volatile ("dsb sy" ::: "memory");
  *(volatile UINT32 *)(UINTN)(BAR + 0x58) = 2;
  __asm__ volatile ("dsb sy" ::: "memory");
}
VOID GoUfsHeading (CONST CHAR8 *State, CONST CHAR8 *Name)
{
  BOX[4] = (UINT8)State[0];
  BOX[5] = (UINT8)Name[0];
}
VOID GoUfsDrawHex (UINTN Col, UINTN Row, UINT32 Value)
{
  if (Row == 4 || Row == 5) BOX[Row+3] = Value;
}
VOID GoUfsDraw (UINTN Col, UINTN Row, CONST CHAR8 *Text)
{
  if (Row == 6 && Text[0] == 'R') BOX[9] = 1;
}
VOID run_guest (VOID)
{
  GoUfsModelWindowNop (BOX[0], BOX[1], BOX[2]);
  __asm__ volatile ("dsb sy" ::: "memory");
  BOX[3] = 0x444f4e45;
  for (;;) __asm__ volatile ("wfe");
}
