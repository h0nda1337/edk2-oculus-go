/** Terminal Pacific UFSHCI 1.1 NOP. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

#define HCI        0x00624000U
#define HBA        0x918e3230U
#define TR_LIST    0x918ee400U
#define TM_LIST    0x918eec00U
#define LIST_BYTES 1024U
#define SLOT       1U
#define SLOT_DW    (8U * SLOT)
#define UCD_OFFSET 640U
#define RSP_OFFSET 128U

STATIC_ASSERT ((TM_LIST + UCD_OFFSET) % 128 == 0, "aligned UCD beyond eight task descriptors");
STATIC_ASSERT (UCD_OFFSET + RSP_OFFSET + 32 <= LIST_BYTES, "NOP entirely inside LK allocation");
STATIC_ASSERT ((TR_LIST >> 12) == ((TM_LIST + LIST_BYTES - 1) >> 12), "one witnessed DMA page");

VOID GoUfsRingNopSlot (VOID);

STATIC BOOLEAN
EqualWord (UINTN Address, UINT32 Expected)
{
  UINT32 Value;
  return GoUfsRead32 (Address, &Value) && Value == Expected;
}

STATIC BOOLEAN
Idle (VOID)
{
  UINT32 Status, Interrupts;
  return GoUfsRead32 (HCI + 0x20, &Interrupts) && (Interrupts & 0x00070804U) == 0 &&
         EqualWord (HCI + 8, 0x00010100) && EqualWord (HCI, 0x0107001f) &&
         EqualWord (HCI + 0x34, 1) && GoUfsRead32 (HCI + 0x30, &Status) &&
         Status != MAX_UINT32 && (Status & 0x3f) == 0x0f &&
         EqualWord (HCI + 0x50, TR_LIST) && EqualWord (HCI + 0x54, 0) &&
         EqualWord (HCI + 0x70, TM_LIST) && EqualWord (HCI + 0x74, 0) &&
         EqualWord (HCI + 0x60, 1) && EqualWord (HCI + 0x80, 1) &&
         EqualWord (HBA + 0x168, HBA + 0x168) && EqualWord (HBA + 0x16c, HBA + 0x168) &&
         EqualWord (HBA + 0x170, 0) && EqualWord (HBA + 0x1a8, HBA + 0x1a8) &&
         EqualWord (HBA + 0x1ac, HBA + 0x1a8) && EqualWord (HBA + 0x1b0, 0) &&
         EqualWord (HCI + 0x58, 0) && EqualWord (HCI + 0x78, 0);
}

STATIC BOOLEAN
CompletedSlotZero (CONST UINT32 *Saved)
{
  // The original LK uses slot 0 first. Require a completed, structured
  // descriptor in that allocation before borrowing a different idle slot.
  return (Saved[0] != MAX_UINT32) && (Saved[0] >> 28 <= 2) &&
         Saved[2] == 0 && Saved[4] != 0 && (Saved[4] & 127) == 0 &&
         Saved[5] == 0 && (Saved[6] & 0xffff) != 0 && (Saved[6] >> 16) >= 8;
}

#ifdef GO_UFS_DATA
BOOLEAN GoUfsLkIdle (VOID) { return Idle (); }
BOOLEAN GoUfsLkPrior (CONST UINT32 *Descriptor) { return CompletedSlotZero (Descriptor); }
#else
STATIC VOID
CopyWords (volatile UINT32 *Dest, volatile CONST UINT32 *Src, UINTN Count)
{
  for (UINTN I = 0; I < Count; ++I) {
    Dest[I] = Src[I];
  }
}

STATIC BOOLEAN
SameWords (volatile CONST UINT32 *A, CONST UINT32 *B, UINTN Count)
{
  for (UINTN I = 0; I < Count; ++I) {
    if (A[I] != B[I]) {
      return FALSE;
    }
  }
  return TRUE;
}

STATIC UINT64
Counter (VOID)
{
  UINT64 Ticks;
  __asm__ volatile ("isb; mrs %0, cntpct_el0" : "=r"(Ticks));
  return Ticks;
}

STATIC VOID
Exchange (volatile UINT32 *Ucd, UINT64 UcdBus, BOOLEAN InWindow)
{
  volatile UINT32 *Tr = (volatile UINT32 *)(UINTN)TR_LIST;
  volatile UINT32 *Tm = (volatile UINT32 *)(UINTN)TM_LIST;
  volatile UINT32 *Rsp = Ucd + RSP_OFFSET / 4;
  UINT32 SavedTr[LIST_BYTES / 4], SavedTm[LIST_BYTES / 4], SavedReq[8], SavedRsp[8];
  UINT32 Desc[8] = { 0x21000000, 0, 15, 0, (UINT32)UcdBus, (UINT32)(UcdBus >> 32),
                      ((RSP_OFFSET / 4) << 16) | 8, 0 };
  UINT32 Request[8] = { SLOT << 24 }, InitialRsp[8], Value;
  UINT32 ExpectedHeader = (SLOT << 24) | 0x20;
  UINT64 Freq;
  __asm__ volatile ("mrs %0, cntfrq_el0" : "=r"(Freq));
  if (Freq == 0 || Freq > 1000000000 || !Idle ()) {
    GoUfsHeading ("STOP", "STATE");
    return;
  }
  // Establish that the counter is readable before changing the idle buffers.
  (VOID)Counter ();
  GoUfsHeading ("CHECK", "LK RAM");
  for (UINTN I = 0; I < ARRAY_SIZE (SavedTr); ++I) {
    if (!GoUfsRead32 (TR_LIST + I * 4, &SavedTr[I]) ||
        !GoUfsRead32 (TM_LIST + I * 4, &SavedTm[I])) {
      GoUfsHeading ("FAULT", "LK RAM");
      return;
    }
  }
  if (!CompletedSlotZero (SavedTr)) {
    GoUfsHeading ("STOP", "NO PRIOR OCS");
    return;
  }
  CopyWords (SavedReq, Ucd, 8);
  CopyWords (SavedRsp, Rsp, 8);
  if (!SameWords (Tr, SavedTr, ARRAY_SIZE (SavedTr)) ||
      !SameWords (Tm, SavedTm, ARRAY_SIZE (SavedTm)) || !Idle ()) {
    GoUfsHeading ("STOP", "CHANGED");
    return;
  }
  for (UINTN I = 0; I < 8; ++I) {
    InitialRsp[I] = 0xa5a5a5a5U;
  }
  GoUfsHeading ("PREPARE", "NOP");
  CopyWords (Ucd, Request, 8);
  CopyWords (Rsp, InitialRsp, 8);
  CopyWords (Tr + SLOT_DW, Desc, 8);
  __asm__ volatile ("dsb sy" ::: "memory");

  // If another owner or an unexpected change appears, leave memory resident.
  if (!SameWords (Ucd, Request, 8) || !SameWords (Rsp, InitialRsp, 8) ||
      !SameWords (Tr + SLOT_DW, Desc, 8) || !Idle ()) {
    GoUfsHeading ("HOLD", "PREPARE");
    return;
  }
  GoUfsHeading ("SUBMIT", "NOP");
  GoUfsRingNopSlot ();
  UINT64 Start = Counter ();
  for (UINTN Polls = 0; ; ++Polls) {
    if (!GoUfsRead32 (HCI + 0x58, &Value) || (Value & ~(1U << SLOT)) != 0) {
      GoUfsHeading ("HOLD", "DOORBELL");
      return;
    }
    if (Value == 0) {
      break;
    }
    if (Counter () - Start >= Freq || Polls == 2000000) {
      GoUfsHeading ("HOLD", "TIMEOUT");
      return;
    }
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  UINT32 Ocs = Tr[SLOT_DW + 2];
  UINT32 Reply = Rsp[0];
  GoUfsDraw (0, 4, "OCS");
  GoUfsDrawHex (4, 4, Ocs);
  GoUfsDraw (0, 5, "RSP");
  GoUfsDrawHex (4, 5, Reply);
  BOOLEAN Valid = Ocs == 0 && Reply == ExpectedHeader &&
                  (Rsp[1] & 0x00ff0000U) == 0 && (Rsp[2] & 0xffff0000U) == 0;
  Desc[2] = Ocs;
  if (!Idle () || !SameWords (Ucd, Request, 8) ||
      !SameWords (Tr + SLOT_DW, Desc, 8) ||
      !SameWords (Tr, SavedTr, SLOT_DW) ||
      !SameWords (Tr + SLOT_DW + 8, SavedTr + SLOT_DW + 8, ARRAY_SIZE (SavedTr) - SLOT_DW - 8)) {
    GoUfsHeading ("HOLD", "STATE");
    return;
  }
  // Only the request and response in the idle task-list padding may differ.
  for (UINTN I = 0; I < ARRAY_SIZE (SavedTm); ++I) {
    if (!InWindow && ((I >= UCD_OFFSET/4 && I < UCD_OFFSET/4 + 8) ||
        (I >= (UCD_OFFSET+RSP_OFFSET)/4 && I < (UCD_OFFSET+RSP_OFFSET)/4 + 8))) {
      continue;
    }
    if (Tm[I] != SavedTm[I]) {
      GoUfsHeading ("HOLD", "TASK RAM");
      return;
    }
  }
  CopyWords (Rsp, SavedRsp, 8);
  CopyWords (Ucd, SavedReq, 8);
  CopyWords (Tr + SLOT_DW, SavedTr + SLOT_DW, 8);
  __asm__ volatile ("dsb sy" ::: "memory");
  if (!SameWords (Tr, SavedTr, ARRAY_SIZE (SavedTr)) || !SameWords (Tm, SavedTm, ARRAY_SIZE (SavedTm)) ||
      !SameWords (Ucd, SavedReq, 8) || !SameWords (Rsp, SavedRsp, 8) || !Idle ()) {
    GoUfsHeading ("HOLD", "RESTORE");
    return;
  }
  GoUfsDraw (0, 6, "RAM RESTORED");
  GoUfsHeading (Valid ? "NOP IN" : "BAD", Valid ? "DONE" : "RESPONSE");
}

VOID
GoUfsNop11 (UINT64 Tr, UINT64 Tm)
{
  if (Tr != TR_LIST || Tm != TM_LIST) {
    GoUfsHeading ("STOP", "BASE");
    return;
  }
  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  GoUfsDraw (0, 1, "TAG 01  CT 02");
  GoUfsDraw (0, 2, "UCD");
  GoUfsDrawHex (4, 2, TM_LIST + UCD_OFFSET);
  GoUfsDraw (0, 3, "UTR");
  GoUfsDrawHex (4, 3, TR_LIST + SLOT_DW * 4);
  GoUfsDraw (0, 7, "FD DMA UNTESTED");
  Exchange ((volatile UINT32 *)(UINTN)(TM_LIST + UCD_OFFSET), TM_LIST + UCD_OFFSET, FALSE);
}

#ifdef GO_UFS11_VIRTUAL_MAP
// Model-only entry. The harness establishes a real four-page SMMUv3 mapping.
// No test entry, mapped bus address or runtime override appears in Pacific SEC.
VOID
GoUfsModelWindowNop (UINT64 BusBase, UINTN Bytes, UINTN Page)
{
  if (Bytes != GO_QUEUE_WINDOW_END - GO_QUEUE_WINDOW_START || Page >= 4 ||
      BusBase == 0 || (BusBase & 4095) != 0 || BusBase > MAX_UINT64 - Bytes ||
      (BusBase < TM_LIST + LIST_BYTES && TR_LIST < BusBase + Bytes)) {
    GoUfsHeading ("STOP", "DMA MAP");
    return;
  }
  UINTN Offset = Page * 4096 + 4096 - RSP_OFFSET - 128;
  Exchange ((volatile UINT32 *)(UINTN)(GO_QUEUE_WINDOW_START + Offset), BusBase + Offset, TRUE);
}
#endif
#endif // GO_UFS_DATA
