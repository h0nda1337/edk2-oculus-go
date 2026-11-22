/** Compare a completed LK response address with the stock allocator's free extents.
    Snapshot only. Do not follow the UCD bus pointer or allocate from this heap.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

#define HEAP_BEGIN   0x918e84acU
#define HEAP_END     0x91c00000U
#define LIST_HEAD    0x918e3170U
#define TR           0x918ee400U
#define TM           0x918eec00U
#define MAX_NODES    256U
#define PAGE_BYTES   4096U
#define HCI          0x624000U

typedef struct {
  UINT32 Address;
  UINT32 Prev;
  UINT32 Next;
  UINT32 Size;
} LK_EXTENT;

STATIC BOOLEAN
ReadEqual (UINT32 Address, UINT32 Expected)
{
  UINT32 Value;
  return GoUfsRead32 (Address, &Value) && Value == Expected;
}

STATIC BOOLEAN
Idle (VOID)
{
  return ReadEqual (HCI+0x50, TR) && ReadEqual (HCI+0x54, 0) &&
         ReadEqual (HCI+0x70, TM) && ReadEqual (HCI+0x74, 0) &&
         ReadEqual (HCI+0x58, 0) && ReadEqual (HCI+0x78, 0);
}

STATIC BOOLEAN
ReadList (LK_EXTENT *Saved, UINT32 *Count, UINT32 *Tail, BOOLEAN Compare)
{
  UINT32 Addr, Last, Prev = LIST_HEAD, End = HEAP_BEGIN, N = 0;
  if (!GoUfsRead32 (LIST_HEAD, &Last) || !GoUfsRead32 (LIST_HEAD+4, &Addr)) {
    return FALSE;
  }
  while (Addr != LIST_HEAD) {
    LK_EXTENT E;
    if (N >= MAX_NODES || (Compare && N >= *Count) || (Addr & 3) != 0 ||
        Addr < End || Addr > HEAP_END-12) {
      return FALSE;
    }
    E.Address = Addr;
    if (!GoUfsRead32 (Addr, &E.Prev) || !GoUfsRead32 (Addr+4, &E.Next) ||
        !GoUfsRead32 (Addr+8, &E.Size) || E.Prev != Prev || E.Size < 12 ||
        E.Size > HEAP_END-Addr || (E.Size & 3) != 0) {
      return FALSE;
    }
    if ((Addr < TR+1024 && TR < Addr+E.Size) || (Addr < TM+1024 && TM < Addr+E.Size)) {
      return FALSE;
    }
    if (Compare && (Saved[N].Address != Addr || Saved[N].Prev != E.Prev ||
                    Saved[N].Next != E.Next || Saved[N].Size != E.Size)) {
      return FALSE;
    }
    Saved[N++] = E;
    Prev = Addr;
    End = Addr + E.Size;
    Addr = E.Next;
  }
  if (Last != Prev || (Compare && (N != *Count || Last != *Tail))) {
    return FALSE;
  }
  *Count = N;
  *Tail = Last;
  return TRUE;
}

VOID
GoUfsHeapPage (UINT64 Tr, UINT64 Tm)
{
  LK_EXTENT Saved[MAX_NODES];
  UINT32 Desc[8], Count = 0, Tail = 0;
  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  GoUfsDraw (0, 7, "CPU ONLY");
  if (Tr != TR || Tm != TM || !Idle ()) {
    GoUfsHeading ("STOP", "QUEUES");
    return;
  }
  for (UINTN I = 0; I < ARRAY_SIZE (Desc); ++I) {
    if (!GoUfsRead32 (TR+4*I, &Desc[I])) {
      GoUfsHeading ("FAULT", "SLOT");
      return;
    }
  }
  UINT32 Base = Desc[4], Offset = (Desc[6] >> 16) * 4, Length = (Desc[6] & 0xffff) * 4;
  if ((Desc[0] & 0x01ffffffU) != 0x01000000U || Desc[0] >> 28 > 2 ||
      Desc[2] != 0 || Desc[5] != 0 || (Base & 127) != 0 ||
      Base < HEAP_BEGIN || Base >= HEAP_END || Offset != 32 || Length < 32 ||
      Offset > HEAP_END-Base || Length > HEAP_END-Base-Offset) {
    GoUfsHeading ("STOP", "SLOT");
    return;
  }
  UINT32 Response = Base+Offset, Page = Response & ~(PAGE_BYTES-1);
  GoUfsDraw (0, 1, "UCD");  GoUfsDrawHex (5, 1, Base);
  GoUfsDraw (0, 2, "RSP");  GoUfsDrawHex (5, 2, Response);
  GoUfsDraw (0, 3, "PAGE"); GoUfsDrawHex (5, 3, Page);
  if (!ReadList (Saved, &Count, &Tail, FALSE) || !ReadList (Saved, &Count, &Tail, TRUE)) {
    GoUfsHeading ("STOP", "HEAP LIST");
    return;
  }
  for (UINTN I = 0; I < ARRAY_SIZE (Desc); ++I) {
    if (!ReadEqual (TR+4*I, Desc[I])) {
      GoUfsHeading ("CHANGED", "SLOT");
      return;
    }
  }
  if (!Idle ()) {
    GoUfsHeading ("CHANGED", "QUEUES");
    return;
  }
  GoUfsDraw (0, 4, "NODES"); GoUfsDrawHex (6, 4, Count);
  if (Page == (TR & ~(PAGE_BYTES-1)) || Page == (TM & ~(PAGE_BYTES-1))) {
    GoUfsHeading ("SHARED", "QUEUE PAGE");
    return;
  }
  for (UINTN I = 0; I < Count; ++I) {
    // Leave all three in-band list words outside the proposed page.
    if (Page >= Saved[I].Address+12 && Page+PAGE_BYTES <= Saved[I].Address+Saved[I].Size) {
      GoUfsDraw (0, 5, "FREE"); GoUfsDrawHex (5, 5, Saved[I].Address);
      GoUfsDraw (0, 6, "END");  GoUfsDrawHex (5, 6, Saved[I].Address+Saved[I].Size);
      GoUfsHeading ("HEAP", "CANDIDATE");
      return;
    }
  }
  GoUfsHeading ("HEAP", "NO PAGE");
}
