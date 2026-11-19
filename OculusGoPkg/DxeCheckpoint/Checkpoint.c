/** Terminal debug checkpoint called inside upstream DxeMain. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugAgentLib.h>
#include <Guid/MemoryAllocationHob.h>
#include <Trial/DxeLayout.h>

#ifdef OCULUS_GO_DXE_MEMORY
BOOLEAN TrialMemoryHandoff (EFI_HOB_HANDOFF_INFO_TABLE *Phit);
#endif

STATIC BOOLEAN
CheckHandoff (VOID *Context, UINTN Pc)
{
  CONST EFI_GUID CoreGuid = GO_DXE_CORE_GUID;
  EFI_HOB_HANDOFF_INFO_TABLE *Phit = Context;
  BOOLEAN FoundFv = FALSE, FoundCore = FALSE;
  UINTN Pos, End;

  if ((UINTN)Context != GO_DXE_POOL || Phit->Header.HobType != EFI_HOB_TYPE_HANDOFF ||
      Phit->Header.HobLength != sizeof (*Phit) || Phit->Version != EFI_HOB_HANDOFF_TABLE_VERSION ||
      Phit->EfiMemoryBottom != GO_DXE_POOL || Phit->EfiMemoryTop != GO_DXE_POOL_END ||
      Phit->EfiFreeMemoryBottom > Phit->EfiFreeMemoryTop || Phit->EfiFreeMemoryTop > GO_DXE_POOL_END) {
    return FALSE;
  }
  End = Phit->EfiEndOfHobList;
  if (!TrialSpan (End, sizeof (EFI_HOB_GENERIC_HEADER), GO_DXE_POOL, GO_DXE_POOL_END) ||
      End + sizeof (EFI_HOB_GENERIC_HEADER) != Phit->EfiFreeMemoryBottom) {
    return FALSE;
  }
  for (Pos = GO_DXE_POOL; Pos <= End;) {
    EFI_HOB_GENERIC_HEADER *H = (VOID *)Pos;
    if (Pos == End) {
      return FoundFv && FoundCore && H->HobType == EFI_HOB_TYPE_END_OF_HOB_LIST && H->HobLength == sizeof (*H);
    }
    if (H->HobLength < sizeof (*H) || (H->HobLength & 7) != 0 || H->HobLength > End - Pos) {
      return FALSE;
    }
    if (H->HobType == EFI_HOB_TYPE_FV && H->HobLength == sizeof (EFI_HOB_FIRMWARE_VOLUME)) {
      EFI_HOB_FIRMWARE_VOLUME *Fv = (VOID *)Pos;
      if (TrialSpan (Fv->BaseAddress, Fv->Length, Phit->EfiFreeMemoryTop, GO_DXE_POOL_END)) {
        FoundFv = TRUE;
      }
    }
    if (H->HobType == EFI_HOB_TYPE_MEMORY_ALLOCATION && H->HobLength == sizeof (EFI_HOB_MEMORY_ALLOCATION_MODULE)) {
      EFI_HOB_MEMORY_ALLOCATION_MODULE *M = (VOID *)Pos;
      UINTN Base = M->MemoryAllocationHeader.MemoryBaseAddress, Size = M->MemoryAllocationHeader.MemoryLength;
      if (CompareGuid (&M->ModuleName, &CoreGuid) &&
          CompareGuid (&M->MemoryAllocationHeader.Name, &gEfiHobMemoryAllocModuleGuid) &&
          TrialSpan (Base, Size, Phit->EfiFreeMemoryTop, GO_DXE_POOL_END) &&
          TrialSpan (Pc, 4, Base, Base + Size) && TrialSpan (M->EntryPoint, 4, Base, Base + Size)) {
        FoundCore = TRUE;
      }
    }
    Pos += H->HobLength;
  }
  return FALSE;
}

VOID EFIAPI
InitializeDebugAgent (UINT32 InitFlag, VOID *Context, DEBUG_AGENT_CONTINUE Function)
{
  UINTN Pc;
  __asm__ volatile ("adr %0, ." : "=r"(Pc));
  if (InitFlag == DEBUG_AGENT_INIT_DXE_CORE && Function == NULL && CheckHandoff (Context, Pc)) {
#ifdef OCULUS_GO_DXE_MEMORY
    if (TrialMemoryHandoff (Context)) {
      TrialPaint (0x00ff00, 0xff00ff);
      return;
    }
#else
    TrialPaint (0x00ff00, 0xff00ff);
    __asm__ volatile (".global TrialDxeComplete\nTrialDxeComplete: b TrialDxeComplete");
#endif
  }
  __asm__ volatile (".global TrialDxeRejected\nTrialDxeRejected: b TrialDxeRejected");
}

BOOLEAN EFIAPI
SaveAndSetDebugTimerInterrupt (BOOLEAN EnableStatus)
{
  return FALSE;
}
