/** Prepare a real, bounded PI handoff while the loaded FD owns the workspace.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiPei.h>
#include <IndustryStandard/PeImage.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/HobLib.h>
#include <Library/PcdLib.h>
#include <Library/PrePiHobListPointerLib.h>
#include <Library/PrePiLib.h>
#include <Trial/DxeLayout.h>
#include "Layout.h"

VOID EFIAPI ProcessLibraryConstructorList (VOID);

typedef struct {
  UINTN TextBase;
  UINTN TextEnd;
  UINTN Entry;
  UINTN Hobs;
} TRIAL_HANDOFF;
STATIC_ASSERT (sizeof (TRIAL_HANDOFF) == 32, "AArch64 handoff ABI");

STATIC BOOLEAN
Erased (UINTN Base, UINTN End)
{
  for (volatile UINT64 *P = (volatile UINT64 *)Base; (UINTN)P < End; ++P) {
    if (*P != MAX_UINT64) {
      return FALSE;
    }
  }
  return TRUE;
}

#ifdef OCULUS_GO_DXE_MEMORY
STATIC __attribute__((noinline)) BOOLEAN
TrialVerifyArenaPattern (UINT64 Mask)
{
  for (UINTN Address = GO_DXE_POOL; Address < GO_DXE_POOL_END; Address += sizeof (UINT64)) {
    if (*(volatile UINT64 *)Address != (Address ^ Mask)) {
      return FALSE;
    }
  }
  return TRUE;
}

STATIC BOOLEAN
QualifyArena (VOID)
{
  UINT64 Mask = 0xa55ac33c5aa53cc3ULL;
  for (UINTN Pass = 0; Pass < 2; ++Pass, Mask = ~Mask) {
    for (UINTN Address = GO_DXE_POOL; Address < GO_DXE_POOL_END; Address += sizeof (UINT64)) {
      *(volatile UINT64 *)Address = Address ^ Mask;
    }
    __asm__ volatile ("dsb sy" ::: "memory");
    if (!TrialVerifyArenaPattern (Mask)) {
      return FALSE;
    }
  }
  for (UINTN Address = GO_DXE_POOL; Address < GO_DXE_POOL_END; Address += sizeof (UINT64)) {
    *(volatile UINT64 *)Address = MAX_UINT64;
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  return Erased (GO_DXE_POOL - EFI_PAGE_SIZE, GO_DXE_POOL_END + EFI_PAGE_SIZE);
}
#endif

STATIC BOOLEAN
CheckPe (UINTN Pe, UINTN End, TRIAL_HANDOFF *Out, UINTN *ExpectedSize)
{
  EFI_IMAGE_DOS_HEADER *Dos = (VOID *)Pe;
  EFI_IMAGE_NT_HEADERS64 *Nt;
  EFI_IMAGE_SECTION_HEADER *Sections;
  UINTN I, Last, ExecStart = 0, ExecEnd = 0;
  if ((Pe & 7) != 0 || !TrialSpan (Pe, sizeof (*Dos), GO_DXE_POOL, End) ||
      Dos->e_magic != EFI_IMAGE_DOS_SIGNATURE || (Dos->e_lfanew & 7) != 0 ||
      Dos->e_lfanew > End - Pe || !TrialSpan (Pe + Dos->e_lfanew, sizeof (*Nt), Pe, End)) {
    return FALSE;
  }
  Nt = (VOID *)(Pe + Dos->e_lfanew);
  if (Nt->Signature != EFI_IMAGE_NT_SIGNATURE || Nt->FileHeader.Machine != IMAGE_FILE_MACHINE_ARM64 ||
      Nt->OptionalHeader.Magic != EFI_IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
      Nt->OptionalHeader.Subsystem != EFI_IMAGE_SUBSYSTEM_EFI_BOOT_SERVICE_DRIVER ||
      Nt->OptionalHeader.SectionAlignment != EFI_PAGE_SIZE ||
      Nt->FileHeader.SizeOfOptionalHeader != sizeof (Nt->OptionalHeader) ||
      Nt->FileHeader.NumberOfSections == 0 || Nt->FileHeader.NumberOfSections > 16 ||
      Nt->OptionalHeader.SizeOfHeaders > End - Pe || Nt->OptionalHeader.SizeOfImage > (GO_DXE_POOL_END - GO_DXE_POOL)/2) {
    return FALSE;
  }
  Sections = (VOID *)(Nt + 1);
  if (!TrialSpan ((UINTN)Sections, Nt->FileHeader.NumberOfSections * sizeof (*Sections),
                  Pe, Pe + Nt->OptionalHeader.SizeOfHeaders)) {
    return FALSE;
  }
  Last = ALIGN_VALUE (Nt->OptionalHeader.SizeOfHeaders, EFI_PAGE_SIZE);
  for (I = 0; I < Nt->FileHeader.NumberOfSections; ++I) {
    EFI_IMAGE_SECTION_HEADER *S = &Sections[I];
    UINTN Rva = S->VirtualAddress;
    UINTN Size = MAX (S->Misc.VirtualSize, S->SizeOfRawData);
    if ((Rva & EFI_PAGE_MASK) != 0 || Rva < Last || !TrialSpan (Rva, Size, 0, Nt->OptionalHeader.SizeOfImage) ||
        (S->SizeOfRawData && !TrialSpan (Pe + S->PointerToRawData, S->SizeOfRawData, Pe, End))) {
      return FALSE;
    }
    Last = ALIGN_VALUE (Rva + Size, EFI_PAGE_SIZE);
    if (S->Characteristics & EFI_IMAGE_SCN_MEM_EXECUTE) {
      if (ExecEnd != 0 || (S->Characteristics & EFI_IMAGE_SCN_MEM_WRITE)) {
        return FALSE;
      }
      ExecStart = Rva;
      ExecEnd = Last;
    }
  }
  if (!TrialSpan (Nt->OptionalHeader.AddressOfEntryPoint, 4, ExecStart, ExecEnd) ||
      Last > Nt->OptionalHeader.SizeOfImage) {
    return FALSE;
  }
  Out->TextBase = ExecStart;
  Out->TextEnd = ExecEnd;
  Out->Entry = Nt->OptionalHeader.AddressOfEntryPoint;
  *ExpectedSize = Nt->OptionalHeader.SizeOfImage;
  return TRUE;
}

BOOLEAN
TrialPrepareDxe (TRIAL_HANDOFF *Out)
{
  CONST EFI_GUID CoreGuid = GO_DXE_CORE_GUID;
  EFI_HOB_HANDOFF_INFO_TABLE *Hob;
  EFI_PEI_FV_HANDLE Inner;
  EFI_PEI_FILE_HANDLE File = NULL;
  EFI_FV_FILE_INFO Info;
  EFI_FIRMWARE_VOLUME_HEADER *Fv;
  VOID *Pe;
  UINTN ExpectedSize;
  UINT64 Base, Size, Entry;

  if (*(volatile UINT64 *)(UINTN)GO_CODE_END != 0x3144464558444f47ULL ||
      !Erased (GO_DXE_POOL - EFI_PAGE_SIZE, GO_DXE_POOL_END + EFI_PAGE_SIZE)) {
    return FALSE;
  }
#ifdef OCULUS_GO_DXE_MEMORY
  if (!QualifyArena ()) {
    return FALSE;
  }
#endif
  Hob = HobConstructor ((VOID *)GO_DXE_POOL, GO_DXE_POOL_END - GO_DXE_POOL,
                        (VOID *)GO_DXE_POOL, (VOID *)GO_DXE_POOL_END);
  if ((UINTN)Hob != GO_DXE_POOL || EFI_ERROR (PrePeiSetHobList (Hob))) {
    return FALSE;
  }
  ProcessLibraryConstructorList ();
  BuildResourceDescriptorHob (EFI_RESOURCE_SYSTEM_MEMORY, EFI_RESOURCE_ATTRIBUTE_PRESENT |
#ifdef OCULUS_GO_DXE_MEMORY
      EFI_RESOURCE_ATTRIBUTE_TESTED |
#endif
      EFI_RESOURCE_ATTRIBUTE_INITIALIZED | EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE,
      GO_DXE_POOL, GO_DXE_POOL_END - GO_DXE_POOL);
#ifdef OCULUS_GO_DXE_GCD
  // Image.c retains the module GUID in the original list until DXE dispatch.
  // Keep its page allocated after GCD copies the list to its new address.
  BuildMemoryAllocationHob (GO_DXE_POOL, EFI_PAGE_SIZE, EfiBootServicesData);
  BuildResourceDescriptorHob (EFI_RESOURCE_MEMORY_RESERVED,
      EFI_RESOURCE_ATTRIBUTE_PRESENT | EFI_RESOURCE_ATTRIBUTE_INITIALIZED | EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE,
      GO_STACK_PAGE, GO_STACK_TOP - GO_STACK_PAGE);
#endif
  BuildStackHob (GO_STACK_PAGE, GO_STACK_TOP - GO_STACK_PAGE);
  BuildCpuHob (32, 0);
  SetBootMode (BOOT_WITH_FULL_CONFIGURATION);
  BuildFvHob (FixedPcdGet64 (PcdFvBaseAddress), FixedPcdGet32 (PcdFvSize));
  TrialPaint (0x0000ff, 0);
  if (EFI_ERROR (DecompressFirstFv ()) || EFI_ERROR (FfsFindNextVolume (1, &Inner)) ||
      !TrialSpan ((UINTN)Inner, sizeof (*Fv), Hob->EfiFreeMemoryTop, GO_DXE_POOL_END)) {
    return FALSE;
  }
  Fv = Inner;
  if (Fv->Signature != EFI_FVH_SIGNATURE ||
      !TrialSpan ((UINTN)Inner, Fv->FvLength, Hob->EfiFreeMemoryTop, GO_DXE_POOL_END) ||
      Fv->HeaderLength < sizeof (*Fv) || Fv->HeaderLength > Fv->FvLength ||
      (Fv->HeaderLength & 1) || CalculateSum16 ((CONST UINT16 *)Fv, Fv->HeaderLength) != 0 ||
      EFI_ERROR (FfsFindNextFile (EFI_FV_FILETYPE_DXE_CORE, Inner, &File)) ||
      EFI_ERROR (FfsGetFileInfo (File, &Info)) || !CompareGuid (&Info.FileName, &CoreGuid) ||
      !TrialSpan ((UINTN)Info.Buffer, Info.BufferSize, (UINTN)Inner, (UINTN)Inner + Fv->FvLength) ||
      EFI_ERROR (FfsFindSectionData (EFI_SECTION_PE32, File, &Pe)) || (UINTN)Pe < (UINTN)Info.Buffer ||
      !CheckPe ((UINTN)Pe, (UINTN)Info.Buffer + Info.BufferSize, Out, &ExpectedSize)) {
    return FALSE;
  }
  TrialPaint (0xffff00, 0);
  if (Hob->EfiFreeMemoryBottom > Hob->EfiFreeMemoryTop ||
      Hob->EfiFreeMemoryTop - Hob->EfiFreeMemoryBottom < ExpectedSize + 2 * EFI_PAGE_SIZE ||
      EFI_ERROR (LoadPeCoffImage (Pe, &Base, &Size, &Entry)) ||
      Size != ExpectedSize || (Base & EFI_PAGE_MASK) != 0 ||
      !TrialSpan (Base, Size, Hob->EfiFreeMemoryTop, GO_DXE_POOL_END) ||
      Entry != Base + Out->Entry || Base + Size > (UINTN)Inner) {
    return FALSE;
  }
  BuildModuleHob (&Info.FileName, Base, ALIGN_VALUE (Size, EFI_PAGE_SIZE), Entry);
  Out->TextBase += Base;
  Out->TextEnd += Base;
  Out->Entry = Entry;
  Out->Hobs = (UINTN)Hob;
  return Erased (GO_DXE_POOL - EFI_PAGE_SIZE, GO_DXE_POOL) &&
         Erased (GO_DXE_POOL_END, GO_DXE_POOL_END + EFI_PAGE_SIZE);
}

VOID
TrialPreBranch (VOID)
{
  TrialPaint (0x00ffff, 0);
}
