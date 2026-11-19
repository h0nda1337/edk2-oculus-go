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

#if defined (OCULUS_GO_SEC_C)
// SEC_C runs before the normal stack, vectors and FP/SIMD setup. Keep this
// leaf independent of the EDK2 C runtime; its exact code is checked offline.
__attribute__((noipa, used, no_stack_protector, target("general-regs-only")))
UINT32
OculusGoSecColorCheckpoint (VOID)
{
  volatile UINT32 Witness;
  volatile UINT8  *Pixel;
  UINTN           Band;
  UINTN           Row;
  UINTN           Block;
  UINTN           Column;
  UINT8           Byte0;
  UINT8           Byte1;
  UINT8           Byte2;

  Witness = 0x43434553U;
  if (Witness != 0x43434553U) {
    return 0;
  }

  // These are the two packed-24-bit spans used by SEC_VISUAL.
  // A white marker is flanked by pure byte 0, a black marker by pure byte 2.
  for (Band = 0; Band < 2; Band++) {
    Pixel = (volatile UINT8 *)(UINTN)(Band == 0 ? 0x836A4000U : 0x83BEA000U);
    for (Row = 0; Row < 32; Row++) {
      for (Block = 0; Block < 6; Block++) {
        Byte0 = (Block <= 2) ? 255 : 0;
        Byte1 = (Block == 1) ? 255 : 0;
        Byte2 = ((Block & 1) != 0) ? 255 : 0;
        for (Column = 0; Column < 240; Column++) {
          Pixel[0] = Byte0;
          Pixel[1] = Byte1;
          Pixel[2] = Byte2;
          Pixel += 3;
        }
      }
    }
  }
  return 1;
}
#endif
