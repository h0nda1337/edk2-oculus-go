/** Exercise the Shell's production capacity gate in an isolated QEMU guest.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "ConnectProvider.h"
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/GoUfsSplashLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/PciIo.h>
#include <Protocol/ScsiPassThruExt.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/UfsHostController.h>

typedef enum { Normal, DenyTail, ShortTail, Bounce, Guard } FIXTURE;

typedef struct {
  VOID                 *Cpu;
  EFI_PHYSICAL_ADDRESS Dma;
  VOID                 *ProviderCookie;
  VOID                 *Staging;
  UINTN                Length;
  UINT8                Data[8];
  BOOLEAN              Closed;
} MAP_EVENT;

STATIC FIXTURE mFixture;
STATIC EDKII_UFS_HC_MAP mMap;
STATIC EDKII_UFS_HC_UNMAP mUnmap;
// Initial unit attention can add one mapping per endpoint.
STATIC MAP_EVENT mEvent[4];
STATIC UINTN mMaps, mUnmaps, mDenied, mShort;
STATIC BOOLEAN mOracleError;

STATIC EFI_STATUS
ReadFixture (EFI_HANDLE Device)
{
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
  EFI_FILE_PROTOCOL *Root;
  EFI_STATUS Status = gBS->HandleProtocol (Device, &gEfiSimpleFileSystemProtocolGuid, (VOID **)&Fs);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = Fs->OpenVolume (Fs, &Root);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  STATIC CONST struct { CHAR16 *Name; FIXTURE Mode; } Markers[] = {
    { L"DENYTAIL", DenyTail }, { L"SHORTMAP", ShortTail }, { L"BOUNCE", Bounce },
    { L"GUARD", Guard }
  };
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
    if (mFixture != Normal) {
      Status = EFI_INVALID_PARAMETER;
      break;
    }
    mFixture = Markers[I].Mode;
  }
  Root->Close (Root);
  return Status;
}

STATIC EFI_STATUS EFIAPI
ObserveMap (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EDKII_UFS_HOST_CONTROLLER_OPERATION Operation,
            VOID *Host, UINTN *Length, EFI_PHYSICAL_ADDRESS *Bus, VOID **Mapping)
{
  if (Operation != EdkiiUfsHcOperationBusMasterWrite || *Length != 8) {
    return mMap (This, Operation, Host, Length, Bus, Mapping);
  }
  BOOLEAN Tail = (((UINTN)Host & EFI_PAGE_MASK) == EFI_PAGE_SIZE - 8);
  if (Tail && mFixture == DenyTail) {
    ++mDenied;
    return EFI_NO_MAPPING;
  }
  if (mMaps == ARRAY_SIZE (mEvent)) {
    mOracleError = TRUE;
    return EFI_OUT_OF_RESOURCES;
  }
  MAP_EVENT *Event = &mEvent[mMaps];
  Event->Cpu = Host;
  if (Tail && mFixture == ShortTail) {
    ++mShort;
    *Length = 4;
  }
  if (mFixture == Bounce) {
    Event->Staging = AllocatePages (1);
    if (Event->Staging == NULL) {
      return EFI_OUT_OF_RESOURCES;
    }
    CopyMem (Event->Staging, Host, *Length);
  }
  EFI_STATUS Status = mMap (This, Operation, Event->Staging == NULL ? Host : Event->Staging,
                            Length, Bus, &Event->ProviderCookie);
  if (EFI_ERROR (Status)) {
    if (Event->Staging != NULL) {
      FreePages (Event->Staging, 1);
    }
    ZeroMem (Event, sizeof (*Event));
    return Status;
  }
  Event->Dma = *Bus;
  Event->Length = *Length;
  // Test-only tokens disambiguate providers that return a single identity-map cookie.
  *Mapping = Event;
  ++mMaps;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
ObserveUnmap (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, VOID *Mapping)
{
  for (UINTN I = 0; I < mMaps; ++I) {
    MAP_EVENT *Event = &mEvent[I];
    if (Mapping != Event) {
      continue;
    }
    if (Event->Closed) {
      mOracleError = TRUE;
      return EFI_INVALID_PARAMETER;
    }
    EFI_STATUS Status = EFI_SUCCESS;
    if (Event->ProviderCookie != NULL) {
      Status = mUnmap (This, Event->ProviderCookie);
    }
    if (!EFI_ERROR (Status)) {
      if (Event->Staging != NULL) {
        CopyMem (Event->Cpu, Event->Staging, Event->Length);
        FreePages (Event->Staging, 1);
      }
      if (mFixture == Guard && (((UINTN)Event->Cpu & EFI_PAGE_MASK) == EFI_PAGE_SIZE - 8)) {
        // Emulate a one-byte underrun within the owned page on the tail transfer.
        ((UINT8 *)Event->Cpu)[-1] ^= 1;
      }
      CopyMem (Event->Data, Event->Cpu, sizeof (Event->Data));
      Event->Closed = TRUE;
      ++mUnmaps;
    }
    return Status;
  }
  return mUnmap (This, Mapping);
}

STATIC VOID
PrintSample (CONST UINT8 *Data)
{
  Print (L"%08x%08x\r\n", SwapBytes32 (ReadUnaligned32 ((CONST UINT32 *)Data)),
         SwapBytes32 (ReadUnaligned32 ((CONST UINT32 *)(Data + 4))));
}

STATIC EFI_STATUS
CheckResult (EFI_STATUS Status, CONST GO_UFS_CAPACITY_SAMPLE *Result)
{
  for (UINTN I = 0; I < mMaps; ++I) {
    MAP_EVENT *Event = &mEvent[I];
    Print (L"UFS-BUFFER OBS CPU %lx DMA %lx DATA ", (UINT64)(UINTN)Event->Cpu, Event->Dma);
    PrintSample (Event->Data);
  }
  Print (L"UFS-BUFFER MAPS %u UNMAPS %u DENIED %u\r\n", mMaps, mUnmaps, mDenied);
  Print (L"UFS-BUFFER SHORT %u\r\n", mShort);
  if (mOracleError || mMaps != mUnmaps || (EFI_ERROR (Status) && !IsZeroBuffer (Result, sizeof (*Result)))) {
    Print (L"UFS-BUFFER ORACLE ERROR\r\n");
    return EFI_PROTOCOL_ERROR;
  }
  if (EFI_ERROR (Status)) {
    return Status;
  }

  for (UINTN End = 0; End < 2; ++End) {
    // The last observation for this CPU address is the completed retry, if any.
    CONST MAP_EVENT *Match = NULL;
    for (UINTN I = 0; I < mMaps; ++I) {
      if (Result->Cpu[End] == (EFI_PHYSICAL_ADDRESS)(UINTN)mEvent[I].Cpu) {
        Match = &mEvent[I];
      }
    }
    if (Match == NULL || Result->Dma[End] != Match->Dma || Match->Length != 8 ||
        CompareMem (Result->Capacity[End], Match->Data, 8) != 0) {
      Print (L"UFS-BUFFER ORACLE ERROR\r\n");
      return EFI_PROTOCOL_ERROR;
    }
    Print (L"UFS-BUFFER END %u CPU %lx DMA %lx DATA ", End, Result->Cpu[End], Result->Dma[End]);
    PrintSample (Result->Capacity[End]);
  }
  return Status;
}

STATIC EFI_STATUS
Measure (EFI_HANDLE Image)
{
  EFI_LOADED_IMAGE_PROTOCOL *App;
  EFI_STATUS Status = gBS->HandleProtocol (Image, &gEfiLoadedImageProtocolGuid, (VOID **)&App);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = ReadFixture (App->DeviceHandle);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  GO_UFS_CAPACITY_SAMPLE Result;
  SetMem (&Result, sizeof (Result), 0xa5);
  Status = ConnectProvider (Image, App->DeviceHandle, L"\\UfsPciHcDxe.efi", &gEfiPciIoProtocolGuid);
  VOID *Protocol;
  if (Status == EFI_NOT_FOUND &&
      gBS->LocateProtocol (&gEdkiiUfsHostControllerProtocolGuid, NULL, &Protocol) == EFI_NOT_FOUND) {
    Print (L"UFS-BUFFER NO PROVIDER\r\n");
    return CheckResult (GoUfsTestLun4Buffer (Image, &Result), &Result);
  }
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
  EDKII_UFS_HOST_CONTROLLER_PROTOCOL *Hc;
  if (Count != 1) {
    gBS->FreePool (Handles);
    return EFI_UNSUPPORTED;
  }
  EFI_HANDLE Controller = Handles[0];
  gBS->FreePool (Handles);
  Status = gBS->HandleProtocol (Controller, &gEdkiiUfsHostControllerProtocolGuid, (VOID **)&Hc);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = gBS->HandleProtocol (Controller, &gEfiExtScsiPassThruProtocolGuid, &Protocol);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  mMap = Hc->Map;
  mUnmap = Hc->Unmap;
  Hc->Map = ObserveMap;
  Hc->Unmap = ObserveUnmap;
  Status = GoUfsTestLun4Buffer (Controller, &Result);
  Hc->Map = mMap;
  Hc->Unmap = mUnmap;
  return CheckResult (Status, &Result);
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE Image, EFI_SYSTEM_TABLE *Table)
{
  EFI_STATUS Status = Measure (Image);
  Print (L"UFS-BUFFER RESULT %r\r\n", Status);
  Table->RuntimeServices->ResetSystem (EfiResetShutdown, Status, 0, NULL);
  return Status;
}
