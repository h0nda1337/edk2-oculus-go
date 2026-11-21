/** Inspect the retained LK block-read workspace without altering its contents.
    The storage transaction is linked only in the QEMU model.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsHeaderBuffer.h"
#include <Library/BaseLib.h>

STATIC_ASSERT (GO_LK_HEADER + GO_LK_HEADER_SIZE <= 0x918e3230U, "overlap with UFS software context");
STATIC_ASSERT ((GO_LK_HEADER & 127U) == 0, "LK cache-line alignment");

VOID
GoUfsHeaderBuffer (VOID)
{
  UINT32 Words[GO_LK_HEADER_SIZE / sizeof (UINT32)];
  UINT32 Value;
  UINT32 PageSize;

  for (UINTN Row = 1; Row < 8; ++Row) {
    GoUfsDraw (0, Row, "                             ");
  }
  GoUfsDraw (0, 1, "BUF");
  GoUfsDrawHex (5, 1, GO_LK_HEADER);
  GoUfsDraw (0, 2, "LKPG");
  GoUfsDraw (0, 3, "OLD");
  GoUfsDraw (0, 7, "CPU ONLY");
  GoUfsHeading ("READ", "BUF4K");
  if (!GoUfsRead32 (GO_LK_PAGE_WORD, &PageSize)) {
    GoUfsHeading ("FAULT", "LKPG");
    return;
  }
  GoUfsDrawHex (5, 2, PageSize);
  if (PageSize != GO_LK_HEADER_SIZE) {
    GoUfsHeading ("STOP", "LKPG");
    return;
  }

  for (UINTN Pass = 0; Pass < 2; ++Pass) {
    for (UINTN I = 0; I < ARRAY_SIZE (Words); ++I) {
      if (!GoUfsRead32 (GO_LK_HEADER + I * sizeof (UINT32), &Value)) {
        GoUfsHeading ("FAULT", "BUFFER");
        return;
      }
      if (Pass == 0) {
        Words[I] = Value;
      } else if (Value != Words[I]) {
        GoUfsHeading ("CHANGED", "BUFFER");
        return;
      }
    }
    if (!GoUfsRead32 (GO_LK_PAGE_WORD, &Value) || Value != PageSize) {
      GoUfsHeading ("CHANGED", "LKPG");
      return;
    }
  }

  UINT32 Crc = CalculateCrc32 ((UINT8 *)Words, sizeof (Words));
  GoUfsDrawHex (5, 3, Crc);
  BOOLEAN Android = Words[0] == 0x52444e41U && Words[1] == 0x2144494fU && Words[9] == PageSize;
  CONST CHAR8 *Kind = "OTHER";
  if (Android && Crc == 0x90c8cea7U) {
    Kind = "BOOT A";
  } else if (Android && Crc == 0x890f078cU) {
    Kind = "BOOT B";
  } else if (Android) {
    Kind = "ANDROID";
  }
  GoUfsDraw (0, 4, Kind);
#ifdef GO_UFS_GPT_MODEL
  if (Android && (Crc == 0x90c8cea7U || Crc == 0x890f078cU)) {
    GoUfsModelReadPrimary (Words);
  } else {
    GoUfsHeading ("STOP", "ORIGINAL");
  }
#else
  GoUfsDraw (0, 6, "TWO SAMPLES MATCH");
  GoUfsHeading ("BUF4K", "DONE");
#endif
}
