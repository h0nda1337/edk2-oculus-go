/** Publish the debugger locator in the aligned page owned by this diagnostic FD.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Guid/DebugImageInfoTable.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Trial/DebugPage.h>
#include <Trial/DxeLayout.h>

extern EFI_SYSTEM_TABLE_POINTER *mDebugTable;
extern EFI_DEBUG_IMAGE_INFO_TABLE_HEADER mDebugInfoTableHeader;
extern EFI_DXE_SERVICES *gDxeCoreDS;
extern EFI_HANDLE gDxeCoreImageHandle;
extern EFI_LOADED_IMAGE_PROTOCOL *gDxeCoreLoadedImage;
VOID __real_CoreNewDebugImageInfoEntry (UINT32 Type, EFI_LOADED_IMAGE_PROTOCOL *Image, EFI_HANDLE Handle);

STATIC_ASSERT ((GO_DEBUG_PAGE & (SIZE_4MB - 1)) == 0, "UEFI debugger locator alignment");
STATIC_ASSERT (sizeof (EFI_SYSTEM_TABLE_POINTER) == 24, "AArch64 debugger locator ABI");

STATIC __attribute__((noinline,noreturn)) VOID
TrialDebugRejected (VOID)
{
  for (;;) {
    __asm__ volatile ("wfe");
  }
}

STATIC __attribute__((noinline)) BOOLEAN
TrialCheckDebugPage (UINT64 Mask)
{
  for (UINTN Addr = GO_DEBUG_PAGE; Addr < GO_DEBUG_PAGE + EFI_PAGE_SIZE; Addr += sizeof (UINT64)) {
    if (*(volatile UINT64 *)Addr != (Addr ^ Mask)) {
      return FALSE;
    }
  }
  return TRUE;
}

STATIC BOOLEAN
DebugPageAllocated (VOID)
{
  EFI_GCD_MEMORY_SPACE_DESCRIPTOR Resource;
  EFI_MEMORY_DESCRIPTOR Descriptors[48];
  UINTN Size = sizeof (Descriptors), Key, Stride;
  UINT32 Version;
  if (gDxeCoreDS->GetMemorySpaceDescriptor (GO_DEBUG_PAGE, &Resource) != EFI_SUCCESS ||
      Resource.BaseAddress != GO_DEBUG_PAGE || Resource.Length != EFI_PAGE_SIZE ||
      Resource.GcdMemoryType != EfiGcdMemoryTypeSystemMemory ||
      Resource.ImageHandle != gDxeCoreImageHandle || Resource.DeviceHandle != NULL ||
      gBS->GetMemoryMap (&Size, Descriptors, &Key, &Stride, &Version) != EFI_SUCCESS ||
      Size > sizeof (Descriptors) || Stride < sizeof (*Descriptors) || Size % Stride != 0 ||
      Version != EFI_MEMORY_DESCRIPTOR_VERSION) {
    return FALSE;
  }
  for (UINTN Offset = 0; Offset < Size; Offset += Stride) {
    EFI_MEMORY_DESCRIPTOR *D = (VOID *)((UINT8 *)Descriptors + Offset);
    if (D->PhysicalStart == GO_DEBUG_PAGE) {
      return D->NumberOfPages == 1 && D->Type == EfiBootServicesData;
    }
  }
  return FALSE;
}

VOID
TrialInitializeDebugPage (VOID)
{
  EFI_PHYSICAL_ADDRESS Address = GO_DEBUG_PAGE;
  EFI_GCD_MEMORY_SPACE_DESCRIPTOR Existing;
  UINT64 Mask = 0x2e8163d4c7095bfaULL;
  if (mDebugTable != NULL || gDxeCoreDS->GetMemorySpaceDescriptor (Address, &Existing) != EFI_SUCCESS ||
      Existing.GcdMemoryType != EfiGcdMemoryTypeNonExistent || Existing.ImageHandle != NULL ||
      mDebugInfoTableHeader.TableSize != 0 || mDebugInfoTableHeader.EfiDebugImageInfoTable != NULL) {
    TrialDebugRejected ();
  }
  // SEC has verified identity translation and both unmapped guards. The
  // erased contents must match the loaded FD before the first store.
  for (UINTN Addr = GO_DEBUG_PAGE; Addr < GO_DEBUG_PAGE + EFI_PAGE_SIZE; Addr += sizeof (UINT64)) {
    if (*(volatile UINT64 *)Addr != MAX_UINT64) {
      TrialDebugRejected ();
    }
  }
  for (UINTN Pass = 0; Pass < 2; ++Pass, Mask = ~Mask) {
    for (UINTN Addr = GO_DEBUG_PAGE; Addr < GO_DEBUG_PAGE + EFI_PAGE_SIZE; Addr += sizeof (UINT64)) {
      *(volatile UINT64 *)Addr = Addr ^ Mask;
    }
    __asm__ volatile ("dsb sy" ::: "memory");
    if (!TrialCheckDebugPage (Mask)) {
      TrialDebugRejected ();
    }
  }
  if (gDxeCoreDS->AddMemorySpace (EfiGcdMemoryTypeSystemMemory, Address, EFI_PAGE_SIZE, EFI_MEMORY_UC) != EFI_SUCCESS ||
      gBS->AllocatePages (AllocateAddress, EfiBootServicesData, 1, &Address) != EFI_SUCCESS ||
      Address != GO_DEBUG_PAGE || !DebugPageAllocated ()) {
    TrialDebugRejected ();
  }
  ZeroMem ((VOID *)(UINTN)Address, EFI_PAGE_SIZE);
  mDebugTable = (EFI_SYSTEM_TABLE_POINTER *)(UINTN)Address;
  mDebugTable->Signature = EFI_SYSTEM_TABLE_SIGNATURE;
  mDebugTable->EfiSystemTableBase = (EFI_PHYSICAL_ADDRESS)(UINTN)gST;
  mDebugTable->Crc32 = CalculateCrc32 (mDebugTable, sizeof (*mDebugTable));
  if (gBS->InstallConfigurationTable (&gEfiDebugImageInfoTableGuid, &mDebugInfoTableHeader) != EFI_SUCCESS) {
    TrialDebugRejected ();
  }
  TrialPaint (0xff8000, 0x00ffff);
}

VOID
__wrap_CoreNewDebugImageInfoEntry (UINT32 Type, EFI_LOADED_IMAGE_PROTOCOL *Image, EFI_HANDLE Handle)
{
  EFI_DEBUG_IMAGE_INFO_TABLE_HEADER *Header;
  EFI_DEBUG_IMAGE_INFO_NORMAL *Record;
  EFI_SYSTEM_TABLE_POINTER Locator;
#ifdef OCULUS_GO_DXE_DISPATCH
  if (Image != gDxeCoreLoadedImage && Handle != gDxeCoreImageHandle) {
    __real_CoreNewDebugImageInfoEntry (Type, Image, Handle);
    return;
  }
#endif
  if (Image != gDxeCoreLoadedImage || Handle != gDxeCoreImageHandle || Type != EFI_DEBUG_IMAGE_INFO_TYPE_NORMAL) {
    TrialDebugRejected ();
  }
  __real_CoreNewDebugImageInfoEntry (Type, Image, Handle);
  if ((UINTN)mDebugTable != GO_DEBUG_PAGE || mDebugTable->Signature != EFI_SYSTEM_TABLE_SIGNATURE ||
      mDebugTable->EfiSystemTableBase != (UINTN)gST || gST->NumberOfTableEntries != 4 ||
      EfiGetSystemConfigurationTable (&gEfiDebugImageInfoTableGuid, (VOID **)&Header) != EFI_SUCCESS ||
      Header != &mDebugInfoTableHeader || Header->UpdateStatus != EFI_DEBUG_IMAGE_INFO_TABLE_MODIFIED ||
      Header->TableSize != 1 || !TrialSpan ((UINTN)Header->EfiDebugImageInfoTable,
                                           sizeof (EFI_DEBUG_IMAGE_INFO), GO_DXE_POOL, GO_DXE_POOL_END)) {
    TrialDebugRejected ();
  }
  CopyMem (&Locator, mDebugTable, sizeof (Locator));
  Locator.Crc32 = 0;
  Record = Header->EfiDebugImageInfoTable[0].NormalImage;
  if (mDebugTable->Crc32 != CalculateCrc32 (&Locator, sizeof (Locator)) ||
      !TrialSpan ((UINTN)Record, sizeof (*Record), GO_DXE_POOL, GO_DXE_POOL_END) ||
      Record->ImageInfoType != Type || Record->ImageHandle != Handle ||
      Record->LoadedImageProtocolInstance != Image || Image->SystemTable != gST) {
    TrialDebugRejected ();
  }
  TrialPaint (0xff0000, 0x00ffff);
#ifdef OCULUS_GO_DXE_DISPATCH
  return;
#else
  __asm__ volatile (".global TrialDebugComplete\nTrialDebugComplete: b TrialDebugComplete");
  __builtin_unreachable ();
#endif
}
