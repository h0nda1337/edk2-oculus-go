/** Test the production Go DXE host binding, resource handoff and Shell reader.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "PlatformFixture.h"
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DevicePathLib.h>
#include <Library/GoUfsSplashLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/DriverBinding.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/IoMmu.h>
#include <Protocol/PciIo.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/ScsiPassThruExt.h>
#include <Protocol/UfsHostController.h>

STATIC EFI_STATUS
ReadCase (EFI_HANDLE Esp, PLATFORM_CASE *Mode)
{
  STATIC CONST struct { CHAR16 *Name; PLATFORM_CASE Mode; } Markers[] = {
    { L"BOUNCE", Bounce }, { L"DENYTAIL", DenyTail }, { L"SHORTMAP", ShortTail },
    { L"OTHERDMA", WrongHandle }, { L"NODMA", MissingDma }, { L"BUSY", BusyHandoff }, { L"NOGRANT", RejectProbe },
    { L"RETRY", RetryRevoke }, { L"ALLOC", Allocation }, { L"NOLUN4", MissingLun }, { L"GPT", Gpt }
  };
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
  EFI_STATUS Status = gBS->HandleProtocol (Esp, &gEfiSimpleFileSystemProtocolGuid, (VOID **)&Fs);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  EFI_FILE_PROTOCOL *Root;
  Status = Fs->OpenVolume (Fs, &Root);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  *Mode = Direct;
  for (UINTN I = 0; I < ARRAY_SIZE (Markers); ++I) {
    EFI_FILE_PROTOCOL *File;
    Status = Root->Open (Root, &File, Markers[I].Name, EFI_FILE_MODE_READ, 0);
    if (Status == EFI_NOT_FOUND) {
      Status = EFI_SUCCESS;
      continue;
    }
    if (EFI_ERROR (Status)) {
      break;
    }
    File->Close (File);
    if (*Mode != Direct) {
      Status = EFI_INVALID_PARAMETER;
      break;
    }
    *Mode = Markers[I].Mode;
  }
  Root->Close (Root);
  return Status;
}

STATIC EFI_STATUS
LoadBinding (EFI_HANDLE Image, EFI_HANDLE Esp, CHAR16 *Name, EFI_DRIVER_BINDING_PROTOCOL **Binding)
{
  EFI_DEVICE_PATH_PROTOCOL *Path = FileDevicePath (Esp, Name);
  if (Path == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  EFI_HANDLE Driver = NULL;
  EFI_STATUS Status = gBS->LoadImage (FALSE, Image, Path, NULL, 0, &Driver);
  FreePool (Path);
  if (!EFI_ERROR (Status)) {
    Status = gBS->StartImage (Driver, NULL, NULL);
  }
  if (!EFI_ERROR (Status)) {
    Status = gBS->HandleProtocol (Driver, &gEfiDriverBindingProtocolGuid, (VOID **)Binding);
  }
  return Status;
}

STATIC BOOLEAN
MatchFixturePartition (GO_READ_SPLASH_BYTES Read, VOID *Context, UINT64 Bytes, GO_OCULUS_LOGO *Logo)
{
  STATIC CONST CHAR8 Marker[] = "GO-UFS-PLATFORM";
  UINT8 Buffer[sizeof (Marker)];
  return Bytes == EFI_PAGE_SIZE && !EFI_ERROR (Read (Context, 0, sizeof (Buffer), Buffer)) &&
         CompareMem (Buffer, Marker, sizeof (Marker)) == 0;
}

STATIC EFI_STATUS
TestCapacity (EFI_HANDLE Controller)
{
  GO_UFS_CAPACITY_SAMPLE Sample;
  SetMem (&Sample, sizeof (Sample), 0xa5);
  EFI_STATUS Status = GoUfsTestLun4Buffer (Controller, &Sample);
  if (EFI_ERROR (Status)) {
    return IsZeroBuffer (&Sample, sizeof (Sample)) ? Status : EFI_PROTOCOL_ERROR;
  }
  for (UINTN I = 0; I < 2; ++I) {
    Print (L"PLATFORM END %u CPU %lx DMA %lx BYTES ", I, Sample.Cpu[I], Sample.Dma[I]);
    for (UINTN B = 0; B < sizeof (Sample.Capacity[I]); ++B) {
      Print (L"%02x", Sample.Capacity[I][B]);
    }
    Print (L"\r\n");
  }
  return EFI_SUCCESS;
}

// Every address in this exercise is within the two pages returned by the
// tested provider. A partial release must not return either page to firmware.
STATIC EFI_STATUS
CheckAllocation (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *Hc)
{
  VOID *Base = NULL;
  EFI_STATUS Status = Hc->AllocateBuffer (Hc, AllocateAnyPages, EfiBootServicesData, 2, &Base, 0);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  if (Hc->FreeBuffer (Hc, 1, Base) != EFI_INVALID_PARAMETER ||
      Hc->FreeBuffer (Hc, 1, (UINT8 *)Base + EFI_PAGE_SIZE) != EFI_INVALID_PARAMETER) {
    return EFI_PROTOCOL_ERROR;
  }
  UINTN Bytes = EFI_PAGE_SIZE;
  EFI_PHYSICAL_ADDRESS Bus;
  VOID *Token = NULL;
  Status = Hc->Map (Hc, EdkiiUfsHcOperationBusMasterCommonBuffer, Base, &Bytes, &Bus, &Token);
  if (EFI_ERROR (Status) || Bytes != EFI_PAGE_SIZE) {
    return EFI_DEVICE_ERROR;
  }
  if (Hc->FreeBuffer (Hc, 2, Base) != EFI_ACCESS_DENIED || EFI_ERROR (Hc->Unmap (Hc, Token))) {
    return EFI_PROTOCOL_ERROR;
  }
  Status = Hc->FreeBuffer (Hc, 2, Base);
  if (!EFI_ERROR (Status)) {
    Print (L"PLATFORM OWNED ALLOCATION VERIFIED\r\n");
  }
  return Status;
}

STATIC EFI_STATUS
Run (EFI_HANDLE Image)
{
  EFI_LOADED_IMAGE_PROTOCOL *App;
  EFI_STATUS Status = gBS->HandleProtocol (Image, &gEfiLoadedImageProtocolGuid, (VOID **)&App);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  PLATFORM_CASE Mode;
  Status = ReadCase (App->DeviceHandle, &Mode);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  VOID *GlobalBefore = NULL;
  EFI_STATUS GlobalStatus = gBS->LocateProtocol (&gEdkiiIoMmuProtocolGuid, NULL, &GlobalBefore);
  EFI_HANDLE Controller;
  Status = PublishFixture (Mode, &Controller);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  VOID *GlobalAfter = NULL;
  if (gBS->LocateProtocol (&gEdkiiIoMmuProtocolGuid, NULL, &GlobalAfter) != GlobalStatus ||
      GlobalAfter != GlobalBefore) {
    return EFI_PROTOCOL_ERROR;
  }
  Print (L"PLATFORM PCI DMA SERVICE PRESERVED\r\n");
  VOID *Existing;
  if (!EFI_ERROR (gBS->HandleProtocol (Controller, &gEfiPciIoProtocolGuid, &Existing)) ||
      !EFI_ERROR (gBS->LocateProtocol (&gEdkiiUfsHostControllerProtocolGuid, NULL, &Existing))) {
    return EFI_ALREADY_STARTED;
  }
  EFI_DRIVER_BINDING_PROTOCOL *Board;
  Status = LoadBinding (Image, App->DeviceHandle, L"\\GoUfsHcDxe.efi", &Board);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  EFI_DRIVER_BINDING_PROTOCOL *Transport;
  Status = LoadBinding (Image, App->DeviceHandle, L"\\UfsPassThruDxe.efi", &Transport);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  BOOLEAN Bds = Mode == Gpt || Mode == MissingLun;
  if (Bds) {
    // Start with the platform handle alone. Let the normal BDS reader connect
    // both drivers and run its own capacity checks before sector reads.
    GO_OCULUS_LOGO Ignored;
    BOOLEAN Found = GoReadUfsLogo (MatchFixturePartition, &Ignored);
    if (Found != (Mode == Gpt)) {
      Print (L"PLATFORM BDS LOOKUP %u HC %r SCSI %r PCI %r\r\n", (UINTN)Found,
             gBS->HandleProtocol (Controller, &gEdkiiUfsHostControllerProtocolGuid, &Existing),
             gBS->HandleProtocol (Controller, &gEfiExtScsiPassThruProtocolGuid, &Existing),
             gBS->HandleProtocol (Controller, &gEfiPciIoProtocolGuid, &Existing));
      return EFI_PROTOCOL_ERROR;
    }
    Print (L"PLATFORM BDS %s\r\n", Found ? L"GPT MARKER FOUND" : L"LUN 4 ABSENT");
  } else {
    Status = Board->Supported (Board, Controller, NULL);
    if (!EFI_ERROR (Status)) {
      Status = Board->Start (Board, Controller, NULL);
    }
  }

  EDKII_UFS_HOST_CONTROLLER_PROTOCOL *Hc;
  BOOLEAN Published = !EFI_ERROR (gBS->HandleProtocol (Controller, &gEdkiiUfsHostControllerProtocolGuid,
                                                       (VOID **)&Hc));
  Print (L"PLATFORM BIND %r HC %u PCI 0\r\n", Status, (UINTN)Published);
  if (EFI_ERROR (Status) || !Published) {
    return EFI_ERROR (Status) && !Published ? Status : EFI_PROTOCOL_ERROR;
  }
  if (!EFI_ERROR (gBS->HandleProtocol (Controller, &gEfiPciIoProtocolGuid, &Existing))) {
    return EFI_PROTOCOL_ERROR;
  }
  UINTN Base = 0;
  Status = Hc->GetUfsHcMmioBar (Hc, &Base);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Print (L"PLATFORM HC BAR %lx\r\n", (UINT64)Base);
  if (Mode == Allocation) {
    Status = CheckAllocation (Hc);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  if (!Bds) {
    Status = Transport->Supported (Transport, Controller, NULL);
    if (!EFI_ERROR (Status)) {
      Status = Transport->Start (Transport, Controller, NULL);
    }
  } else {
    Status = gBS->HandleProtocol (Controller, &gEfiExtScsiPassThruProtocolGuid, &Existing);
  }
  Print (L"PLATFORM TRANSPORT %r\r\n", Status);
  if (!EFI_ERROR (Status)) {
    if (!Bds) {
      Status = TestCapacity (Controller);
    }
    EFI_STATUS Stopped = Transport->Stop (Transport, Controller, 0, NULL);
    Print (L"PLATFORM STOP TRANSPORT %r\r\n", Stopped);
    if (EFI_ERROR (Stopped)) {
      return Stopped;
    }
  }
  EFI_STATUS Stopped = Board->Stop (Board, Controller, 0, NULL);
  Print (L"PLATFORM STOP HC %r\r\n", Stopped);
  if (EFI_ERROR (Stopped)) {
    return Stopped;
  }
  if (!EFI_ERROR (gBS->HandleProtocol (Controller, &gEdkiiUfsHostControllerProtocolGuid, &Existing))) {
    return EFI_PROTOCOL_ERROR;
  }
  return Status;
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE Image, EFI_SYSTEM_TABLE *Table)
{
  EFI_STATUS Status = Run (Image);
  PrintFixtureStats ();
  Print (L"PLATFORM RESULT %r\r\n", Status);
  Table->RuntimeServices->ResetSystem (EfiResetShutdown, Status, 0, NULL);
  return Status;
}
