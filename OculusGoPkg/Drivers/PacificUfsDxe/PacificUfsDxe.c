/** Publish the controller identified by the Pacific EVT device tree.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Library/DebugLib.h>
#include <Library/HobLib.h>
#include <Library/GoUfsHandoffLib.h>
#include <Library/NonDiscoverableDeviceRegistrationLib.h>
#include <Platform/PacificUfs.h>

STATIC EFI_HANDLE mController;

STATIC EFI_STATUS EFIAPI
PacificUfsPrepare (NON_DISCOVERABLE_DEVICE *Device)
{
  if (Device == NULL || Device->Resources == NULL || mController == NULL ||
      Device->Resources[0].AddrRangeMin != PACIFIC_UFS_BASE ||
      Device->Resources[0].AddrLen != PACIFIC_UFS_LENGTH) {
    return EFI_INVALID_PARAMETER;
  }
  return GoUfsCheckHandoff (mController, (UINTN)Device->Resources[0].AddrRangeMin, 0x00010100);
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
