/** DXE_MEM terminal probe, entered by DxeMain after it creates its service tables.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Trial/DxeLayout.h>

extern EFI_SYSTEM_TABLE   *gDxeCoreST;
extern EFI_BOOT_SERVICES   mBootServices;

STATIC UINTN mFreeBase;
STATIC UINTN mFreeEnd;
#define TRIAL_PAGES  2
#define TRIAL_BYTES  257

// The debug callback has already checked the structural HOB bounds and module identity.
BOOLEAN
TrialMemoryHandoff (EFI_HOB_HANDOFF_INFO_TABLE *Phit)
{
  UINTN Low = ALIGN_VALUE (Phit->EfiFreeMemoryBottom, EFI_PAGE_SIZE);
  UINTN High = Phit->EfiFreeMemoryTop;
  UINTN Resources = 0;
  if (Low < GO_DXE_POOL || High > GO_DXE_POOL_END || Low >= High || (High & EFI_PAGE_MASK) ||
      High - Low < 0x20000) {
    return FALSE;
  }
  for (UINTN P = (UINTN)Phit; P < Phit->EfiEndOfHobList;) {
    EFI_HOB_GENERIC_HEADER *H = (VOID *)P;
    if (H->HobType == EFI_HOB_TYPE_RESOURCE_DESCRIPTOR) {
      EFI_HOB_RESOURCE_DESCRIPTOR *R = (VOID *)P;
      if (H->HobLength != sizeof (*R) || R->ResourceType != EFI_RESOURCE_SYSTEM_MEMORY ||
          R->PhysicalStart != GO_DXE_POOL || R->ResourceLength != GO_DXE_POOL_END - GO_DXE_POOL ||
          R->ResourceAttribute != (EFI_RESOURCE_ATTRIBUTE_PRESENT | EFI_RESOURCE_ATTRIBUTE_INITIALIZED |
                                   EFI_RESOURCE_ATTRIBUTE_TESTED | EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE)) {
        return FALSE;
      }
      ++Resources;
    }
    if (H->HobType == EFI_HOB_TYPE_MEMORY_ALLOCATION) {
      EFI_HOB_MEMORY_ALLOCATION *M = (VOID *)P;
      if (H->HobLength < sizeof (*M)) {
        return FALSE;
      }
      UINTN Start = M->AllocDescriptor.MemoryBaseAddress;
      UINTN Size = M->AllocDescriptor.MemoryLength;
      if (Size == 0 || Size > MAX_UINTN - Start || (Start < High && Start + Size > Low)) {
        return FALSE;
      }
    }
    P += H->HobLength;
  }
  if (Resources != 1) {
    return FALSE;
  }
  mFreeBase = Low;
  mFreeEnd = High;
  return TRUE;
}

STATIC BOOLEAN
CheckMap (EFI_BOOT_SERVICES *Bs, UINTN Pages, UINT32 ExpectedType, UINTN *Key)
{
  UINT64 Buffer[256];
  UINTN Size = sizeof (Buffer), Stride = 0, Sum = 0;
  UINT32 Version = 0;
  BOOLEAN Found = FALSE;
  if (Bs->GetMemoryMap (&Size, (EFI_MEMORY_DESCRIPTOR *)Buffer, Key, &Stride, &Version) != EFI_SUCCESS ||
      Stride < sizeof (EFI_MEMORY_DESCRIPTOR) || (Stride & 7) || Size == 0 || Size > sizeof (Buffer) ||
      Size % Stride != 0 || Version != EFI_MEMORY_DESCRIPTOR_VERSION) {
    return FALSE;
  }
  for (UINTN Off = 0; Off < Size; Off += Stride) {
    EFI_MEMORY_DESCRIPTOR *D = (VOID *)((UINT8 *)Buffer + Off);
    if (D->NumberOfPages > (mFreeEnd-mFreeBase)/EFI_PAGE_SIZE || (D->PhysicalStart & EFI_PAGE_MASK)) {
      return FALSE;
    }
    UINTN Length = EFI_PAGES_TO_SIZE (D->NumberOfPages);
    if (!TrialSpan (D->PhysicalStart, Length, mFreeBase, mFreeEnd)) {
      return FALSE;
    }
    UINTN End = D->PhysicalStart + Length;
    for (UINTN Prev = 0; Prev < Off; Prev += Stride) {
      EFI_MEMORY_DESCRIPTOR *Before = (VOID *)((UINT8 *)Buffer + Prev);
      if (Before->PhysicalStart < End &&
          D->PhysicalStart < Before->PhysicalStart + EFI_PAGES_TO_SIZE (Before->NumberOfPages)) {
        return FALSE;
      }
    }
    Sum += Length;
    if (D->Type == ExpectedType && TrialSpan (Pages, TRIAL_PAGES*EFI_PAGE_SIZE, D->PhysicalStart, End)) {
      Found = TRUE;
    }
  }
  return Found && Sum == mFreeEnd - mFreeBase;
}

STATIC __attribute__((noinline)) BOOLEAN
TrialVerifyAllocations (volatile UINT64 *Pages, volatile UINT8 *Pool)
{
  for (UINTN I = 0; I < TRIAL_PAGES*EFI_PAGE_SIZE/sizeof (*Pages); ++I) {
    if (Pages[I] != (0xa55a1234eeddbb66ULL ^ (UINTN)&Pages[I])) {
      return FALSE;
    }
  }
  for (UINTN I = 0; I < TRIAL_BYTES; ++I) {
    if (Pool[I] != (UINT8)(0xc3 ^ I)) {
      return FALSE;
    }
  }
  return TRUE;
}

STATIC BOOLEAN
ExerciseMemory (VOID *HobStart)
{
  EFI_PHYSICAL_ADDRESS Pages = 0;
  VOID *Pool = NULL;
  UINTN KeyAllocated, KeyFreed;
  if ((UINTN)HobStart != GO_DXE_POOL ||
      !TrialSpan ((UINTN)gDxeCoreST, sizeof (*gDxeCoreST), mFreeBase, mFreeEnd) ||
      gDxeCoreST->Hdr.Signature != EFI_SYSTEM_TABLE_SIGNATURE ||
      !TrialSpan ((UINTN)gDxeCoreST->RuntimeServices, sizeof (EFI_RUNTIME_SERVICES), mFreeBase, mFreeEnd) ||
      gDxeCoreST->RuntimeServices->Hdr.Signature != EFI_RUNTIME_SERVICES_SIGNATURE ||
      gDxeCoreST->BootServices != &mBootServices || mBootServices.Hdr.Signature != EFI_BOOT_SERVICES_SIGNATURE) {
    return FALSE;
  }
  EFI_BOOT_SERVICES *Bs = gDxeCoreST->BootServices;
  if (Bs->AllocatePages (AllocateAnyPages, EfiLoaderData, TRIAL_PAGES, &Pages) != EFI_SUCCESS ||
      (Pages & EFI_PAGE_MASK) || !TrialSpan (Pages, TRIAL_PAGES*EFI_PAGE_SIZE, mFreeBase, mFreeEnd) ||
      Bs->AllocatePool (EfiBootServicesData, TRIAL_BYTES, &Pool) != EFI_SUCCESS ||
      !TrialSpan ((UINTN)Pool, TRIAL_BYTES, mFreeBase, mFreeEnd) ||
      ((UINTN)Pool < Pages + TRIAL_PAGES*EFI_PAGE_SIZE && Pages < (UINTN)Pool + TRIAL_BYTES)) {
    return FALSE;
  }
  volatile UINT64 *Words = (volatile UINT64 *)(UINTN)Pages;
  volatile UINT8 *Bytes = Pool;
  for (UINTN I = 0; I < TRIAL_PAGES*EFI_PAGE_SIZE/sizeof (*Words); ++I) {
    Words[I] = 0xa55a1234eeddbb66ULL ^ (UINTN)&Words[I];
  }
  for (UINTN I = 0; I < TRIAL_BYTES; ++I) {
    Bytes[I] = (UINT8)(0xc3 ^ I);
  }
  __asm__ volatile ("dsb sy" ::: "memory");
  if (!TrialVerifyAllocations (Words, Bytes) || !CheckMap (Bs, Pages, EfiLoaderData, &KeyAllocated) ||
      Bs->FreePool (Pool) != EFI_SUCCESS || Bs->FreePages (Pages, TRIAL_PAGES) != EFI_SUCCESS ||
      !CheckMap (Bs, Pages, EfiConventionalMemory, &KeyFreed)) {
    return FALSE;
  }
  return KeyAllocated != KeyFreed;
}

// Link-time hook for this terminal image only. The two runtime pools have been created.
// DxeMain and the memory services being measured are linked directly from upstream.
EFI_STATUS
__wrap_CoreInitializeImageServices (VOID *HobStart)
{
  TrialPaint (0xff8000, 0x000000);
  if (ExerciseMemory (HobStart)) {
    TrialPaint (0x0000ff, 0x00ff00);
    __asm__ volatile (".global TrialMemoryComplete\nTrialMemoryComplete: b TrialMemoryComplete");
  }
  __asm__ volatile (".global TrialMemoryRejected\nTrialMemoryRejected: b TrialMemoryRejected");
  return EFI_ABORTED;
}
