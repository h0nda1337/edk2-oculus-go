/** Inspect the retained native slot on Pacific using CPU loads only.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

#define TR           0x918ee400U
#define TM           0x918eec00U
#define HCI          0x00624000U
// Fixed CPU address seen in LK's completed slot during UFS_HEAP4K. Never
// follow a new bus pointer. Read at most the tail of that one RAM page.
#define NATIVE_UCD   0x918fdf00U
#define SAMPLE_BYTES 0x100U
#define FD_PAGE      (GO_QUEUE_WINDOW_START + 0x1000U)

STATIC BOOLEAN
EqualWord (UINTN Address, UINT32 Expected)
{
  UINT32 Value;
  return GoUfsRead32 (Address, &Value) && Value == Expected;
}

STATIC BOOLEAN
Idle (VOID)
{
  return EqualWord (HCI+0x50, TR) && EqualWord (HCI+0x54, 0) &&
         EqualWord (HCI+0x70, TM) && EqualWord (HCI+0x74, 0) &&
         EqualWord (HCI+0x58, 0) && EqualWord (HCI+0x78, 0);
}

STATIC BOOLEAN
Sample (UINTN Base, UINT32 *Words, UINTN Count, BOOLEAN Compare)
{
  for (UINTN I = 0; I < Count; ++I) {
    UINT32 Value;
    if (!GoUfsRead32 (Base + 4*I, &Value) || (Compare && Words[I] != Value)) {
      return FALSE;
    }
    Words[I] = Value;
  }
  return TRUE;
}

STATIC UINT32
Big32 (CONST UINT8 *P)
{
  return ((UINT32)P[0] << 24) | ((UINT32)P[1] << 16) | ((UINT32)P[2] << 8) | P[3];
}

STATIC VOID
Show (UINTN Row, CONST CHAR8 *Label, UINT32 Value)
{
  GoUfsDraw (0, Row, Label);
  GoUfsDrawHex (6, Row, Value);
}

VOID
GoUfsPrdt (UINT64 Tr, UINT64 Tm)
{
  UINT32 Desc[8], Words[SAMPLE_BYTES/4];
  CONST UINT8 *Req = (CONST UINT8 *)Words;
  CONST UINT8 *Rsp = Req + 32;
  UINT32 First = 0;
  UINT64 End = 0, Length = 0;

  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  GoUfsDraw (0, 7, "CPU ONLY");
  if (Tr != TR || Tm != TM || !Idle () || !Sample (TR, Desc, 8, FALSE)) {
    GoUfsHeading ("STOP", "QUEUES");
    return;
  }
  Show (1, "UCD", Desc[4]);
  if (Desc[4] != NATIVE_UCD || Desc[5] != 0) {
    GoUfsHeading ("STOP", "UCD MOVED");
    return;
  }
  UINT32 Count = Desc[7] & 0xffffU;
  UINT32 Offset = (Desc[7] >> 16) * 4;
  Show (2, "NPRD", Count);
  if (!Sample (TR, Desc, 8, TRUE) || !Idle ()) {
    GoUfsHeading ("STOP", "CHANGED");
    return;
  }
  if (Count == 0) {
    GoUfsHeading ("PRDT", "NO DATA");
    return;
  }
  // Native data-in, IOC, completed slot and the reviewed response offset.
  if ((Desc[0] & 0x0fffffffU) != 0x05000000U || (Desc[0] >> 28) > 2 ||
      Desc[2] != 0 || (Desc[6] >> 16) != 8 || (Desc[6] & 0xffffU) < 8 ||
      Offset < 64 || Offset > SAMPLE_BYTES || Count > (SAMPLE_BYTES-Offset)/16) {
    GoUfsHeading ("STOP", "DESCRIPTOR");
    return;
  }

  UINTN Used = Offset/4 + 4*Count;
  if (!Sample (NATIVE_UCD, Words, Used, FALSE) || !Sample (NATIVE_UCD, Words, Used, TRUE) ||
      !Sample (TR, Desc, 8, TRUE) || !Idle ()) {
    GoUfsHeading ("STOP", "CHANGED");
    return;
  }
  UINT8 Op = Req[16];
  Show (3, "OP", Op);
  Show (4, "LUN", Req[2]);
  // Stock LK takes the tag from HBA+0x174, independently of the UTR slot.
  if (Req[0] != 1 || (Req[1] & 0xe0) != 0x40 || Req[2] > 7 ||
      Req[10] != 0 || Req[11] != 0 || Rsp[0] != 0x21 || Rsp[1] != 0 ||
      Rsp[3] != Req[3] || Rsp[6] != 0 || Rsp[7] != 0 || Big32 (Rsp+12) != 0 ||
      (Op != 0x28 && Op != 0x88 && Op != 0x25)) {
    GoUfsHeading ("STOP", "UPIU");
    return;
  }
  for (UINTN I = 0; I < Count; ++I) {
    CONST UINT32 *Entry = &Words[Offset/4 + 4*I];
    UINT32 Bus = Entry[0], Dbc = Entry[3];
    if ((Bus & 3) != 0 || Entry[1] != 0 || Dbc >= 0x40000U ||
        (I != 0 && Bus != End) || (I+1 < Count && Dbc != 0x3ffffU)) {
      GoUfsHeading ("STOP", "ENTRY");
      return;
    }
    if (I == 0) {
      First = Bus;
    }
    Length += Dbc+1U;
    End = (UINT64)Bus + Dbc + 1;
    if (End > 0x100000000ULL) {
      GoUfsHeading ("STOP", "RANGE");
      return;
    }
  }
  if (Length != Big32 (Req+12) || (Op == 0x25 && Length != 8)) {
    GoUfsHeading ("STOP", "LENGTH");
    return;
  }
  if (Op != 0x25) {
    UINT32 Blocks = Op == 0x28 ? ((UINT32)Req[23] << 8) | Req[24] : Big32 (Req+26);
    if (Blocks == 0 || (Req[2] == 4 && Length != (UINT64)Blocks*4096)) {
      GoUfsHeading ("STOP", "BLOCKS");
      return;
    }
  }
  Show (5, "FIRST", First);
  Show (6, "LAST", (UINT32)(End-1));
  // Compare bus numbers only. No PA assertion, dereference or device command.
  if (First <= FD_PAGE && End >= (UINT64)FD_PAGE+4096) {
    GoUfsHeading ("PRDT", "COVERS");
  } else if (First < FD_PAGE+4096 && End > FD_PAGE) {
    GoUfsHeading ("PRDT", "PARTIAL");
  } else {
    GoUfsHeading ("PRDT", "OUTSIDE");
  }
}
