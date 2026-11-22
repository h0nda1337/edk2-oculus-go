/** UFS host for a prepared, non-discoverable controller with a device-scoped mapper.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "GoUfsHc.h"
#include <Guid/NonDiscoverableDevice.h>
#include <Library/BaseMemoryLib.h>
#include <Library/IoLib.h>
#include <Library/UefiLib.h>
#include <Protocol/DevicePath.h>
#include <Protocol/NonDiscoverableDevice.h>

// A failed provider release retains the original page, mapping and protocol
// opens. A subsequent Start or Stop retries cleanup before reusing the handle.
STATIC LIST_ENTRY mPending = INITIALIZE_LIST_HEAD_VARIABLE (mPending);

STATIC EFI_STATUS EFIAPI
GetBar (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, UINTN *Base)
{
  if (This == NULL || Base == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  *Base = GO_HOST (This)->Base;
  return EFI_SUCCESS;
}

// The pinned UFS transport uses only natural 32-bit register accesses.
STATIC EFI_STATUS
Registers (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EDKII_UFS_HOST_CONTROLLER_PROTOCOL_WIDTH Width,
           UINT64 Offset, UINTN Count, VOID *Buffer, BOOLEAN Write)
{
  if (This == NULL || (Count != 0 && Buffer == NULL)) {
    return EFI_INVALID_PARAMETER;
  }
  GO_UFS_HOST *Host = GO_HOST (This);
  if (Width != EfiUfsHcWidthUint32 || (Offset & 3) != 0 || Offset > Host->Size ||
      Count > (Host->Size - (UINTN)Offset) / sizeof (UINT32)) {
    return EFI_UNSUPPORTED;
  }
  if (Count != 0 && Count * sizeof (UINT32) - 1 > MAX_UINTN - (UINTN)Buffer) {
    return EFI_INVALID_PARAMETER;
  }
  UINTN Address = Host->Base + (UINTN)Offset;
  UINT8 *Data = Buffer;
  for (UINTN I = 0; I < Count; ++I) {
    if (Write) {
      MmioWrite32 (Address + I * sizeof (UINT32), ReadUnaligned32 ((UINT32 *)(Data + I * sizeof (UINT32))));
    } else {
      WriteUnaligned32 ((UINT32 *)(Data + I * sizeof (UINT32)), MmioRead32 (Address + I * sizeof (UINT32)));
    }
  }
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
Read (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EDKII_UFS_HOST_CONTROLLER_PROTOCOL_WIDTH Width,
      UINT64 Offset, UINTN Count, VOID *Buffer)
{
  return Registers (This, Width, Offset, Count, Buffer, FALSE);
}

STATIC EFI_STATUS EFIAPI
Write (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EDKII_UFS_HOST_CONTROLLER_PROTOCOL_WIDTH Width,
       UINT64 Offset, UINTN Count, VOID *Buffer)
{
  return Registers (This, Width, Offset, Count, Buffer, TRUE);
}

STATIC EFI_STATUS EFIAPI
Flush (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This)
{
  if (This == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  // Drain posted register writes using a read of the read-only UFSHCI CAP.
  // Cache maintenance and inbound data completion belong to the DMA provider.
  MemoryFence ();
  MmioRead32 (GO_HOST (This)->Base);
  MemoryFence ();
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
CheckIdle (GO_UFS_DMA_GUARD_PROTOCOL *This, EFI_PHYSICAL_ADDRESS Base, UINTN Pages)
{
  if (This == NULL || (Base & EFI_PAGE_MASK) != 0 || Pages == 0 ||
      Pages > MAX_UINTN / EFI_PAGE_SIZE || Base > MAX_UINTN - (EFI_PAGES_TO_SIZE (Pages) - 1)) {
    return EFI_INVALID_PARAMETER;
  }
  GO_UFS_HOST *Host = BASE_CR (This, GO_UFS_HOST, Guard);
  return GoCheckIdle (Host, (UINTN)Base, (UINTN)Base + EFI_PAGES_TO_SIZE (Pages) - 1);
}

STATIC CONST EDKII_UFS_HOST_CONTROLLER_PROTOCOL mHc = {
  GetBar, GoAllocate, GoFree, GoMap, GoUnmap, Flush, Read, Write
};

STATIC VOID
CloseInputs (EFI_DRIVER_BINDING_PROTOCOL *Binding, EFI_HANDLE Controller)
{
  gBS->CloseProtocol (Controller, &gGoUfsPlatformDmaProtocolGuid, Binding->DriverBindingHandle, Controller);
  gBS->CloseProtocol (Controller, &gEdkiiNonDiscoverableDeviceProtocolGuid, Binding->DriverBindingHandle, Controller);
}

STATIC BOOLEAN
ValidResources (NON_DISCOVERABLE_DEVICE *Device)
{
  if (Device == NULL || Device->Type == NULL || !CompareGuid (Device->Type, &gEdkiiNonDiscoverableUfsDeviceGuid) ||
      Device->Initialize == NULL || Device->Resources == NULL || (UINTN)Device->DmaType >= NonDiscoverableDeviceDmaTypeMax) {
    return FALSE;
  }
  EFI_ACPI_ADDRESS_SPACE_DESCRIPTOR *Res = Device->Resources;
  // Standard UFSHCI registers up to and including UICCMDARG3 (offset 0x9c).
  return Res->Desc == ACPI_ADDRESS_SPACE_DESCRIPTOR && Res->Len == sizeof (*Res) - 3 &&
         Res->ResType == ACPI_ADDRESS_SPACE_TYPE_MEM && Res->AddrTranslationOffset == 0 &&
         (Res->AddrSpaceGranularity == 32 || Res->AddrSpaceGranularity == 64) &&
         (Res->AddrRangeMin & 3) == 0 && Res->AddrLen >= 0xa0 && Res->AddrLen <= MAX_UINTN &&
         Res->AddrRangeMin <= MAX_UINTN - (Res->AddrLen - 1) &&
         Res->AddrRangeMax == Res->AddrRangeMin + Res->AddrLen - 1 &&
         ((EFI_ACPI_END_TAG_DESCRIPTOR *)(Res + 1))->Desc == ACPI_END_TAG_DESCRIPTOR;
}

STATIC EFI_STATUS
OpenInputs (EFI_DRIVER_BINDING_PROTOCOL *Binding, EFI_HANDLE Controller, NON_DISCOVERABLE_DEVICE **Device,
            EDKII_IOMMU_PROTOCOL **Dma)
{
  EFI_HANDLE Agent = Binding->DriverBindingHandle;
  EFI_STATUS Status = gBS->OpenProtocol (Controller, &gEfiDevicePathProtocolGuid, NULL, Agent, Controller,
                                         EFI_OPEN_PROTOCOL_TEST_PROTOCOL);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = gBS->OpenProtocol (Controller, &gEdkiiNonDiscoverableDeviceProtocolGuid, (VOID **)Device,
                              Agent, Controller, EFI_OPEN_PROTOCOL_BY_DRIVER);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  if (!ValidResources (*Device)) {
    gBS->CloseProtocol (Controller, &gEdkiiNonDiscoverableDeviceProtocolGuid, Agent, Controller);
    return EFI_UNSUPPORTED;
  }
  Status = gBS->OpenProtocol (Controller, &gGoUfsPlatformDmaProtocolGuid, (VOID **)Dma,
                              Agent, Controller, EFI_OPEN_PROTOCOL_BY_DRIVER);
  if (EFI_ERROR (Status)) {
    gBS->CloseProtocol (Controller, &gEdkiiNonDiscoverableDeviceProtocolGuid, Agent, Controller);
    return Status;
  }
  if (*Dma == NULL || (*Dma)->Revision < EDKII_IOMMU_PROTOCOL_REVISION || (*Dma)->SetAttribute == NULL ||
      (*Dma)->Map == NULL || (*Dma)->Unmap == NULL || (*Dma)->AllocateBuffer == NULL || (*Dma)->FreeBuffer == NULL) {
    CloseInputs (Binding, Controller);
    return EFI_UNSUPPORTED;
  }
  return EFI_SUCCESS;
}

STATIC GO_UFS_HOST *
FindPending (EFI_HANDLE Controller)
{
  for (LIST_ENTRY *Link = mPending.ForwardLink; Link != &mPending; Link = Link->ForwardLink) {
    GO_UFS_HOST *Host = BASE_CR (Link, GO_UFS_HOST, PendingLink);
    if (Host->Controller == Controller) {
      return Host;
    }
  }
  return NULL;
}

STATIC EFI_STATUS
ReleasePending (EFI_DRIVER_BINDING_PROTOCOL *Binding, GO_UFS_HOST *Host)
{
  EFI_STATUS Status = GoReleaseProbe (Host);
  if (!EFI_ERROR (Status)) {
    RemoveEntryList (&Host->PendingLink);
    CloseInputs (Binding, Host->Controller);
    FreePool (Host);
  }
  return Status;
}

STATIC EFI_STATUS EFIAPI
Supported (EFI_DRIVER_BINDING_PROTOCOL *Binding, EFI_HANDLE Controller, EFI_DEVICE_PATH_PROTOCOL *Remaining)
{
  if (FindPending (Controller) != NULL) {
    return EFI_SUCCESS;
  }
  NON_DISCOVERABLE_DEVICE *Device;
  EDKII_IOMMU_PROTOCOL *Dma;
  EFI_STATUS Status = OpenInputs (Binding, Controller, &Device, &Dma);
  if (!EFI_ERROR (Status)) {
    CloseInputs (Binding, Controller);
  }
  return Status;
}

STATIC EFI_STATUS EFIAPI
Start (EFI_DRIVER_BINDING_PROTOCOL *Binding, EFI_HANDLE Controller, EFI_DEVICE_PATH_PROTOCOL *Remaining)
{
  GO_UFS_HOST *Host = FindPending (Controller);
  if (Host != NULL) {
    EFI_STATUS Cleanup = ReleasePending (Binding, Host);
    if (EFI_ERROR (Cleanup)) {
      return Cleanup;
    }
  }
  NON_DISCOVERABLE_DEVICE *Device;
  EDKII_IOMMU_PROTOCOL *Dma;
  EFI_STATUS Status = OpenInputs (Binding, Controller, &Device, &Dma);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  Host = AllocateZeroPool (sizeof (*Host));
  if (Host == NULL) {
    CloseInputs (Binding, Controller);
    return EFI_OUT_OF_RESOURCES;
  }
  Host->Hc = mHc;
  Host->Guard.CheckIdle = CheckIdle;
  Host->Controller = Controller;
  Host->Dma = Dma;
  Host->Base = (UINTN)Device->Resources->AddrRangeMin;
  Host->Size = (UINTN)Device->Resources->AddrLen;
  InitializeListHead (&Host->Mappings);
  InitializeListHead (&Host->Allocations);

  // The board owns preparation of the device aperture, clocks and exclusive
  // handoff. The transport can take control of the HCI immediately at bind.
  Status = Device->Initialize (Device);
  if (Status != EFI_SUCCESS && !EFI_ERROR (Status)) {
    // Only an unqualified board handoff permits the transport to take the HCI.
    Status = EFI_NOT_READY;
  }
  if (!EFI_ERROR (Status)) {
    Status = GoProbeDma (Host);
  }
  if (!EFI_ERROR (Status)) {
    Status = gBS->InstallMultipleProtocolInterfaces (&Controller, &gEdkiiUfsHostControllerProtocolGuid, &Host->Hc,
                                                     &gGoUfsDmaGuardProtocolGuid, &Host->Guard, NULL);
  }
  if (EFI_ERROR (Status)) {
    if (Host->ProbePage != NULL) {
      InsertTailList (&mPending, &Host->PendingLink);
    } else {
      CloseInputs (Binding, Controller);
      FreePool (Host);
    }
  }
  return Status;
}

STATIC EFI_STATUS EFIAPI
Stop (EFI_DRIVER_BINDING_PROTOCOL *Binding, EFI_HANDLE Controller, UINTN Children, EFI_HANDLE *ChildHandles)
{
  if (Children != 0) {
    return EFI_UNSUPPORTED;
  }
  GO_UFS_HOST *Host = FindPending (Controller);
  if (Host != NULL) {
    return ReleasePending (Binding, Host);
  }
  EDKII_UFS_HOST_CONTROLLER_PROTOCOL *Hc;
  EFI_STATUS Status = gBS->HandleProtocol (Controller, &gEdkiiUfsHostControllerProtocolGuid, (VOID **)&Hc);
  if (EFI_ERROR (Status) || Hc == NULL || Hc->Map != GoMap) {
    return EFI_UNSUPPORTED;
  }
  Host = GO_HOST (Hc);
  if (!IsListEmpty (&Host->Allocations) || !IsListEmpty (&Host->Mappings)) {
    return EFI_ACCESS_DENIED;
  }
  Status = gBS->UninstallMultipleProtocolInterfaces (Controller, &gEdkiiUfsHostControllerProtocolGuid, Hc,
                                                    &gGoUfsDmaGuardProtocolGuid, &Host->Guard, NULL);
  if (!EFI_ERROR (Status)) {
    CloseInputs (Binding, Controller);
    FreePool (Host);
  }
  return Status;
}

STATIC EFI_DRIVER_BINDING_PROTOCOL mDriver = {Supported, Start, Stop, 0x10, NULL, NULL};

EFI_STATUS EFIAPI
GoUfsHcEntry (EFI_HANDLE Image, EFI_SYSTEM_TABLE *SystemTable)
{
  return EfiLibInstallDriverBindingComponentName2 (Image, SystemTable, &mDriver, Image, NULL, NULL);
}
