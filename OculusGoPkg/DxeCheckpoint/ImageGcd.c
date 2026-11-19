/** Terminal DXE_GCD checkpoint around the upstream GCD initializer.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Protocol/LoadedImage.h>
#include <Library/BaseMemoryLib.h>
#include <Library/HobLib.h>
#include <Trial/DxeLayout.h>
#include <Trial/StackLayout.h>

extern EFI_SYSTEM_TABLE          *gDxeCoreST;
extern EFI_DXE_SERVICES          *gDxeCoreDS;
extern EFI_LOADED_IMAGE_PROTOCOL *gDxeCoreLoadedImage;
extern EFI_HANDLE                 gDxeCoreImageHandle;
extern EFI_GUID                  *gDxeCoreFileName;
EFI_STATUS __real_CoreInitializeGcdServices (VOID **Hobs, EFI_PHYSICAL_ADDRESS Base, UINT64 Length);

STATIC BOOLEAN
CheckLoadedImage (EFI_HOB_HANDOFF_INFO_TABLE *Phit)
{
  CONST EFI_GUID CoreGuid = GO_DXE_CORE_GUID;
  EFI_LOADED_IMAGE_PROTOCOL *Image = NULL;
  if (gDxeCoreImageHandle == NULL ||
      gDxeCoreST->BootServices->HandleProtocol (gDxeCoreImageHandle, &gEfiLoadedImageProtocolGuid,
                                                (VOID **)&Image) != EFI_SUCCESS ||
      !TrialSpan ((UINTN)Image, sizeof (*Image), GO_DXE_POOL, GO_DXE_POOL_END) ||
      Image != gDxeCoreLoadedImage || Image->Revision != EFI_LOADED_IMAGE_PROTOCOL_REVISION ||
      Image->SystemTable != gDxeCoreST || Image->ImageCodeType != EfiBootServicesCode ||
      Image->ImageDataType != EfiBootServicesData) {
    return FALSE;
  }
  for (UINTN P = (UINTN)Phit; P < Phit->EfiEndOfHobList;) {
    EFI_HOB_GENERIC_HEADER *H = (VOID *)P;
    if (H->HobType == EFI_HOB_TYPE_MEMORY_ALLOCATION && H->HobLength == sizeof (EFI_HOB_MEMORY_ALLOCATION_MODULE)) {
      EFI_HOB_MEMORY_ALLOCATION_MODULE *M = (VOID *)P;
      if (CompareGuid (&M->ModuleName, &CoreGuid)) {
        return gDxeCoreFileName == &M->ModuleName && (UINTN)Image->ImageBase == M->MemoryAllocationHeader.MemoryBaseAddress &&
               Image->ImageSize == M->MemoryAllocationHeader.MemoryLength;
      }
    }
    P += H->HobLength;
  }
  return FALSE;
}

// This profile's CPU HOB advertises a 32-bit address space and one tested RAM resource.
STATIC __attribute__((noinline)) BOOLEAN
TrialCheckGcdMap (EFI_GCD_MEMORY_SPACE_DESCRIPTOR *Map, UINTN Count)
{
  UINT64 Cursor = 0, TestedBytes = 0;
  BOOLEAN ReservedStack = FALSE;
  CONST UINT64 End = (1ULL << 32);
  if (Count < 3 || Count > 64 ||
      !TrialSpan ((UINTN)Map, Count * sizeof (*Map), GO_DXE_POOL, GO_DXE_POOL_END)) {
    return FALSE;
  }
  for (UINTN Index = 0; Index < Count; ++Index) {
    EFI_GCD_MEMORY_SPACE_DESCRIPTOR *D = &Map[Index];
    if (D->BaseAddress != Cursor || D->Length == 0 || D->Length > End - Cursor || D->DeviceHandle != NULL) {
      return FALSE;
    }
    Cursor += D->Length;
    if (D->BaseAddress == GO_DXE_STACK_BASE && Cursor == GO_TRIAL_STACK_TOP) {
      if (D->GcdMemoryType != EfiGcdMemoryTypeReserved || D->ImageHandle != gDxeCoreImageHandle) {
        return FALSE;
      }
      ReservedStack = TRUE;
    } else if (Cursor <= GO_DXE_POOL || D->BaseAddress >= GO_DXE_POOL_END) {
      if (D->GcdMemoryType != EfiGcdMemoryTypeNonExistent || D->ImageHandle != NULL) {
        return FALSE;
      }
    } else {
      if (D->BaseAddress < GO_DXE_POOL || Cursor > GO_DXE_POOL_END ||
          D->GcdMemoryType != EfiGcdMemoryTypeSystemMemory ||
          D->ImageHandle != gDxeCoreImageHandle || (D->Capabilities & EFI_MEMORY_UC) == 0) {
        return FALSE;
      }
      TestedBytes += D->Length;
    }
  }
  return ReservedStack && Cursor == End && TestedBytes == GO_DXE_POOL_END - GO_DXE_POOL;
}

// The dispatcher later compares a GUID in the original HOB page. Verify its
// EFI memory type after migration, when that page could otherwise be reclaimed.
STATIC BOOLEAN
OriginalHobsAllocated (VOID)
{
  UINT64 Storage[256];
  UINTN Size = sizeof (Storage), Key, Stride;
  UINT32 Version;
  if (gDxeCoreST->BootServices->GetMemoryMap (&Size, (EFI_MEMORY_DESCRIPTOR *)Storage,
        &Key, &Stride, &Version) != EFI_SUCCESS || Size > sizeof (Storage) ||
      Stride < sizeof (EFI_MEMORY_DESCRIPTOR) || Size % Stride != 0 ||
      Version != EFI_MEMORY_DESCRIPTOR_VERSION) {
    return FALSE;
  }
  for (UINTN Offset = 0; Offset < Size; Offset += Stride) {
    EFI_MEMORY_DESCRIPTOR *D = (VOID *)((UINT8 *)Storage + Offset);
    if (D->PhysicalStart == GO_DXE_POOL) {
      return D->Type == EfiBootServicesData && D->NumberOfPages >= 1 &&
             D->NumberOfPages <= EFI_SIZE_TO_PAGES (GO_DXE_POOL_END - GO_DXE_POOL);
    }
  }
  return FALSE;
}

EFI_STATUS
__wrap_CoreInitializeGcdServices (VOID **Hobs, EFI_PHYSICAL_ADDRESS Base, UINT64 Length)
{
  EFI_HOB_HANDOFF_INFO_TABLE *Phit = *Hobs;
  UINT8 Original[EFI_PAGE_SIZE];
  UINTN Bytes, Count;
  EFI_GCD_MEMORY_SPACE_DESCRIPTOR *Map = NULL;
  if ((UINTN)Phit != GO_DXE_POOL || !CheckLoadedImage (Phit)) {
    goto Rejected;
  }
  TrialPaint (0xffff00, 0xff00ff);
  Bytes = Phit->EfiFreeMemoryBottom - (UINTN)Phit;
  if (Bytes < sizeof (*Phit) || Bytes > sizeof (Original) ||
      Base != ALIGN_VALUE (Phit->EfiFreeMemoryBottom, EFI_PAGE_SIZE) ||
      Base >= Phit->EfiFreeMemoryTop || Length != Phit->EfiFreeMemoryTop - Base) {
    goto Rejected;
  }
  // Snapshot before GCD relocates the list and publishes its final memory types.
  CopyMem (Original, Phit, Bytes);
  if (__real_CoreInitializeGcdServices (Hobs, Base, Length) != EFI_SUCCESS ||
      !TrialSpan ((UINTN)*Hobs, Bytes, Base, Base + Length) || *Hobs != GetHobList () ||
      CompareMem (*Hobs, Original, Bytes) != 0 || !OriginalHobsAllocated () ||
      CompareMem (Phit, Original, Bytes) != 0) {
    goto Rejected;
  }
  TrialPaint (0xff8000, 0xffffff);
  if (gDxeCoreDS->Hdr.Signature != DXE_SERVICES_SIGNATURE ||
      gDxeCoreDS->GetMemorySpaceMap (&Count, &Map) != EFI_SUCCESS ||
      !TrialCheckGcdMap (Map, Count) || gDxeCoreST->BootServices->FreePool (Map) != EFI_SUCCESS) {
    goto Rejected;
  }
  TrialPaint (0xff00ff, 0x00ffff);
#ifdef OCULUS_GO_DXE_TABLES
  return EFI_SUCCESS;
#else
  __asm__ volatile (".global TrialGcdComplete\nTrialGcdComplete: b TrialGcdComplete");
#endif

Rejected:
  __asm__ volatile (".global TrialGcdRejected\nTrialGcdRejected: b TrialGcdRejected");
  return EFI_ABORTED;
}
