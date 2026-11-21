/** Inspect retained LK CPU mappings. All loads are bounded to stock BSS or HCI.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsPanel.h"

// Provenance and stock firmware fingerprint in docs/UFS_LK_DMA.md.
#define LK_HBA      0x918e3230U
#define LK_L1       0x918e4000U
#define LK_HEAP_VA  0x91800000U
#define UFS_HCI     0x00624000U
#define BLOCK_MASK  0xffe00000U

STATIC BOOLEAN
Word (UINTN Address, CONST CHAR8 *Name, UINT32 *Value)
{
  GoUfsHeading ("READ", Name);
  if (!GoUfsRead32 (Address, Value)) {
    GoUfsHeading ("FAULT", Name);
    return FALSE;
  }
  return TRUE;
}

STATIC BOOLEAN
Pair (UINTN Address, CONST CHAR8 *Name, UINT32 *Low, UINT32 *High)
{
  return Word (Address, Name, Low) && Word (Address + 4, Name, High);
}

STATIC VOID
ShowPair (UINTN Row, CONST CHAR8 *Name, UINT32 Low, UINT32 High)
{
  GoUfsDraw (0, Row, Name);
  GoUfsDrawHex (4, Row, High);
  GoUfsDrawHex (13, Row, Low);
}

STATIC BOOLEAN
IdentityBlock (UINT32 Low, UINT32 High, UINT32 Va)
{
  // The Go's LK emits 40-bit output addresses in 2 MiB LPAE blocks. Require
  // AF, type 01, and zero reserved PA bits [47:40] and [20:12].
  return ((Low & 0xfffff403U) == ((Va & BLOCK_MASK) | 0x401U)) &&
         ((High & 0xffffU) == 0);
}

VOID
GoUfsLkMap (UINT64 Tr, UINT64 Tm)
{
  UINT32 First[11], Data[11], Hci[4];
  CONST CHAR8 *Names[] = { "HBA", "UTR", "UTR", "UTM", "UTM" };
  CONST UINT32 Offsets[] = { 4, 0x178, 0x17c, 0x1b8, 0x1bc };
  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  GoUfsDraw (0, 7, "DMA WINDOW UNTESTED");
  for (UINTN Pass = 0; Pass < 2; ++Pass) {
    for (UINTN I = 0; I < ARRAY_SIZE (Offsets); ++I) {
      if (!Word (LK_HBA + Offsets[I], Names[I], &Data[I])) {
        return;
      }
    }
    GoUfsDraw (0, 1, "HBA");
    GoUfsDrawHex (4, 1, Data[0]);
    ShowPair (2, "UTR", Data[1], Data[2]);
    ShowPair (3, "UTM", Data[3], Data[4]);
    if ((Data[0] != UFS_HCI) || (Data[1] != Tr) || (Data[2] != 0) ||
        (Data[3] != Tm) || (Data[4] != 0) ||
        ((Tr & BLOCK_MASK) != LK_HEAP_VA) || ((Tm & BLOCK_MASK) != LK_HEAP_VA)) {
      GoUfsHeading ("MISMATCH", "HBA");
      return;
    }
    // FD and both previously checked list extents lie in L1 index 2.
    if (!Pair (LK_L1 + 2 * 8, "L1", &Data[5], &Data[6])) {
      return;
    }
    ShowPair (4, "L1", Data[5], Data[6]);
    // Restrict the next reads to the three pages in the stock ELF's BSS
    // allocator. An unexpected descriptor is displayed, never followed.
    if ((Data[6] != 0) || ((Data[5] != 0x918e5003U) &&
        (Data[5] != 0x918e6003U) && (Data[5] != 0x918e7003U))) {
      GoUfsHeading ("UNKNOWN", "L1");
      return;
    }
    UINTN Table = Data[5] - 3;
    if (!Pair (Table + ((GO_QUEUE_WINDOW_START >> 21) & 511) * 8, "FD", &Data[7], &Data[8]) ||
        !Pair (Table + ((LK_HEAP_VA >> 21) & 511) * 8, "LK", &Data[9], &Data[10])) {
      return;
    }
    ShowPair (5, "FD", Data[7], Data[8]);
    ShowPair (6, "LK", Data[9], Data[10]);
    for (UINTN I = 0; I < ARRAY_SIZE (First); ++I) {
      if (Pass == 0) {
        First[I] = Data[I];
      } else if (Data[I] != First[I]) {
        GoUfsHeading ("CHANGED", "LK");
        return;
      }
    }
  }
  if (!Pair (UFS_HCI + 0x50, "TRL", &Hci[0], &Hci[1]) ||
      !Pair (UFS_HCI + 0x70, "TML", &Hci[2], &Hci[3])) {
    return;
  }
  if ((Hci[0] != Tr) || (Hci[1] != 0) || (Hci[2] != Tm) || (Hci[3] != 0)) {
    GoUfsHeading ("CHANGED", "HCI");
  } else if (!IdentityBlock (Data[7], Data[8], GO_QUEUE_WINDOW_START)) {
    GoUfsHeading ("UNKNOWN", "FD MAP");
  } else if (!IdentityBlock (Data[9], Data[10], LK_HEAP_VA)) {
    GoUfsHeading ("UNKNOWN", "LK MAP");
  } else {
#ifdef GO_UFS_NOP11
    GoUfsNop11 (Tr, Tm);
#else
    GoUfsHeading ("LK MAP", "MATCH");
#endif
  }
}
