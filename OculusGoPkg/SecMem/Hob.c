/** @file
  Exercise the pinned PI handoff constructor inside the loaded image.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiPei.h>
#include <Library/PrePiLib.h>

// Both ends fall in the unused first image page. The stack grows down
// to HOB_LIMIT and the firmware volume begins at 0x80081000.
#define HOB_BASE  0x80080200U
#define HOB_LIMIT 0x80080800U

STATIC_ASSERT (sizeof (EFI_HOB_HANDOFF_INFO_TABLE) == 56, "Unexpected PI handoff size");
STATIC_ASSERT (sizeof (EFI_HOB_GENERIC_HEADER) == 8, "Unexpected end HOB size");

__attribute__((noinline))
BOOLEAN
SecMemValidateHob (IN CONST volatile EFI_HOB_HANDOFF_INFO_TABLE *Hob)
{
  CONST volatile EFI_HOB_GENERIC_HEADER *End;

  if ((UINTN)Hob != HOB_BASE) {
    return FALSE;
  }
  // Compute the known end address independently. A bad handoff field must
  // never redirect a read to an arbitrary location.
  End = (CONST volatile EFI_HOB_GENERIC_HEADER *)(UINTN)(HOB_BASE + sizeof (*Hob));
  return (Hob->Header.HobType == EFI_HOB_TYPE_HANDOFF) &&
         (Hob->Header.HobLength == sizeof (*Hob)) &&
         (Hob->Header.Reserved == 0) &&
         (Hob->Version == EFI_HOB_HANDOFF_TABLE_VERSION) &&
         (Hob->BootMode == BOOT_WITH_FULL_CONFIGURATION) &&
         (Hob->EfiMemoryTop == HOB_LIMIT) &&
         (Hob->EfiMemoryBottom == HOB_BASE) &&
         (Hob->EfiFreeMemoryTop == HOB_LIMIT) &&
         (Hob->EfiFreeMemoryBottom == (UINTN)(End + 1)) &&
         (Hob->EfiEndOfHobList == (UINTN)End) &&
         (End->HobType == EFI_HOB_TYPE_END_OF_HOB_LIST) &&
         (End->HobLength == sizeof (*End)) &&
         (End->Reserved == 0);
}

BOOLEAN
SecMemConstructHob (VOID)
{
  EFI_HOB_HANDOFF_INFO_TABLE *Hob;

  Hob = HobConstructor ((VOID *)(UINTN)HOB_BASE, HOB_LIMIT - HOB_BASE,
                        (VOID *)(UINTN)HOB_BASE, (VOID *)(UINTN)HOB_LIMIT);
  return SecMemValidateHob (Hob);
}
