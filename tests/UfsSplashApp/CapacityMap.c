/** QEMU/AAVMF only. Observe the provider's actual DMA map on a synchronous SCSI read.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "ConnectProvider.h"
#include <IndustryStandard/Scsi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/PciIo.h>
#include <Protocol/ScsiPassThruExt.h>
#include <Protocol/UfsHostController.h>

#define WINDOW    0x80440000ULL
#define PAGES     4
#define LUN4      0x400   // EDK2 extended SCSI flat-space LUN encoding
#define CAP_BYTES 8
STATIC CONST UINT8 Expected[CAP_BYTES] = { 0, 0x11, 0xff, 0xff, 0, 0, 0x10, 0 };
STATIC EDKII_UFS_HC_MAP mMap;
STATIC VOID *mExpectedHost;
STATIC EFI_PHYSICAL_ADDRESS mBus;
STATIC UINTN mMappings;

STATIC EFI_STATUS EFIAPI
ObserveMap (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EDKII_UFS_HOST_CONTROLLER_OPERATION Operation,
            VOID *Host, UINTN *Length, EFI_PHYSICAL_ADDRESS *Bus, VOID **Mapping)
{
  EFI_STATUS Status = mMap (This, Operation, Host, Length, Bus, Mapping);
  if (!EFI_ERROR (Status) && Operation == EdkiiUfsHcOperationBusMasterWrite &&
      Host == mExpectedHost && *Length == CAP_BYTES) {
    ++mMappings;
    mBus = *Bus;
  }
  return Status;
}

STATIC UINT8
Canary (UINTN I)
{
  return (UINT8)(0x6dU ^ (I >> 12) ^ I);
}

STATIC EFI_STATUS
Sample (EFI_EXT_SCSI_PASS_THRU_PROTOCOL *Scsi, UINT8 *Target, UINT8 *Window, UINTN Page)
{
  UINTN Offset = Page * EFI_PAGE_SIZE;
  UINT8 *Dest = Window + Offset;
  for (UINTN Attempt = 0; Attempt < 2; ++Attempt) {
    EFI_EXT_SCSI_PASS_THRU_SCSI_REQUEST_PACKET Packet = { 0 };
    UINT8 Cdb[10] = { EFI_SCSI_OP_READ_CAPACITY };
    UINT8 Sense[32] = { 0 };
    Packet.Cdb = Cdb;
    Packet.CdbLength = sizeof (Cdb);
    Packet.DataDirection = EFI_EXT_SCSI_DATA_DIRECTION_READ;
    Packet.InDataBuffer = Dest;
    Packet.InTransferLength = CAP_BYTES;
    Packet.SenseData = Sense;
    Packet.SenseDataLength = sizeof (Sense);
    Packet.Timeout = 10000000;
    mMappings = 0;
    mExpectedHost = Dest;
    EFI_STATUS Status = Scsi->PassThru (Scsi, Target, LUN4, &Packet, NULL);
    mExpectedHost = NULL;
    if (mMappings != 1) {
      return EFI_NO_MAPPING;
    }
    for (UINTN I = 0; I < PAGES * EFI_PAGE_SIZE; ++I) {
      if ((I < Offset || I >= Offset + CAP_BYTES) && Window[I] != Canary (I)) {
        return EFI_COMPROMISED_DATA;
      }
    }
    if (Attempt == 0 && Packet.TargetStatus == EFI_EXT_SCSI_STATUS_TARGET_CHECK_CONDITION &&
        Packet.SenseDataLength >= 14 && (Sense[0] & 0x7f) == 0x70 &&
        (Sense[2] & 15) == 6 && Sense[12] == 0x29 && Sense[13] == 0) {
      continue;
    }
    if (EFI_ERROR (Status) || Packet.HostAdapterStatus != 0 || Packet.TargetStatus != 0 ||
        Packet.InTransferLength != CAP_BYTES) {
      return EFI_DEVICE_ERROR;
    }
    if (CompareMem (Dest, Expected, CAP_BYTES) != 0) {
      return EFI_VOLUME_CORRUPTED;
    }
    Print (L"UFS-MAP PAGE %u CPU %lx BUS %lx DATA 0011FFFF00001000\r\n",
           (UINT32)Page, (UINT64)(UINTN)Dest, mBus);
    for (UINTN I = 0; I < CAP_BYTES; ++I) {
      Dest[I] = Canary (Offset + I);
    }
    return EFI_SUCCESS;
  }
  return EFI_DEVICE_ERROR;
}

STATIC EFI_STATUS
Measure (EFI_HANDLE Image)
{
  EFI_LOADED_IMAGE_PROTOCOL *App;
  EFI_STATUS Status = gBS->HandleProtocol (Image, &gEfiLoadedImageProtocolGuid, (VOID **)&App);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = ConnectProvider (Image, App->DeviceHandle, L"\\UfsPciHcDxe.efi", &gEfiPciIoProtocolGuid);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = ConnectProvider (Image, App->DeviceHandle, L"\\UfsPassThruDxe.efi", &gEdkiiUfsHostControllerProtocolGuid);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  EFI_HANDLE *Handles;
  UINTN Count;
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEdkiiUfsHostControllerProtocolGuid, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  EFI_EXT_SCSI_PASS_THRU_PROTOCOL *Scsi;
  EDKII_UFS_HOST_CONTROLLER_PROTOCOL *Hc;
  Status = (Count == 1) ? gBS->HandleProtocol (Handles[0], &gEfiExtScsiPassThruProtocolGuid,
                                               (VOID **)&Scsi) : EFI_UNSUPPORTED;
  if (!EFI_ERROR (Status)) {
    Status = gBS->HandleProtocol (Handles[0], &gEdkiiUfsHostControllerProtocolGuid, (VOID **)&Hc);
  }
  gBS->FreePool (Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }

  UINT8 Id[TARGET_MAX_BYTES];
  UINT8 *Target = Id;
  UINT64 Lun = 0;
  SetMem (Id, sizeof (Id), 0xff);
  for (UINTN I = 0; I < 32; ++I) {
    Status = Scsi->GetNextTargetLun (Scsi, &Target, &Lun);
    if (EFI_ERROR (Status) || Lun == LUN4) {
      break;
    }
  }
  if (EFI_ERROR (Status) || Lun != LUN4) {
    return EFI_NOT_FOUND;
  }

  EFI_PHYSICAL_ADDRESS Physical = WINDOW;
  Status = gBS->AllocatePages (AllocateAddress, EfiBootServicesData, PAGES, &Physical);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  UINT8 *Window = (UINT8 *)(UINTN)Physical;
  for (UINTN I = 0; I < PAGES * EFI_PAGE_SIZE; ++I) {
    Window[I] = Canary (I);
  }
  // This dedicated VM has no storage stack above the synchronous pass-through provider.
  // Delegate every call and preserve the original handle, length and return values.
  mMap = Hc->Map;
  Hc->Map = ObserveMap;
  for (UINTN Page = 0; Page < PAGES; ++Page) {
    Status = Sample (Scsi, Target, Window, Page);
    if (EFI_ERROR (Status)) {
      break;
    }
  }
  Hc->Map = mMap;
  if (!EFI_ERROR (Status)) {
    Status = gBS->FreePages (Physical, PAGES);
  }
  // A failed or timed-out request may still reference the buffer until VM shutdown.
  return Status;
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE Image, EFI_SYSTEM_TABLE *Table)
{
  EFI_STATUS Status = Measure (Image);
  Print (L"UFS-MAP RESULT %r\r\n", Status);
  Table->RuntimeServices->ResetSystem (EfiResetShutdown, Status, 0, NULL);
  return Status;
}
