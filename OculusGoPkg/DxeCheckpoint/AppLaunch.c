/** Load an application by its firmware volume device path using UEFI Boot Services.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Library/DevicePathLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include "AppLaunch.h"

EFI_HANDLE mTrialAppHandle;
extern EFI_GUID gOculusGoConsoleProbeFileGuid;

STATIC __attribute__((noinline,noreturn)) VOID
TrialAppRejected (VOID)
{
  for (;;) {
    __asm__ volatile ("wfe");
  }
}

VOID
TrialLaunchApplication (VOID)
{
  MEDIA_FW_VOL_FILEPATH_DEVICE_PATH Node;
  EFI_DEVICE_PATH_PROTOCOL *Volume = DevicePathFromHandle (mTrialFvHandle);
  if (Volume == NULL) {
    TrialAppRejected ();
  }
  Node.Header.Type = MEDIA_DEVICE_PATH;
  Node.Header.SubType = MEDIA_PIWG_FW_FILE_DP;
  SetDevicePathNodeLength (&Node.Header, sizeof (Node));
  CopyGuid (&Node.FvFileName, &gOculusGoConsoleProbeFileGuid);
  EFI_DEVICE_PATH_PROTOCOL *Path = AppendDevicePathNode (Volume, &Node.Header);
  if (Path == NULL) {
    TrialAppRejected ();
  }
  EFI_STATUS Status = gBS->LoadImage (FALSE, gImageHandle, Path, NULL, 0, &mTrialAppHandle);
  gBS->FreePool (Path);
  if (Status != EFI_SUCCESS) {
    if (mTrialAppHandle != NULL) {
      gBS->UnloadImage (mTrialAppHandle);
    }
    TrialAppRejected ();
  }
  EFI_LOADED_IMAGE_PROTOCOL *Image;
  if (gBS->HandleProtocol (mTrialAppHandle, &gEfiLoadedImageProtocolGuid, (VOID **)&Image) != EFI_SUCCESS ||
      Image->DeviceHandle != mTrialFvHandle || Image->ParentHandle != gImageHandle || Image->SystemTable != gST ||
      Image->ImageCodeType != EfiLoaderCode || Image->ImageDataType != EfiLoaderData ||
      Image->FilePath == NULL || CompareMem (Image->FilePath, &Node, sizeof (Node)) != 0 ||
      !IsDevicePathEnd (NextDevicePathNode (Image->FilePath)) || !TrialSealApplication (Image)) {
    gBS->UnloadImage (mTrialAppHandle);
    TrialAppRejected ();
  }
  Status = gBS->StartImage (mTrialAppHandle, NULL, NULL);
  mTrialAppHandle = NULL;
  if (Status != EFI_SUCCESS) {
    TrialAppRejected ();
  }
  __asm__ volatile ("dsb sy\n.global TrialAppComplete\nTrialAppComplete: wfe\n b TrialAppComplete" ::: "memory");
  __builtin_unreachable ();
}
