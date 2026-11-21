/** QEMU-only experiment on the inherited UFS queues.
    Read the primary GPT header into the stock LK buffer, then restore it.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "UfsGptModel.h"
#include <Library/BaseLib.h>
#include <Uefi.h>
#include <Uefi/UefiGpt.h>

#define LK_CONTROL_DATA  0x918eef80U
#define LUN4_LAST        0x0011ffffU
#define GUARD_WORDS      32U

STATIC BOOLEAN
CheckRange (UINTN Base, CONST UINT32 *Expected, UINTN Count)
{
  for (UINTN I = 0; I < Count; ++I) {
    if (((volatile UINT32 *)Base)[I] != Expected[I]) {
      return FALSE;
    }
  }
  return TRUE;
}

STATIC CONST CHAR8 *
ValidateHeader (UINT32 *Block, UINT32 *HeaderCrc, UINT32 *FullCrc)
{
  EFI_PARTITION_TABLE_HEADER H;
  // Copy to a naturally aligned local structure before interpreting EFI fields.
  for (UINTN I = 0; I < sizeof (H); ++I) {
    ((UINT8 *)&H)[I] = ((UINT8 *)Block)[I];
  }
  *FullCrc = CalculateCrc32 ((UINT8 *)Block, GO_LK_HEADER_SIZE);
  if (H.Header.Signature != EFI_PTAB_HEADER_ID || H.Header.Revision != 0x10000 ||
      H.Header.Reserved != 0 || H.Header.HeaderSize < sizeof (H) || H.Header.HeaderSize > GO_LK_HEADER_SIZE) {
    return "FORMAT";
  }
  Block[4] = 0; // CRC field in the private copy.
  *HeaderCrc = CalculateCrc32 ((UINT8 *)Block, H.Header.HeaderSize);
  if (*HeaderCrc != H.Header.CRC32) {
    return "CRC";
  }
  if (H.MyLBA != 1 || H.AlternateLBA != LUN4_LAST || H.FirstUsableLBA > H.LastUsableLBA ||
      H.LastUsableLBA >= LUN4_LAST || H.PartitionEntryLBA < 2 || H.PartitionEntryLBA >= H.FirstUsableLBA ||
      H.NumberOfPartitionEntries == 0 || H.SizeOfPartitionEntry < sizeof (EFI_PARTITION_ENTRY) ||
      (H.SizeOfPartitionEntry & (H.SizeOfPartitionEntry - 1)) != 0) {
    return "GEOMETRY";
  }
  UINT64 ArrayBytes = (UINT64)H.NumberOfPartitionEntries * H.SizeOfPartitionEntry;
  if (ArrayBytes > (H.FirstUsableLBA - H.PartitionEntryLBA) * GO_LK_HEADER_SIZE) {
    return "GEOMETRY";
  }
  if (*HeaderCrc != 0x4c32247eU || *FullCrc != 0xdf7e0b12U) {
    return "BASELINE";
  }
  return NULL;
}

VOID
GoUfsModelReadPrimary (CONST UINT32 *Original)
{
  UINT32 Before[GUARD_WORDS], After[GUARD_WORDS], Block[GO_LK_HEADER_SIZE / 4];
  UINTN Low = GO_LK_HEADER - sizeof (Before), High = GO_LK_HEADER + GO_LK_HEADER_SIZE;
  volatile UINT32 *Dest = (volatile UINT32 *)(UINTN)GO_LK_HEADER;
  UINT64 Freq;
  __asm__ volatile ("mrs %0, cntfrq_el0" : "=r"(Freq));
  if (Freq == 0 || Freq > 1000000000U) {
    GoUfsHeading ("STOP", "TIMER");
    return;
  }
  for (UINTN I = 0; I < GUARD_WORDS; ++I) {
    if (!GoUfsRead32 (Low + 4 * I, &Before[I]) || !GoUfsRead32 (High + 4 * I, &After[I])) {
      GoUfsHeading ("FAULT", "GUARDS");
      return;
    }
  }
  BOOLEAN Held;
  if (!GoUfsModelTransfer (LK_CONTROL_DATA, FALSE, Freq, &Held)) {
    return;
  }
  GoUfsDraw (0, 4, "ENDS                         ");
  GoUfsDrawHex (5, 4, 0);
  GoUfsDraw (0, 5, "HCRC");
  GoUfsDraw (0, 6, "FULL");
  GoUfsDraw (0, 7, "                             ");
  CONST CHAR8 *Fault = NULL;
  for (UINTN Step = 0; Step < 3; ++Step) {
    BOOLEAN Sector = Step == 2;
    UINTN First = Step == 1 ? ARRAY_SIZE (Block) - 2 : 0;
    UINTN Count = Sector ? ARRAY_SIZE (Block) : 2;
    if (!CheckRange (GO_LK_HEADER, Original, ARRAY_SIZE (Block))) {
      GoUfsHeading ("HOLD", "CHANGED");
      return;
    }
    BOOLEAN Good = GoUfsModelTransfer (GO_LK_HEADER + First * 4, Sector, Freq, &Held);
    if (Held) {
      return;
    }
    if (!CheckRange (Low, Before, GUARD_WORDS) || !CheckRange (High, After, GUARD_WORDS) ||
        !CheckRange (GO_LK_HEADER, Original, First) ||
        !CheckRange (GO_LK_HEADER + 4 * (First + Count), Original + First + Count,
                     ARRAY_SIZE (Block) - First - Count)) {
      GoUfsHeading ("HOLD", "GUARD");
      return;
    }
    if (Sector && Good) {
      for (UINTN I = 0; I < ARRAY_SIZE (Block); ++I) {
        Block[I] = Dest[I];
      }
      UINT32 HeaderCrc = 0, FullCrc = 0;
      Fault = ValidateHeader (Block, &HeaderCrc, &FullCrc);
      GoUfsDrawHex (5, 5, HeaderCrc);
      GoUfsDrawHex (5, 6, FullCrc);
    }
    for (UINTN I = First; I < First + Count; ++I) {
      Dest[I] = Original[I];
    }
    __asm__ volatile ("dsb sy" ::: "memory");
    if (!CheckRange (GO_LK_HEADER, Original, ARRAY_SIZE (Block))) {
      GoUfsHeading ("HOLD", "RESTORE");
      return;
    }
    if (!Good) {
      return;
    }
    if (!Sector) {
      GoUfsDrawHex (5, 4, (1U << (Step + 1)) - 1);
    }
  }
  GoUfsDraw (0, 7, "RAM RESTORED");
  GoUfsHeading (Fault == NULL ? "GPT" : "BAD GPT", Fault == NULL ? "DONE" : Fault);
}
