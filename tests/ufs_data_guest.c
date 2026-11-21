/* ARM64 QEMU board glue, excluded from Pacific SEC. SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "../OculusGoPkg/SecMem/UfsData.h"
#define BOX ((volatile UINT32 *)(UINTN)0x40300000)
#define BAR 0x10000000U

BOOLEAN GoUfsRead32 (UINTN Address, UINT32 *Value)
{
  if (Address >= 0x624000 && Address < 0x625000) {
    UINTN Off = Address - 0x624000;
    if (Off == 0 || Off == 8 || Off == 0x80) {
      *Value = Off == 0 ? 0x0107001f : Off == 8 ? 0x00010100 : 1;
      return TRUE;
    }
    Address = BAR + Off;
  }
  *Value = *(volatile UINT32 *)Address;
  return TRUE;
}

VOID GoUfsRingNopSlot (VOID)
{
  if (BOX[2] < 8) {
    volatile UINT32 *Log = &BOX[48 + 5*BOX[2]];
    volatile UINT32 *Prd = (volatile UINT32 *)(UINTN)(0x918eee80 + 208);
    Log[0] = Prd[0];
    Log[1] = Prd[1];
    Log[2] = Prd[3];
    Log[3] = *(volatile UINT32 *)(UINTN)0x918ee420;
    Log[4] = *(volatile UINT32 *)(UINTN)(0x918eee80 + 16);
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  *(volatile UINT32 *)(UINTN)(BAR + 0x58) = 2;
  __asm__ volatile ("dsb sy" ::: "memory");
  BOX[2]++;
}

VOID GoUfsHeading (CONST CHAR8 *State, CONST CHAR8 *Name)
{
  volatile UINT8 *Out = (volatile UINT8 *)&BOX[16];
  for (UINTN I = 0; I < 32; ++I) Out[I] = 0;
  for (UINTN I = 0; State[I] != 0 && I < 15; ++I) Out[I] = State[I];
  for (UINTN I = 0; Name[I] != 0 && I < 15; ++I) Out[16+I] = Name[I];
}

VOID GoUfsDrawHex (UINTN Col, UINTN Row, UINT32 Value)
{
  if (Row >= 2 && Row <= 6) BOX[4+Row] = Value;
  if (Row == 4) {
    for (UINTN I = 0; I < 16; ++I) BOX[32+I] = ((volatile UINT32 *)(UINTN)0x918eef00)[I];
  }
}

VOID GoUfsDraw (UINTN Col, UINTN Row, CONST CHAR8 *Text) {}

VOID run_guest (VOID)
{
  UINT64 Pages[4];
  for (UINTN P = 0; P < 4; ++P) Pages[P] = BOX[24+P];
  GoUfsDataWindow (BOX[0] ? Pages : NULL);
  __asm__ volatile ("dsb sy" ::: "memory");
  BOX[1] = 0x444f4e45;
  for (;;) __asm__ volatile ("wfe");
}
