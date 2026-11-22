/** Present the assigned QEMU UFS BAR and its device-specific DMA services
    on a separate non-PCI handle. This adapter belongs only to the AAVMF test.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "PlatformFixture.h"
#include <Guid/NonDiscoverableDevice.h>
#include <IndustryStandard/Pci.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/DevicePath.h>
#include <Protocol/GoUfsPlatformDma.h>
#include <Protocol/NonDiscoverableDevice.h>
#include <Protocol/PciIo.h>

typedef struct {
  VOID                 *PciToken;
  VOID                 *Host;
  VOID                 *BouncePage;
  UINTN                Length;
  EFI_PHYSICAL_ADDRESS Bus;
  UINT64               Required;
  BOOLEAN              Granted;
  BOOLEAN              Capacity;
} FIXTURE_MAP;

STATIC EFI_PCI_IO_PROTOCOL *mPci;
STATIC EFI_HANDLE mController;
STATIC PLATFORM_CASE mCase;
STATIC UINTN mInit, mAlloc, mFree, mMap, mGrant, mRevoke, mUnmap, mRefused, mShortened;

STATIC UINTN mProbeDenials, mRevokeFailures;

STATIC EFI_STATUS EFIAPI
BoardInitialize (NON_DISCOVERABLE_DEVICE *This)
{
  ++mInit;
  if (mCase == BusyHandoff) {
    return EFI_NOT_READY;
  }
  // Enable only the assigned virtual PCI controller once DXE requests ownership.
  return mPci->Attributes (mPci, EfiPciIoAttributeOperationEnable,
                           EFI_PCI_IO_ATTRIBUTE_MEMORY | EFI_PCI_IO_ATTRIBUTE_BUS_MASTER, NULL);
}

STATIC EFI_STATUS EFIAPI
BoardAllocate (EDKII_IOMMU_PROTOCOL *This, EFI_ALLOCATE_TYPE Type, EFI_MEMORY_TYPE MemoryType,
               UINTN Pages, VOID **Host, UINT64 Attributes)
{
  EFI_STATUS Status = mPci->AllocateBuffer (mPci, Type, MemoryType, Pages, Host, Attributes);
  if (!EFI_ERROR (Status)) {
    ++mAlloc;
  }
  return Status;
}

STATIC EFI_STATUS EFIAPI
BoardFree (EDKII_IOMMU_PROTOCOL *This, UINTN Pages, VOID *Host)
{
  EFI_STATUS Status = mPci->FreeBuffer (mPci, Pages, Host);
  if (!EFI_ERROR (Status)) {
    ++mFree;
  }
  return Status;
}

STATIC EFI_STATUS EFIAPI
BoardMap (EDKII_IOMMU_PROTOCOL *This, EDKII_IOMMU_OPERATION Operation, VOID *Host, UINTN *Length,
          EFI_PHYSICAL_ADDRESS *Bus, VOID **Mapping)
{
  EFI_PCI_IO_PROTOCOL_OPERATION PciOperation;
  UINT64 Access;
  switch (Operation) {
    case EdkiiIoMmuOperationBusMasterCommonBuffer:
    case EdkiiIoMmuOperationBusMasterCommonBuffer64:
      PciOperation = EfiPciIoOperationBusMasterCommonBuffer;
      Access = EDKII_IOMMU_ACCESS_READ | EDKII_IOMMU_ACCESS_WRITE;
      break;
    case EdkiiIoMmuOperationBusMasterWrite:
    case EdkiiIoMmuOperationBusMasterWrite64:
      PciOperation = EfiPciIoOperationBusMasterWrite;
      Access = EDKII_IOMMU_ACCESS_WRITE;
      break;
    case EdkiiIoMmuOperationBusMasterRead:
    case EdkiiIoMmuOperationBusMasterRead64:
      PciOperation = EfiPciIoOperationBusMasterRead;
      Access = EDKII_IOMMU_ACCESS_READ;
      break;
    default:
      return EFI_INVALID_PARAMETER;
  }
  FIXTURE_MAP *Record = AllocateZeroPool (sizeof (*Record));
  if (Record == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  Record->Host = Host;
  Record->Required = Access;
  Record->Capacity = Access == EDKII_IOMMU_ACCESS_WRITE && *Length == 8;
  if (Record->Capacity && mCase == Bounce) {
    Record->BouncePage = AllocatePages (1);
    if (Record->BouncePage == NULL) {
      FreePool (Record);
      return EFI_OUT_OF_RESOURCES;
    }
    CopyMem (Record->BouncePage, Host, *Length);
  }
  if (Record->Capacity && mCase == ShortTail && ((UINTN)Host & EFI_PAGE_MASK) == EFI_PAGE_SIZE - 8) {
    *Length = 4;
    ++mShortened;
  }
  EFI_STATUS Status = mPci->Map (mPci, PciOperation, Record->BouncePage == NULL ? Host : Record->BouncePage,
                                 Length, Bus, &Record->PciToken);
  if (EFI_ERROR (Status)) {
    if (Record->BouncePage != NULL) {
      FreePages (Record->BouncePage, 1);
    }
    FreePool (Record);
    return Status;
  }
  Record->Bus = *Bus;
  Record->Length = *Length;
  *Mapping = Record;
  ++mMap;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
BoardSetAttribute (EDKII_IOMMU_PROTOCOL *This, EFI_HANDLE Device, VOID *Mapping, UINT64 Access)
{
  FIXTURE_MAP *Record = Mapping;
  if (Device != mController || Record == NULL ||
      (Access != 0 && Access != Record->Required) || ((Access != 0) == Record->Granted)) {
    return EFI_INVALID_PARAMETER;
  }
  if (mCase == RejectProbe && Access == (EDKII_IOMMU_ACCESS_READ | EDKII_IOMMU_ACCESS_WRITE)) {
    ++mProbeDenials;
    return EFI_ACCESS_DENIED;
  }
  if (mCase == RetryRevoke && Access == 0 && mRevokeFailures == 0 && Record->Capacity &&
      ((UINTN)Record->Host & EFI_PAGE_MASK) == EFI_PAGE_SIZE - 8) {
    ++mRevokeFailures;
    return EFI_DEVICE_ERROR;
  }
  if (Access != 0 && mCase == DenyTail && Record->Capacity &&
      ((UINTN)Record->Host & EFI_PAGE_MASK) == EFI_PAGE_SIZE - 8) {
    ++mRefused;
    return EFI_NO_MAPPING;
  }
  Record->Granted = Access != 0;
  if (Access != 0) {
    ++mGrant;
  } else {
    ++mRevoke;
  }
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
BoardUnmap (EDKII_IOMMU_PROTOCOL *This, VOID *Mapping)
{
  FIXTURE_MAP *Record = Mapping;
  if (Record == NULL || Record->Granted) {
    return EFI_ACCESS_DENIED;
  }
  if (Record->PciToken != NULL) {
    EFI_STATUS Status = mPci->Unmap (mPci, Record->PciToken);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  if (Record->BouncePage != NULL) {
    CopyMem (Record->Host, Record->BouncePage, Record->Length);
    FreePages (Record->BouncePage, 1);
  }
  if (Record->Capacity) {
    Print (L"PLATFORM DATA CPU %lx DMA %lx MAPPED %u BYTES ", (UINT64)(UINTN)Record->Host, Record->Bus,
           Record->Length);
    // The client owns all eight bytes even when the provider shortens the mapping.
    for (UINTN I = 0; I < 8; ++I) {
      Print (L"%02x", ((UINT8 *)Record->Host)[I]);
    }
    Print (L"\r\n");
  }
  ++mUnmap;
  FreePool (Record);
  return EFI_SUCCESS;
}

STATIC EDKII_IOMMU_PROTOCOL mDma = {
  EDKII_IOMMU_PROTOCOL_REVISION, BoardSetAttribute, BoardMap, BoardUnmap, BoardAllocate, BoardFree
};
STATIC NON_DISCOVERABLE_DEVICE mDevice = {
  &gEdkiiNonDiscoverableUfsDeviceGuid, NonDiscoverableDeviceDmaTypeCoherent, BoardInitialize, NULL
};
STATIC struct {
  VENDOR_DEVICE_PATH Vendor;
  EFI_DEVICE_PATH_PROTOCOL End;
} mPath = {
  { { HARDWARE_DEVICE_PATH, HW_VENDOR_DP, { sizeof (VENDOR_DEVICE_PATH), 0 } },
    { 0x264fec4b, 0x23f8, 0x40cf, { 0x8a, 0x70, 0x06, 0xe0, 0xdb, 0xc7, 0x70, 0x69 } } },
  { END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, { END_DEVICE_PATH_LENGTH, 0 } }
};

EFI_STATUS
PublishFixture (PLATFORM_CASE Mode, EFI_HANDLE *Platform)
{
  mCase = Mode;
  UINTN Count;
  EFI_HANDLE *Handles;
  EFI_STATUS Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiPciIoProtocolGuid, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  for (UINTN I = 0; I < Count; ++I) {
    EFI_PCI_IO_PROTOCOL *Pci;
    UINT8 Class[3];
    Status = gBS->HandleProtocol (Handles[I], &gEfiPciIoProtocolGuid, (VOID **)&Pci);
    if (EFI_ERROR (Status)) {
      break;
    }
    Status = Pci->Pci.Read (Pci, EfiPciIoWidthUint8, PCI_CLASSCODE_OFFSET, 3, Class);
    if (EFI_ERROR (Status)) {
      break;
    }
    if (Class[2] == PCI_CLASS_MASS_STORAGE && Class[1] == 0x09) {
      if (mPci != NULL) {
        Status = EFI_UNSUPPORTED;
        break;
      }
      mPci = Pci;
    }
  }
  FreePool (Handles);
  if (EFI_ERROR (Status) || mPci == NULL) {
    return EFI_ERROR (Status) ? Status : EFI_NOT_FOUND;
  }
  // QEMU UFS uses BAR 0. The PCI bus assigned its address and returns the
  // associated host memory resource and EndTag. No hard-coded MMIO address.
  Status = mPci->GetBarAttributes (mPci, 0, NULL, (VOID **)&mDevice.Resources);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  EFI_ACPI_ADDRESS_SPACE_DESCRIPTOR *Bar = mDevice.Resources;
  if (Bar->Desc != ACPI_ADDRESS_SPACE_DESCRIPTOR || Bar->ResType != ACPI_ADDRESS_SPACE_TYPE_MEM ||
      Bar->AddrTranslationOffset != 0 || Bar->AddrLen == 0 || Bar->AddrLen - 1 > MAX_UINT64 - Bar->AddrRangeMin) {
    return EFI_UNSUPPORTED;
  }
  Bar->AddrRangeMax = Bar->AddrRangeMin + Bar->AddrLen - 1;
  Status = gBS->InstallMultipleProtocolInterfaces (&mController, &gEfiDevicePathProtocolGuid, &mPath.Vendor.Header,
                                                    &gEdkiiNonDiscoverableDeviceProtocolGuid, &mDevice, NULL);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  if (Mode != MissingDma) {
    EFI_HANDLE Provider = Mode == WrongHandle ? NULL : mController;
    Status = gBS->InstallMultipleProtocolInterfaces (&Provider, &gGoUfsPlatformDmaProtocolGuid, &mDma, NULL);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  *Platform = mController;
  Print (L"PLATFORM RESOURCE %lx SIZE %lx\r\n", Bar->AddrRangeMin, Bar->AddrLen);
  return EFI_SUCCESS;
}

VOID
PrintFixtureStats (VOID)
{
  Print (L"PLATFORM PROBE DENIED %u REVOKE FAILED %u\r\n", mProbeDenials, mRevokeFailures);
  Print (L"PLATFORM COUNTS INIT %u ALLOC %u FREE %u MAP %u GRANT %u REVOKE %u UNMAP %u DENIED %u SHORT %u\r\n",
         mInit, mAlloc, mFree, mMap, mGrant, mRevoke, mUnmap, mRefused, mShortened);
}
