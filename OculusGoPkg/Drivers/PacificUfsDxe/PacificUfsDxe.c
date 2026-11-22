/** Publish the controller identified by the Pacific EVT device tree.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Library/DebugLib.h>
#include <Library/HobLib.h>
#include <Library/IoLib.h>
#include <Library/NonDiscoverableDeviceRegistrationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Platform/PacificUfs.h>
#include <Protocol/PacificUfsHandoff.h>

STATIC EFI_HANDLE mController;

STATIC EFI_STATUS EFIAPI
PacificUfsPrepare (NON_DISCOVERABLE_DEVICE *Device)
{
  if (Device == NULL || Device->Resources == NULL || mController == NULL ||
      Device->Resources[0].AddrRangeMin != PACIFIC_UFS_BASE ||
      Device->Resources[0].AddrLen != PACIFIC_UFS_LENGTH) {
    return EFI_INVALID_PARAMETER;
  }
  GO_PACIFIC_UFS_HANDOFF_PROTOCOL *Handoff;
  EFI_STATUS Status = gBS->HandleProtocol (mController, &gGoPacificUfsHandoffProtocolGuid,
                                           (VOID **)&Handoff);
  if (EFI_ERROR (Status) || Handoff == NULL || Handoff->ConfirmReleased == NULL) {
    return EFI_NOT_READY;
  }
  Status = Handoff->ConfirmReleased (Handoff, mController);
  if (Status != EFI_SUCCESS) {
    return EFI_ERROR (Status) ? Status : EFI_NOT_READY;
  }

  // UFSHCI 1.1 VER, HCE, transfer/task Run-Stop and doorbells. Check the
  // actual release against live state before allowing transport initialization.
  UINTN Base = (UINTN)Device->Resources[0].AddrRangeMin;
  if (MmioRead32 (Base + 0x08) != 0x00010100) {
    return EFI_UNSUPPORTED;
  }
  if ((MmioRead32 (Base + 0x34) > 1) || (MmioRead32 (Base + 0x60) != 0) ||
      (MmioRead32 (Base + 0x80) != 0) || (MmioRead32 (Base + 0x58) != 0) ||
      (MmioRead32 (Base + 0x78) != 0)) {
    return EFI_NOT_READY;
  }
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
PacificUfsEntry (EFI_HANDLE Image, EFI_SYSTEM_TABLE *SystemTable)
{
  VOID *Hob = GetFirstGuidHob (&gOculusGoUfsResourceGuid);
  if (Hob == NULL) {
    return EFI_NOT_FOUND;
  }
  if (GET_GUID_HOB_DATA_SIZE (Hob) != sizeof (GO_PACIFIC_UFS_RESOURCE)) {
    return EFI_COMPROMISED_DATA;
  }
  CONST GO_PACIFIC_UFS_RESOURCE *Ufs = GET_GUID_HOB_DATA (Hob);
  if (Ufs->Base != PACIFIC_UFS_BASE || Ufs->Length != PACIFIC_UFS_LENGTH || Ufs->DmaCoherent > 1) {
    return EFI_COMPROMISED_DATA;
  }
  EFI_STATUS Status = RegisterNonDiscoverableMmioDevice (
                        NonDiscoverableDeviceTypeUfs,
                        Ufs->DmaCoherent ? NonDiscoverableDeviceDmaTypeCoherent : NonDiscoverableDeviceDmaTypeNonCoherent,
                        PacificUfsPrepare, &mController, 1, (UINTN)Ufs->Base, (UINTN)Ufs->Length);
  DEBUG ((DEBUG_INFO, "Pacific UFS: register %Lx + %x: %r\n", Ufs->Base, Ufs->Length, Status));
  return Status;
}
