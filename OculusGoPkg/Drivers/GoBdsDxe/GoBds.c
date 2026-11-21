/** Minimal platform boot policy: the inherited display and the Shell in this FV.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include "Welcome.h"
#include <Display/TextModes.h>
#include <Guid/EventGroup.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/PcdLib.h>
#include <Protocol/Bds.h>
#include <Protocol/GraphicsOutput.h>
#include <Protocol/LoadedImage.h>

extern EFI_GUID gUefiShellFileGuid;
extern EFI_GUID gOculusGoDisplayFileGuid;

STATIC EFI_STATUS
SelectDisplay (VOID)
{
  EFI_HANDLE *Handles;
  UINTN Count;
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *Text;
  EFI_STATUS Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiGraphicsOutputProtocolGuid,
                                  NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = EFI_NOT_FOUND;
  for (UINTN Index = 0; Index < Count; ++Index) {
    EFI_DEVICE_PATH_PROTOCOL *Path = DevicePathFromHandle (Handles[Index]);
    if (Path == NULL || DevicePathType (Path) != HARDWARE_DEVICE_PATH ||
        DevicePathSubType (Path) != HW_VENDOR_DP || DevicePathNodeLength (Path) != sizeof (VENDOR_DEVICE_PATH) ||
        !CompareGuid (&((VENDOR_DEVICE_PATH *)Path)->Guid, &gOculusGoDisplayFileGuid) ||
        !IsDevicePathEnd (NextDevicePathNode (Path))) {
      continue;
    }
    Status = gBS->HandleProtocol (Handles[Index], &gEfiSimpleTextOutProtocolGuid, (VOID **)&Text);
    if (EFI_ERROR (Status)) {
      break;
    }
    Status = Text->SetMode (Text, GO_TEXT_MODE_WIDE);
    if (EFI_ERROR (Status)) {
      break;
    }
    gST->ConsoleOutHandle = gST->StandardErrorHandle = Handles[Index];
    gST->ConOut = gST->StdErr = Text;
    gST->Hdr.CRC32 = 0;
    Status = gBS->CalculateCrc32 (gST, gST->Hdr.HeaderSize, &gST->Hdr.CRC32);
    break;
  }
  FreePool (Handles);
  return Status;
}

STATIC EFI_STATUS
BootShell (VOID)
{
  EFI_LOADED_IMAGE_PROTOCOL *Parent;
  EFI_HANDLE Child = NULL;
  MEDIA_FW_VOL_FILEPATH_DEVICE_PATH Node;
  GO_OCULUS_LOGO Logo;
  BOOLEAN HasLogo = FixedPcdGetBool (PcdGoWelcomeEnabled) && GoReadOculusLogo (&Logo);
  EFI_STATUS Status = SelectDisplay ();
  if (EFI_ERROR (Status) || gST->ConIn == NULL || gST->ConsoleInHandle == NULL) {
    return EFI_ERROR (Status) ? Status : EFI_NOT_READY;
  }
  Status = gBS->HandleProtocol (gImageHandle, &gEfiLoadedImageProtocolGuid, (VOID **)&Parent);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  EFI_DEVICE_PATH_PROTOCOL *Volume = DevicePathFromHandle (Parent->DeviceHandle);
  if (Volume == NULL) {
    return EFI_NOT_FOUND;
  }
  EfiInitializeFwVolDevicepathNode (&Node, &gUefiShellFileGuid);
  EFI_DEVICE_PATH_PROTOCOL *Path = AppendDevicePathNode (Volume, &Node.Header);
  if (Path == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  if (FixedPcdGetBool (PcdGoWelcomeEnabled)) {
    EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop;
    EFI_STATUS Intro = gBS->HandleProtocol (gST->ConsoleOutHandle,
                                             &gEfiGraphicsOutputProtocolGuid, (VOID **)&Gop);
    if (!EFI_ERROR (Intro)) {
      Intro = GoPlayWelcome (Gop, HasLogo ? &Logo : NULL);
      // The shorter text window no longer covers the outer rows of the intro.
      EFI_GRAPHICS_OUTPUT_BLT_PIXEL Black = {0, 0, 0, 0};
      Gop->Blt (Gop, &Black, EfiBltVideoFill, 0, 0, 0, 0,
                Gop->Mode->Info->HorizontalResolution, Gop->Mode->Info->VerticalResolution, 0);
      gST->ConOut->ClearScreen (gST->ConOut);
      if (HasLogo) {
        EFI_STATUS Badge = GoShowShellLogo (Gop, &Logo);
        DEBUG ((DEBUG_INFO, "Go BDS: Shell emblem returned %r\n", Badge));
      }
    }
    DEBUG ((DEBUG_INFO, "Go BDS: welcome scene returned %r\n", Intro));
  }
  EfiSignalEventReadyToBoot ();
  Status = gBS->LoadImage (FALSE, gImageHandle, Path, NULL, 0, &Child);
  FreePool (Path);
  if (EFI_ERROR (Status)) {
    if (Child != NULL) {
      gBS->UnloadImage (Child);
    }
    return Status;
  }
  return gBS->StartImage (Child, NULL, NULL);
}

STATIC VOID EFIAPI
GoBdsEntry (EFI_BDS_ARCH_PROTOCOL *This)
{
  CONST CHAR16 *Vendor = FixedPcdGetPtr (PcdFirmwareVendor);
  gST->FirmwareVendor = AllocateRuntimeCopyPool (StrSize (Vendor), Vendor);
  if (gST->FirmwareVendor == NULL) {
    CpuDeadLoop ();
  }
  gST->FirmwareRevision = FixedPcdGet32 (PcdFirmwareRevision);
  gST->Hdr.CRC32 = 0;
  EFI_STATUS CrcStatus = gBS->CalculateCrc32 (gST, gST->Hdr.HeaderSize, &gST->Hdr.CRC32);
  if (EFI_ERROR (CrcStatus)) {
    CpuDeadLoop ();
  }
  EfiEventGroupSignal (&gEfiEndOfDxeEventGroupGuid);
  EFI_STATUS Status = BootShell ();
  DEBUG ((DEBUG_ERROR, "Go BDS: Shell returned %r\n", Status));
  if (gST->ConOut != NULL) {
    Print (L"\r\nBDS: Shell returned %r\r\n", Status);
  }
  CpuDeadLoop ();
}

STATIC EFI_BDS_ARCH_PROTOCOL mBds = { GoBdsEntry };

EFI_STATUS EFIAPI
GoBdsInitialize (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
  return gBS->InstallMultipleProtocolInterfaces (&ImageHandle, &gEfiBdsArchProtocolGuid, &mBds, NULL);
}
