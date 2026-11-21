/** Host-only EFI application for a QEMU GPT media test. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DiskIo.h>
#include <Protocol/PartitionInfo.h>
#include <Protocol/SimpleTextOut.h>
#include "OculusLogo.h"

EFI_BOOT_SERVICES *gBS;
EFI_GUID gEfiBlockIoProtocolGuid = EFI_BLOCK_IO_PROTOCOL_GUID;
EFI_GUID gEfiDiskIoProtocolGuid = EFI_DISK_IO_PROTOCOL_GUID;
EFI_GUID gEfiPartitionInfoProtocolGuid = EFI_PARTITION_INFO_PROTOCOL_GUID;

VOID *EFIAPI AllocatePool (UINTN Size) {
  VOID *P;
  return EFI_ERROR (gBS->AllocatePool (EfiBootServicesData, Size, &P)) ? NULL : P;
}
VOID EFIAPI FreePool (VOID *P) { gBS->FreePool (P); }
INTN EFIAPI CompareMem (CONST VOID *A, CONST VOID *B, UINTN Length) {
  CONST UINT8 *X = A, *Y = B;
  for (UINTN I = 0; I < Length; ++I) {
    if (X[I] != Y[I]) { return (INTN)X[I] - Y[I]; }
  }
  return 0;
}

EFI_STATUS EFIAPI TestMain (EFI_HANDLE Image, EFI_SYSTEM_TABLE *St) {
  gBS = St->BootServices;
  // The booted VM may have connected only the ESP. Bind all storage handles
  // before testing the partition discovery used by the Pacific firmware.
  EFI_HANDLE *Handles;
  UINTN Count;
  if (!EFI_ERROR (gBS->LocateHandleBuffer (AllHandles, NULL, NULL, &Count, &Handles))) {
    for (UINTN I = 0; I < Count; ++I) {
      gBS->ConnectController (Handles[I], NULL, NULL, TRUE);
    }
    FreePool (Handles);
  }
  GO_OCULUS_LOGO Logo;
  UINT32 Crc = 0;
  BOOLEAN Found = GoReadPartitionLogo (&Logo);
  if (Found) { gBS->CalculateCrc32 (&Logo, sizeof (Logo), &Crc); }
  St->ConOut->OutputString (St->ConOut, Crc == 0x93104dc6 ? L"GO-GPT-EMBLEM-PASS\r\n" : L"GO-GPT-EMBLEM-MISSING\r\n");
  St->RuntimeServices->ResetSystem (EfiResetShutdown, EFI_SUCCESS, 0, NULL);
  return EFI_SUCCESS;
}
