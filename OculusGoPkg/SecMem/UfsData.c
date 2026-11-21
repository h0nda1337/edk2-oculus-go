/** Fixed LUN 4 READ CAPACITY(10) on the inherited queues.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsData.h"
#ifdef GO_UFS_GPT_MODEL
#include "UfsGptModel.h"
#endif
#include <IndustryStandard/Scsi.h>

#define TR                  0x918ee400U
#define TM                  0x918eec00U
#define LIST_BYTES          1024U
#define SLOT_OFFSET         32U
#define UCD                 (TM + 640U)
#define RESPONSE            (UCD + 128U)
#define RESPONSE_BYTES      64U
#define PRD                 (UCD + 208U)
#define CONTROL_DATA        (UCD + 256U)
#define WINDOW              GO_QUEUE_WINDOW_START
#define WINDOW_SIZE         (GO_QUEUE_WINDOW_END - WINDOW)
#define PAGE_BYTES          4096U
#define CAPACITY_LAST_LBA   0x0011ffffU
#define CAPACITY_BLOCK_SIZE 4096U
#define BYTE_AT(A)          (*(volatile UINT8 *)(UINTN)(A))
#define WORD_AT(A)          (*(volatile UINT32 *)(UINTN)(A))

STATIC_ASSERT (CONTROL_DATA + 8 <= TM + LIST_BYTES, "control buffer outside task allocation");
STATIC_ASSERT (RESPONSE + RESPONSE_BYTES <= PRD && PRD + 16 <= CONTROL_DATA, "overlapping descriptors");
STATIC_ASSERT (PAGE_BYTES * 4 == WINDOW_SIZE, "expected four pages");

typedef enum { Good, Attention, Bad, Hold } RESULT;

STATIC UINT32
Big32 (UINTN Address)
{
  return ((UINT32)BYTE_AT (Address) << 24) | ((UINT32)BYTE_AT (Address + 1) << 16) |
         ((UINT32)BYTE_AT (Address + 2) << 8) | BYTE_AT (Address + 3);
}

STATIC UINT64
Ticks (VOID)
{
  UINT64 Value;
  __asm__ volatile ("isb; mrs %0, cntpct_el0" : "=r"(Value));
  return Value;
}

STATIC BOOLEAN
InRange (UINTN Address, UINTN Start, UINTN Bytes)
{
  return Address >= Start && Address - Start < Bytes;
}

STATIC UINT8
Mark (UINTN Offset)
{
  return (UINT8)(0x5aU ^ (Offset >> 12) ^ Offset);
}

#ifndef GO_UFS_BOUNCE
STATIC BOOLEAN
CheckWindow (UINTN Destination)
{
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    if (InRange (WINDOW + I, Destination, 8)) {
      continue;
    }
    if (BYTE_AT (WINDOW + I) != Mark (I)) {
      return FALSE;
    }
  }
  return TRUE;
}

#endif

STATIC RESULT
DataIn (UINTN Data, UINT64 Bus, UINT64 Freq, UINT8 *Returned, BOOLEAN PrimaryHeader)
{
  UINT32 OldTr[LIST_BYTES / 4], OldTm[LIST_BYTES / 4];
  UINT32 Request[8] = { 0x01044001U, 0, 0, 0x08000000U, EFI_SCSI_OP_READ_CAPACITY, 0, 0, 0 };
  UINT32 Descriptor[8] = { 0x05000000U, 0, 15, 0, UCD, 0, (32U << 16) | 16, (52U << 16) | 1 };
  UINT32 Region[4] = { (UINT32)Bus, (UINT32)(Bus >> 32), 0, 7 };
  UINTN Bytes = 8;
#ifdef GO_UFS_GPT_MODEL
  if (PrimaryHeader) {
    if (Data != GO_LK_HEADER || Bus != GO_LK_HEADER) {
      return Bad;
    }
    // READ(10), LBA 1, one 4096-byte block. UPIU and CDB fields are big-endian.
    Bytes = GO_LK_HEADER_SIZE;
    Request[3] = 0x00100000U;
    Request[4] = EFI_SCSI_OP_READ10;
    Request[5] = 0x00000100U;
    Request[6] = 1;
    Region[3] = Bytes - 1;
  }
#endif
  if (!GoUfsLkIdle ()) {
    GoUfsHeading ("STOP", "BUSY");
    return Bad;
  }
  for (UINTN I = 0; I < ARRAY_SIZE (OldTr); ++I) {
    if (!GoUfsRead32 (TR + 4 * I, &OldTr[I]) || !GoUfsRead32 (TM + 4 * I, &OldTm[I])) {
      GoUfsHeading ("STOP", "LK RAM");
      return Bad;
    }
  }
  if (!GoUfsLkPrior (OldTr)) {
    GoUfsHeading ("STOP", "PRIOR");
    return Bad;
  }
  for (UINTN I = 0; I < ARRAY_SIZE (OldTr); ++I) {
    if (WORD_AT (TR + 4 * I) != OldTr[I] || WORD_AT (TM + 4 * I) != OldTm[I]) {
      GoUfsHeading ("STOP", "LK CHANGED");
      return Bad;
    }
  }
  for (UINTN I = 0; I < ARRAY_SIZE (Request); ++I) {
    WORD_AT (UCD + I * 4) = Request[I];
    WORD_AT (TR + SLOT_OFFSET + I * 4) = Descriptor[I];
  }
  for (UINTN I = 0; I < RESPONSE_BYTES; ++I) {
    BYTE_AT (RESPONSE + I) = 0xa5;
  }
  for (UINTN I = 0; I < ARRAY_SIZE (Region); ++I) {
    WORD_AT (PRD + I * 4) = Region[I];
  }
  for (UINTN I = 0; I < Bytes; ++I) {
    BYTE_AT (Data + I) = 0xa5;
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  if (!GoUfsLkIdle ()) {
    GoUfsHeading ("HOLD", "PREPARE");
    return Hold;
  }
  for (UINTN I = 0; I < ARRAY_SIZE (Descriptor); ++I) {
    if (WORD_AT (TR + SLOT_OFFSET + 4*I) != Descriptor[I] || WORD_AT (UCD + 4*I) != Request[I]) {
      GoUfsHeading ("HOLD", "DESCRIPTOR");
      return Hold;
    }
  }
  for (UINTN I = 0; I < ARRAY_SIZE (Region); ++I) {
    if (WORD_AT (PRD+4*I) != Region[I]) {
      GoUfsHeading ("HOLD", "PRDT");
      return Hold;
    }
  }
  GoUfsRingNopSlot ();
  UINT64 Start = Ticks ();
  for (UINTN I = 0; ; ++I) {
    UINT32 Db;
    if (!GoUfsRead32 (0x624058, &Db) || (Db & ~2U) != 0) {
      GoUfsHeading ("HOLD", "DOORBELL");
      return Hold;
    }
    if (Db == 0) break;
    if (Ticks () - Start >= Freq || I == 2000000) {
      GoUfsHeading ("HOLD", "TIMEOUT");
      return Hold;
    }
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  UINT32 Ocs = WORD_AT (TR + SLOT_OFFSET + 8);
  UINT8 Sample[8];
  for (UINTN I = 0; I < sizeof (Sample); ++I) {
    Sample[I] = BYTE_AT (Data + I);
  }
  UINT32 Last = Big32 ((UINTN)Sample), Block = Big32 ((UINTN)(Sample + 4));
  UINT8 Status = BYTE_AT (RESPONSE + 7);
#ifndef GO_UFS_GPT_MODEL
  GoUfsDrawHex (5, 3, Ocs);
  GoUfsDrawHex (5, 4, Status);
  GoUfsDrawHex (5, 5, Last);
  GoUfsDrawHex (5, 6, Block);
#endif
  RESULT Result = Bad;
  if (Ocs == 0 && BYTE_AT (RESPONSE) == 0x21 &&
      BYTE_AT (RESPONSE+2) == 4 && BYTE_AT (RESPONSE+3) == 1) {
    UINTN Segment = (BYTE_AT (RESPONSE+10) << 8) | BYTE_AT (RESPONSE+11);
    if (Status == 0 && BYTE_AT (RESPONSE+1) == 0 && BYTE_AT (RESPONSE+6) == 0 &&
        (Segment == 0 || (Segment == 2 && BYTE_AT (RESPONSE+32) == 0 && BYTE_AT (RESPONSE+33) == 0)) &&
        Big32 (RESPONSE+12) == 0 &&
        (PrimaryHeader || (Last == CAPACITY_LAST_LBA && Block == CAPACITY_BLOCK_SIZE))) {
      Result = Good;
    } else if (Status == 2 && BYTE_AT (RESPONSE+6) <= 1 &&
               (BYTE_AT (RESPONSE+1) & ~0x20U) == 0 && Big32 (RESPONSE+12) <= Bytes && Segment >= 16 && Segment <= RESPONSE_BYTES-32 &&
               BYTE_AT (RESPONSE+32) == 0 && BYTE_AT (RESPONSE+33) >= 14 &&
               BYTE_AT (RESPONSE+33) <= Segment-2 && (BYTE_AT (RESPONSE+34) & 0x7f) == 0x70 &&
               (BYTE_AT (RESPONSE+36) & 15) == 6 && BYTE_AT (RESPONSE+46) == 0x29 &&
               BYTE_AT (RESPONSE+47) == 0) {
      Result = Attention;
    }
  }
  if (!GoUfsLkIdle ()) {
    GoUfsHeading ("HOLD", "STATE");
    return Hold;
  }
  Descriptor[2] = Ocs;
  for (UINTN I = 0; I < ARRAY_SIZE (OldTr); ++I) {
    UINTN Off = 4 * I;
    UINT32 WantTr = InRange (Off, SLOT_OFFSET, 32) ? Descriptor[(Off-SLOT_OFFSET)/4] : OldTr[I];
    UINTN Addr = TM + Off;
    UINT32 WantTm = OldTm[I];
    if (InRange (Addr, UCD, 32)) WantTm = Request[(Addr-UCD)/4];
    if (InRange (Addr, PRD, 16)) WantTm = Region[(Addr-PRD)/4];
    if (WORD_AT (TR + Off) != WantTr || (!(InRange (Addr, RESPONSE, RESPONSE_BYTES) ||
        (Data == CONTROL_DATA && InRange (Addr, CONTROL_DATA, 8))) && WORD_AT (Addr) != WantTm)) {
      GoUfsHeading ("HOLD", "GUARD");
      return Hold;
    }
  }
  for (UINTN I = 0; I < ARRAY_SIZE (OldTr); ++I) {
    UINTN Off = I * 4, Addr = TM + Off;
    if (InRange (Off, SLOT_OFFSET, 32)) WORD_AT (TR + Off) = OldTr[I];
    if (InRange (Addr, UCD, 32) || InRange (Addr, RESPONSE, RESPONSE_BYTES) || InRange (Addr, PRD, 16) ||
        (Data == CONTROL_DATA && InRange (Addr, CONTROL_DATA, 8))) WORD_AT (Addr) = OldTm[I];
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  for (UINTN I = 0; I < ARRAY_SIZE (OldTr); ++I) {
    if (WORD_AT (TR + 4*I) != OldTr[I] || WORD_AT (TM + 4*I) != OldTm[I]) {
      GoUfsHeading ("HOLD", "RESTORE");
      return Hold;
    }
  }
  if (Result == Good && Returned != NULL) {
    for (UINTN I = 0; I < sizeof (Sample); ++I) {
      Returned[I] = Sample[I];
    }
  }
  if (Result == Bad) GoUfsHeading ("STOP", PrimaryHeader ? "READ10" : "CAPACITY");
  return Result;
}

STATIC RESULT
ReadGeometry (UINTN Data, UINT64 Bus, UINT64 Freq, UINT8 *Returned)
{
  RESULT Result = DataIn (Data, Bus, Freq, Returned, FALSE);
  if (Result == Attention) {
    Result = DataIn (Data, Bus, Freq, Returned, FALSE);
    if (Result == Attention) GoUfsHeading ("STOP", "ATTENTION");
  }
  return Result;
}

#ifdef GO_UFS_GPT_MODEL
// Only the model SEC exposes this entry. Refuse every other address and CDB.
BOOLEAN
GoUfsModelTransfer (UINTN Address, BOOLEAN Sector, UINT64 Freq, BOOLEAN *Held)
{
  RESULT Result;
  *Held = FALSE;
  if (Sector) {
    if (Address != GO_LK_HEADER) {
      return FALSE;
    }
    Result = DataIn (Address, Address, Freq, NULL, TRUE);
  } else {
    if (Address != CONTROL_DATA && Address != GO_LK_HEADER &&
        Address != GO_LK_HEADER + GO_LK_HEADER_SIZE - 8) {
      return FALSE;
    }
    Result = ReadGeometry (Address, Address, Freq, NULL);
  }
  *Held = Result == Hold;
  return Result == Good;
}
#endif

STATIC UINT64
StartDataPanel (CONST CHAR8 *MaskLabel)
{
  UINT64 Freq;
  __asm__ volatile ("mrs %0, cntfrq_el0" : "=r"(Freq));
  if (Freq == 0 || Freq > 1000000000) {
    GoUfsHeading ("STOP", "TIMER");
    return 0;
  }
  (VOID)Ticks ();
  for (UINTN I = 1; I < 8; ++I) GoUfsDraw (0, I, "                             ");
  GoUfsDraw (0, 1, "LUN4 READ CAPACITY");
  GoUfsDraw (0, 2, MaskLabel);
  GoUfsDrawHex (10, 2, 0);
  GoUfsDraw (0, 3, "OCS");
  GoUfsDraw (0, 4, "SCSI");
  GoUfsDraw (0, 5, "LAST");
  GoUfsDraw (0, 6, "SIZE");
  GoUfsHeading ("DATA", "CONTROL");
  return Freq;
}

#ifndef GO_UFS_BOUNCE
// The QEMU bus fixture supplies the mapping at this ABI boundary.
__attribute__((noipa)) VOID
GoUfsDataWindow (CONST UINT64 BusPages[4])
{
  UINT64 Freq = StartDataPanel ("PAGE MASK");
  if (Freq == 0 || ReadGeometry (CONTROL_DATA, CONTROL_DATA, Freq, NULL) != Good) return;
  if (BusPages == NULL) {
    GoUfsDraw (0, 7, "WINDOW DMA UNTESTED");
    GoUfsHeading ("LK DATA", "DONE");
    return;
  }
  for (UINTN P = 0; P < 4; ++P) {
    if (BusPages[P] == 0 || (BusPages[P] & (PAGE_BYTES-1)) != 0 ||
        BusPages[P] == (TR & ~(PAGE_BYTES-1))) {
      GoUfsHeading ("STOP", "DMA MAP");
      return;
    }
    for (UINTN J = 0; J < P; ++J) {
      if (BusPages[P] == BusPages[J]) {
        GoUfsHeading ("STOP", "DMA ALIAS");
        return;
      }
    }
  }
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    if (BYTE_AT (WINDOW+I) != 0xff) {
      GoUfsHeading ("STOP", "FD DIRTY");
      return;
    }
  }
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) BYTE_AT (WINDOW+I) = Mark (I);
  BOOLEAN Complete = TRUE;
  for (UINTN P = 0; P < 4; ++P) {
    UINTN Offset = (P & 1) ? PAGE_BYTES - 8 : 0;
    UINTN Dest = WINDOW + P*PAGE_BYTES + Offset;
    GoUfsHeading ("DATA", "WINDOW");
    RESULT Result = ReadGeometry (Dest, BusPages[P]+Offset, Freq, NULL);
    if (Result == Hold) return;
    if (!CheckWindow (Dest)) {
      GoUfsHeading ("HOLD", "FD GUARD");
      return;
    }
    for (UINTN I = 0; I < 8; ++I) BYTE_AT (Dest+I) = Mark (Dest+I-WINDOW);
    if (Result != Good) {
      Complete = FALSE;
      break;
    }
    GoUfsDrawHex (10, 2, (1U << (P+1))-1);
  }
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) BYTE_AT (WINDOW+I) = 0xff;
  __asm__ volatile ("dsb sy" ::: "memory");
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    if (BYTE_AT (WINDOW+I) != 0xff) {
      GoUfsHeading ("HOLD", "FD RESTORE");
      return;
    }
  }
  GoUfsDraw (0, 7, "WINDOW RESTORED");
  if (Complete) GoUfsHeading ("FD DATA", "DONE");
}

#else
STATIC BOOLEAN
BounceWindowIntact (CONST UINT8 Samples[4][8], UINTN Completed)
{
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    UINTN Page = I / PAGE_BYTES;
    UINTN Offset = I % PAGE_BYTES;
    UINT8 Expected = Mark (I);
    if (Page < Completed && Offset < 8) {
      Expected = Samples[Page][Offset];
    }
    if (BYTE_AT (WINDOW + I) != Expected) {
      return FALSE;
    }
  }
  return TRUE;
}

// Called only after the last synchronous request has settled and guards matched.
// The host test can observe every sample before the firmware restores the window.
__attribute__((noipa)) STATIC BOOLEAN
RestoreBounceWindow (VOID)
{
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    BYTE_AT (WINDOW + I) = 0xff;
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    if (BYTE_AT (WINDOW + I) != 0xff) {
      return FALSE;
    }
  }
  return TRUE;
}

STATIC VOID
GoUfsBounceWindow (VOID)
{
  UINT8 Samples[4][8];
  UINT64 Freq = StartDataPanel ("COPY MASK");
  if (Freq == 0) {
    return;
  }
  GoUfsDraw (0, 7, "FD DIRECT UNTESTED");
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    if (BYTE_AT (WINDOW + I) != 0xff) {
      GoUfsHeading ("STOP", "FD DIRTY");
      return;
    }
  }
  for (UINTN I = 0; I < WINDOW_SIZE; ++I) {
    BYTE_AT (WINDOW + I) = Mark (I);
  }
  UINTN Page;
  for (Page = 0; Page < 4; ++Page) {
    RESULT Result = ReadGeometry (CONTROL_DATA, CONTROL_DATA, Freq, Samples[Page]);
    if (Result == Hold) {
      return;
    }
    // At device completion only the witnessed LK allocation may have received DMA.
    if (!BounceWindowIntact (Samples, Page)) {
      GoUfsHeading ("HOLD", "FD GUARD");
      return;
    }
    if (Result != Good) {
      break;
    }
    for (UINTN I = 0; I < sizeof (Samples[Page]); ++I) {
      BYTE_AT (WINDOW + Page * PAGE_BYTES + I) = Samples[Page][I];
    }
    if (!BounceWindowIntact (Samples, Page + 1)) {
      GoUfsHeading ("HOLD", "COPY GUARD");
      return;
    }
    GoUfsDrawHex (10, 2, (1U << (Page + 1)) - 1);
  }
  if (!RestoreBounceWindow ()) {
    GoUfsHeading ("HOLD", "FD RESTORE");
  } else if (Page == 4) {
    GoUfsHeading ("LK COPY", "DONE");
  }
}
#endif

VOID
GoUfsDataControl (UINT64 Tr, UINT64 Tm)
{
  if (Tr != TR || Tm != TM) {
    GoUfsHeading ("STOP", "BASE");
    return;
  }
#ifdef GO_UFS_BOUNCE
  GoUfsBounceWindow ();
#else
  GoUfsDataWindow (NULL);
#endif
}
