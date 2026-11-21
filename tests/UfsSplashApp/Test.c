/** QEMU/AAVMF only. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <Library/DevicePathLib.h>
#include <Library/BaseMemoryLib.h>
#include <Protocol/GraphicsOutput.h>
#include <Library/GoUfsSplashLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/DriverBinding.h>
#include <Protocol/PciIo.h>
#include <Protocol/UfsHostController.h>
#include <Protocol/ScsiPassThruExt.h>
#include "../../OculusGoPkg/Drivers/GoBdsDxe/OculusLogo.h"

STATIC EFI_STATUS
ConnectProvider (EFI_HANDLE Image, EFI_HANDLE Esp, CHAR16 *Name, EFI_GUID *Input)
{
  EFI_HANDLE Drivers[2] = { NULL, NULL };
  EFI_DEVICE_PATH_PROTOCOL *Path = FileDevicePath (Esp, Name);
  if (Path == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  EFI_STATUS Status = gBS->LoadImage (FALSE, Image, Path, NULL, 0, &Drivers[0]);
  FreePool (Path);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = gBS->StartImage (Drivers[0], NULL, NULL);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  EFI_HANDLE *Handles;
  UINTN Count;
  Status = gBS->LocateHandleBuffer (ByProtocol, Input, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  EFI_DRIVER_BINDING_PROTOCOL *Binding;
  Status = gBS->HandleProtocol (Drivers[0], &gEfiDriverBindingProtocolGuid, (VOID **)&Binding);
  if (EFI_ERROR (Status)) {
    FreePool (Handles);
    return Status;
  }
  BOOLEAN Connected = FALSE;
  for (UINTN I = 0; I < Count; ++I) {
    // Invoke exactly this driver. ConnectController may try other registered drivers.
    Status = Binding->Supported (Binding, Handles[I], NULL);
    if (!EFI_ERROR (Status)) {
      Status = Binding->Start (Binding, Handles[I], NULL);
    }
    if (!EFI_ERROR (Status)) {
      Connected = TRUE;
    }
  }
  FreePool (Handles);
  return Connected ? EFI_SUCCESS : EFI_NOT_FOUND;
}

STATIC EFI_STATUS
DrawAndCheck (EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop, GO_OCULUS_LOGO *Logo)
{
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Pixels = AllocateZeroPool (sizeof (*Pixels) * sizeof (Logo->Luma));
  if (Pixels == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  UINTN X = (Gop->Mode->Info->HorizontalResolution - GO_LOGO_WIDTH) / 2;
  UINTN Y = (Gop->Mode->Info->VerticalResolution - GO_LOGO_HEIGHT) / 2;
  for (UINTN I = 0; I < sizeof (Logo->Luma); ++I) {
    Pixels[I].Blue = Pixels[I].Green = Pixels[I].Red = ((UINT8 *)Logo->Luma)[I];
  }
  EFI_STATUS Status = Gop->Blt (Gop, Pixels, EfiBltBufferToVideo, 0, 0, X, Y, GO_LOGO_WIDTH, GO_LOGO_HEIGHT, 0);
  if (!EFI_ERROR (Status)) {
    ZeroMem (Pixels, sizeof (*Pixels) * sizeof (Logo->Luma));
    Status = Gop->Blt (Gop, Pixels, EfiBltVideoToBltBuffer, X, Y, 0, 0, GO_LOGO_WIDTH, GO_LOGO_HEIGHT, 0);
    for (UINTN I = 0; I < sizeof (Logo->Luma) && !EFI_ERROR (Status); ++I) {
      UINT8 Gray = ((UINT8 *)Logo->Luma)[I];
      if (Pixels[I].Blue != Gray || Pixels[I].Green != Gray || Pixels[I].Red != Gray) {
        Status = EFI_DEVICE_ERROR;
      }
    }
  }
  FreePool (Pixels);
  return Status;
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE Image, EFI_SYSTEM_TABLE *St)
{
  EFI_LOADED_IMAGE_PROTOCOL *App;
  EFI_STATUS Status = gBS->HandleProtocol (Image, &gEfiLoadedImageProtocolGuid, (VOID **)&App);
  if (!EFI_ERROR (Status)) {
    Status = ConnectProvider (Image, App->DeviceHandle, L"\\UfsPciHcDxe.efi", &gEfiPciIoProtocolGuid);
  }
  Print (L"GO-UFS-HC %r\r\n", Status);
  if (!EFI_ERROR (Status)) {
    Status = ConnectProvider (Image, App->DeviceHandle, L"\\UfsPassThruDxe.efi", &gEdkiiUfsHostControllerProtocolGuid);
  }
  Print (L"GO-UFS-TRANSPORT %r\r\n", Status);
  if (!EFI_ERROR (Status)) {
    EFI_EXT_SCSI_PASS_THRU_PROTOCOL *Bus;
    Status = gBS->LocateProtocol (&gEfiExtScsiPassThruProtocolGuid, NULL, (VOID **)&Bus);
    if (!EFI_ERROR (Status)) {
      UINT8 Id[TARGET_MAX_BYTES];
      UINT8 *Target = Id;
      UINT64 Lun = 0;
      SetMem (Id, sizeof (Id), 0xff);
      for (UINTN I = 0; I < 32 && !EFI_ERROR (Bus->GetNextTargetLun (Bus, &Target, &Lun)); ++I) {
        Print (L"GO-UFS-ADDRESS %lx\r\n", Lun);
      }
    }
    GO_OCULUS_LOGO Logo;
    UINT32 Crc = 0;
    EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop;
    Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&Gop);
    EFI_GRAPHICS_OUTPUT_BLT_PIXEL Black = { 0 };
    if (!EFI_ERROR (Status) && Gop->Mode->Info->HorizontalResolution >= GO_LOGO_WIDTH &&
        Gop->Mode->Info->VerticalResolution >= GO_LOGO_HEIGHT) {
      Status = Gop->Blt (Gop, &Black, EfiBltVideoFill, 0, 0, 0, 0, Gop->Mode->Info->HorizontalResolution,
                         Gop->Mode->Info->VerticalResolution, 0);
    } else {
      Status = EFI_UNSUPPORTED;
    }
    BOOLEAN Found = GoReadUfsLogo (GoDecodeSplash, &Logo);
    Print (L"GO-UFS-GOP-CLEAR %r\r\n", Status);
    if (Found && !EFI_ERROR (Status)) {
      Status = DrawAndCheck (Gop, &Logo);
      Print (L"GO-UFS-GOP-READBACK %r\r\n", Status);
    }
    if (Found && !EFI_ERROR (Status)) {
      Status = gBS->CalculateCrc32 (&Logo, sizeof (Logo), &Crc);
    }
    Print (L"GO-UFS-RESULT %s %08x\r\n", Found && !EFI_ERROR (Status) ? L"FOUND" : L"ABSENT", Crc);
  }
  St->RuntimeServices->ResetSystem (EfiResetShutdown, EFI_SUCCESS, 0, NULL);
  return EFI_SUCCESS;
}
