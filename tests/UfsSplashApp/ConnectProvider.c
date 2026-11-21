/** QEMU-only transport setup. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "ConnectProvider.h"
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/DriverBinding.h>

EFI_STATUS
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
