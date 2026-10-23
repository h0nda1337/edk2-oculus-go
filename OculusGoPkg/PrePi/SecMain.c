/** @file
  Original Go SEC coordinator using upstream EDK2 PI services.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiPei.h>
#include <Library/ArmLib.h>
#include <Library/BaseLib.h>
#include <Library/DebugLib.h>
#include <Library/HobLib.h>
#include <Library/PcdLib.h>
#include <Library/PrePiHobListPointerLib.h>
#include <Library/PrePiLib.h>
#include <Protocol/TrustMeBro.h>

VOID EFIAPI ProcessLibraryConstructorList (VOID);
EFI_STATUS OculusGoInitializeMemory (VOID);

STATIC VOID
RequireSuccess (EFI_STATUS Status)
{
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "OculusGo SEC failed: %r\n", Status));
    ASSERT_EFI_ERROR (Status);
    CpuDeadLoop ();
  }
}

VOID
OculusGoSecMain (IN OCULUS_GO_ENTRY_STATE *Entry)
{
  UINTN                       Pool;
  UINTN                       Length;
  UINTN                       Stack;
  EFI_HOB_HANDOFF_INFO_TABLE  *Handoff;
  OCULUS_GO_ENTRY_STATE       *Published;

  Pool   = (UINTN)FixedPcdGet64 (PcdMemoryPoolBase);
  Length = FixedPcdGet32 (PcdMemoryPoolSize);
  Stack  = Pool + Length - FixedPcdGet32 (PcdStackSize);

  Handoff = HobConstructor ((VOID *)Pool, Length, (VOID *)Pool, (VOID *)Stack);
  RequireSuccess (PrePeiSetHobList (Handoff));
  ProcessLibraryConstructorList ();
  Published = BuildGuidDataHob (&gOculusGoEntryHobGuid, Entry, sizeof (*Entry));
  if (Published == NULL) {
    CpuDeadLoop ();
  }

  RequireSuccess (OculusGoInitializeMemory ());
  Published->Phase = OCULUS_GO_PHASE_MMU;
  BuildStackHob (Stack, FixedPcdGet32 (PcdStackSize));
  BuildCpuHob (ArmGetPhysicalAddressBits (), 0);
  SetBootMode (BOOT_WITH_FULL_CONFIGURATION);
  BuildFvHob (FixedPcdGet64 (PcdFvBaseAddress), FixedPcdGet32 (PcdFvSize));
  Published->Phase = OCULUS_GO_PHASE_PRE_DXE;

  DEBUG ((DEBUG_INFO, "TrustMeBro: SEC -> DXE, EL%u\n", Entry->CurrentEl >> 2));
  RequireSuccess (DecompressFirstFv ());
  RequireSuccess (LoadDxeCoreFromFv (NULL, 0));
  CpuDeadLoop ();
}
