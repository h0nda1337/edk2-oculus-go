/** Private FD layout for the terminal SEC_DXE image. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef OCULUS_GO_DXE_TRIAL_H
#define OCULUS_GO_DXE_TRIAL_H
#define GO_DXE_POOL      0x80200000
#define GO_DXE_POOL_END  0x80380000
#define GO_DXE_CORE_GUID {0xd6a2cb7f,0x6a18,0x4e2f,{0xb4,0x3b,0x99,0x20,0xa7,0x33,0x70,0x0a}}

STATIC inline BOOLEAN
TrialSpan (UINTN Start, UINTN Length, UINTN Base, UINTN End)
{
  return (Start >= Base) && (Start < End) && (Length != 0) && (Length <= End - Start);
}

STATIC inline VOID
TrialPaint (UINT32 Side, UINT32 Center)
{
  UINTN Band, Row, Block, X;
  for (Band = 0; Band < 2; ++Band) {
    volatile UINT8 *Pixel = (volatile UINT8 *)(UINTN)((Band == 0) ? 0x836a4000 : 0x83bea000);
    for (Row = 0; Row < 32; ++Row) {
      for (Block = 0; Block < 5; ++Block) {
        UINT32 Color = ((Block == 0) || (Block == 4)) ? 0xffffff : ((Block == 2) ? Center : Side);
        for (X = 0; X < 288; ++X) {
          *Pixel++ = (UINT8)Color;
          *Pixel++ = (UINT8)(Color >> 8);
          *Pixel++ = (UINT8)(Color >> 16);
        }
      }
    }
  }
  __asm__ volatile ("dsb sy" ::: "memory");
}
#endif
