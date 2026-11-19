/** Fixed stage-1 workspace inside the physically exercised SEC_STACK range.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Base.h>
#include <Chipset/AArch64Mmu.h>
#include "Layout.h"
#ifdef OCULUS_GO_SEC_DXE
#include <Trial/DxeLayout.h>
#endif

// One root, one L2 and five L3 tables. The second band crosses a 2 MiB
// boundary. The table walker uses physical addresses; the pages holding
// its descriptors are deliberately absent from the CPU's virtual map.
STATIC CONST UINT32 Windows[] = {0x80000000, 0x80400000, 0x83600000, 0x83a00000, 0x83c00000
#ifdef OCULUS_GO_SEC_DXE
  , GO_DXE_POOL
#endif
};
STATIC_ASSERT (ARRAY_SIZE (Windows) + 2 == GO_TABLE_COUNT, "L3 table count");
STATIC_ASSERT (GO_TABLE_BASE + GO_TABLE_COUNT * GO_PAGE_BYTES < GO_STACK_PAGE, "workspace overlap");
STATIC_ASSERT ((GO_BAND_BYTES + GO_PAGE_BYTES - 1) / GO_PAGE_BYTES == GO_BAND_PAGES, "band coverage");

STATIC
UINT64
Descriptor (UINTN Table, UINTN Index, UINTN El, UINTN TextBase, UINTN TextEnd)
{
  UINTN  N;
  UINT64 Address;
  UINT64 Attributes;

  if (Table == 0) {
    return (Index == (GO_CODE_START >> 30)) ? ((GO_TABLE_BASE + GO_PAGE_BYTES) | TT_TYPE_TABLE_ENTRY) : 0;
  }
  if (Table == 1) {
    for (N = 0; N < ARRAY_SIZE (Windows); ++N) {
      if (Index == ((Windows[N] >> 21) & 511)) {
        return (GO_TABLE_BASE + (2 + N) * GO_PAGE_BYTES) | TT_TYPE_TABLE_ENTRY;
      }
    }
    return 0;
  }

  Address = Windows[Table - 2] + Index * GO_PAGE_BYTES;
  Attributes = TT_TYPE_BLOCK_ENTRY_LEVEL3 | TT_AF | TT_SH_INNER_SHAREABLE | TT_ATTR_INDX_MEMORY_NON_CACHEABLE;
  if (((Address >= GO_CODE_START) && (Address < GO_CODE_END)) ||
      ((Address >= TextBase) && (Address < TextEnd))) {
    return Address | Attributes | TT_AP_NO_RO | ((El == 4) ? TT_UXN_MASK : 0);
  }
#ifdef OCULUS_GO_SEC_DXE
  if (((Address >= GO_STACK_PAGE) && (Address < GO_STACK_TOP)) ||
      ((Address >= GO_DXE_POOL) && (Address < GO_DXE_POOL_END)) ||
#else
  if ((Address == GO_STACK_PAGE) ||
#endif
      ((Address >= GO_BAND_ONE) && (Address < GO_BAND_ONE + GO_BAND_BYTES)) ||
      ((Address >= GO_BAND_TWO) && (Address < GO_BAND_TWO + GO_BAND_BYTES))) {
    return Address | Attributes | TT_XN_MASK | ((El == 4) ? TT_PXN_MASK : 0);
  }
  return 0;
}

BOOLEAN
MmuBuildTables (UINTN El
#ifdef OCULUS_GO_SEC_DXE
                , UINTN TextBase, UINTN TextEnd
#endif
                )
{
  volatile UINT64 *Words = (volatile UINT64 *)(UINTN)GO_TABLE_BASE;
  UINTN I;
#ifndef OCULUS_GO_SEC_DXE
  CONST UINTN TextBase = 0, TextEnd = 0;
#endif
  for (I = 0; I < GO_TABLE_COUNT * TT_ENTRY_COUNT; ++I) {
    if (Words[I] != MAX_UINT64) {
      return FALSE;
    }
  }
  for (I = 0; I < GO_TABLE_COUNT * TT_ENTRY_COUNT; ++I) {
    Words[I] = Descriptor (I / TT_ENTRY_COUNT, I % TT_ENTRY_COUNT, El, TextBase, TextEnd);
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  for (I = 0; I < GO_TABLE_COUNT * TT_ENTRY_COUNT; ++I) {
    if (Words[I] != Descriptor (I / TT_ENTRY_COUNT, I % TT_ENTRY_COUNT, El, TextBase, TextEnd)) {
      return FALSE;
    }
  }
  return TRUE;
}
