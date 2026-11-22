/** Read a named GPT slice over a UFS transport. No public raw-disk interface.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <IndustryStandard/Scsi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/GoUfsSplashLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/GoUfsCapacity.h>
#include <Protocol/ScsiPassThruExt.h>
#include <Protocol/UfsHostController.h>
#include <Uefi/UefiGpt.h>

#define WINDOW_BYTES SIZE_64KB
#define PACIFIC_LUN4 0x0400U  // UEFI extended SCSI LUN encoding
#define PACIFIC_LAST_LBA 0x0011ffffU
#define PACIFIC_BLOCK_BYTES 4096U
#define CAPACITY_BYTES 8U
#define GUARD_BYTE 0xa5

typedef struct {
  EFI_EXT_SCSI_PASS_THRU_PROTOCOL *Bus;
  GO_UFS_CAPACITY_PROTOCOL *CapacityIo;
  UINT8 Target[TARGET_MAX_BYTES];
  UINT64 Lun;
  UINT8 *Window;
  UINT8 *Sense;
  UINT32 BlockSize;
  UINT32 LastBlock;
  UINT64 First;
  UINT64 Bytes;
} GO_UFS_LUN;

// The caller supplies an operation, never an arbitrary CDB. Both operations
// have only an inbound data phase. READ(10) suffices for this device.
STATIC EFI_STATUS
ReadCommand (GO_UFS_LUN *Disk, BOOLEAN Capacity, UINT32 Lba, UINT16 Blocks,
             UINT8 *Destination, EFI_PHYSICAL_ADDRESS *Dma)
{
  UINT8 Cdb[10] = { 0 };
  UINT32 Bytes = Capacity ? CAPACITY_BYTES : Blocks * Disk->BlockSize;
  if (Capacity) {
    Cdb[0] = EFI_SCSI_OP_READ_CAPACITY;
  } else {
    if (Blocks == 0 || Bytes > WINDOW_BYTES || Lba > Disk->LastBlock ||
        Blocks - 1U > Disk->LastBlock - Lba) {
      return EFI_INVALID_PARAMETER;
    }
    Cdb[0] = EFI_SCSI_OP_READ10;
    WriteUnaligned32 ((UINT32 *)&Cdb[2], SwapBytes32 (Lba));
    WriteUnaligned16 ((UINT16 *)&Cdb[7], SwapBytes16 (Blocks));
  }

  EFI_EXT_SCSI_PASS_THRU_SCSI_REQUEST_PACKET Packet = { 0 };
  Packet.Timeout = EFI_TIMER_PERIOD_SECONDS (2);
  Packet.Cdb = Cdb;
  Packet.CdbLength = sizeof (Cdb);
  Packet.DataDirection = EFI_EXT_SCSI_DATA_DIRECTION_READ;
  Packet.InDataBuffer = Destination;
  Packet.SenseData = Disk->Sense;
  // A device may report a power-on unit attention on its first command.
  // Retry that one read once with a fresh transfer length and sense buffer.
  for (UINTN Attempt = 0; Attempt < 2; ++Attempt) {
    ZeroMem (Disk->Sense, 18);
    Packet.SenseDataLength = 18;
    Packet.InTransferLength = Bytes;
    Packet.HostAdapterStatus = 0;
    Packet.TargetStatus = 0;
    EFI_STATUS Status;
    if (Dma != NULL) {
      Status = Disk->CapacityIo->ReadCapacity (Disk->CapacityIo, Disk->Target, &Packet, Dma);
    } else {
      Status = Disk->Bus->PassThru (Disk->Bus, Disk->Target, Disk->Lun, &Packet, NULL);
    }
    if ((EFI_ERROR (Status) && Status != EFI_DEVICE_ERROR) ||
        Packet.HostAdapterStatus != EFI_EXT_SCSI_STATUS_HOST_ADAPTER_OK) {
      return EFI_ERROR (Status) ? Status : EFI_DEVICE_ERROR;
    }
    if (Packet.TargetStatus == EFI_EXT_SCSI_STATUS_TARGET_GOOD) {
      return !EFI_ERROR (Status) && Packet.InTransferLength == Bytes ? EFI_SUCCESS : EFI_DEVICE_ERROR;
    }
    UINT8 Format = Disk->Sense[0] & 0x7f;
    BOOLEAN Attention = Packet.SenseDataLength >= 3 && (Format == 0x70 || Format == 0x71) &&
                        (Disk->Sense[2] & 0xf) == EFI_SCSI_SK_UNIT_ATTENTION;
    if (Packet.SenseDataLength >= 2 && (Format == 0x72 || Format == 0x73)) {
      Attention = (Disk->Sense[1] & 0xf) == EFI_SCSI_SK_UNIT_ATTENTION;
    }
    if (Packet.TargetStatus != EFI_EXT_SCSI_STATUS_TARGET_CHECK_CONDITION || !Attention) {
      break;
    }
  }
  return EFI_DEVICE_ERROR;
}

STATIC EFI_STATUS
ReadSlice (VOID *Context, UINT64 Offset, UINTN Size, VOID *Buffer)
{
  GO_UFS_LUN *Disk = Context;
  if (Offset > Disk->Bytes || Size > Disk->Bytes - Offset || (Size != 0 && Buffer == NULL)) {
    return EFI_INVALID_PARAMETER;
  }
  UINT8 *Out = Buffer;
  while (Size != 0) {
    UINT32 Skip = (UINT32)(Offset % Disk->BlockSize);
    UINTN Take = MIN (Size, WINDOW_BYTES - Skip);
    UINT16 Blocks = (UINT16)((Skip + Take + Disk->BlockSize - 1) / Disk->BlockSize);
    EFI_STATUS Status = ReadCommand (Disk, FALSE, (UINT32)(Disk->First + Offset / Disk->BlockSize), Blocks, Disk->Window, NULL);
    if (EFI_ERROR (Status)) {
      return Status;
    }
    CopyMem (Out, Disk->Window + Skip, Take);
    Offset += Take;
    Out += Take;
    Size -= Take;
  }
  return EFI_SUCCESS;
}

// A broken primary GPT is a failed lookup. Never repair it from the backup.
STATIC BOOLEAN
FindSplash (GO_UFS_LUN *Disk)
{
  if (EFI_ERROR (ReadCommand (Disk, FALSE, PRIMARY_PART_HEADER_LBA, 1, Disk->Window, NULL))) {
    return FALSE;
  }
  EFI_PARTITION_TABLE_HEADER Header;
  CopyMem (&Header, Disk->Window, sizeof (Header));
  UINT32 Crc;
  ((EFI_PARTITION_TABLE_HEADER *)Disk->Window)->Header.CRC32 = 0;
  if (Header.Header.Signature != EFI_PTAB_HEADER_ID || Header.Header.Revision != 0x10000 || Header.Header.Reserved != 0 ||
      Header.Header.HeaderSize < sizeof (Header) || Header.Header.HeaderSize > Disk->BlockSize ||
      EFI_ERROR (gBS->CalculateCrc32 (Disk->Window, Header.Header.HeaderSize, &Crc)) ||
      Crc != Header.Header.CRC32 || Header.MyLBA != PRIMARY_PART_HEADER_LBA ||
      Header.AlternateLBA != Disk->LastBlock || Header.LastUsableLBA >= Disk->LastBlock ||
      Header.FirstUsableLBA > Header.LastUsableLBA || Header.PartitionEntryLBA < 2 ||
      Header.PartitionEntryLBA >= Header.FirstUsableLBA) {
    return FALSE;
  }
  UINT32 Stride = Header.SizeOfPartitionEntry;
  UINT32 Count = Header.NumberOfPartitionEntries;
  if (Stride < sizeof (EFI_PARTITION_ENTRY) || (Stride & (Stride - 1)) != 0 ||
      Count == 0 || Count > WINDOW_BYTES / Stride) {
    return FALSE;
  }
  UINT32 Length = Count * Stride;
  UINT16 Blocks = (UINT16)((Length + Disk->BlockSize - 1) / Disk->BlockSize);
  if (Blocks > Header.FirstUsableLBA - Header.PartitionEntryLBA ||
      EFI_ERROR (ReadCommand (Disk, FALSE, (UINT32)Header.PartitionEntryLBA, Blocks, Disk->Window, NULL)) ||
      EFI_ERROR (gBS->CalculateCrc32 (Disk->Window, Length, &Crc)) || Crc != Header.PartitionEntryArrayCRC32) {
    return FALSE;
  }
  BOOLEAN Found = FALSE;
  CONST EFI_GUID Empty = { 0 };
  for (UINT32 Index = 0; Index < Count; ++Index) {
    EFI_PARTITION_ENTRY *Entry = (EFI_PARTITION_ENTRY *)(Disk->Window + Index * Stride);
    if (CompareGuid (&Entry->PartitionTypeGUID, &Empty) ||
        CompareMem (Entry->PartitionName, L"splash", sizeof (L"splash")) != 0) {
      continue;
    }
    if (Found || Entry->StartingLBA < Header.FirstUsableLBA || Entry->EndingLBA > Header.LastUsableLBA ||
        Entry->EndingLBA < Entry->StartingLBA) {
      return FALSE;
    }
    Found = TRUE;
    Disk->First = Entry->StartingLBA;
    Disk->Bytes = (Entry->EndingLBA - Entry->StartingLBA + 1) * Disk->BlockSize;
  }
  return Found;
}

// A map belongs to one synchronous request. Each endpoint gets its own mapping.
STATIC EFI_STATUS
MeasurePacificPage (GO_UFS_LUN *Disk, GO_UFS_CAPACITY_SAMPLE *Sample)
{
  GO_UFS_CAPACITY_SAMPLE Complete = { 0 };
  UINT8 *Guard = Disk->Window - EFI_PAGE_SIZE;
  UINTN GuardedBytes = (UINTN)(Disk->Sense - Guard);
  for (UINTN End = 0; End < 2; ++End) {
    UINT8 *Data = Disk->Window + (End == 0 ? 0 : EFI_PAGE_SIZE - CAPACITY_BYTES);
    SetMem (Guard, GuardedBytes, GUARD_BYTE);
    EFI_STATUS Status = ReadCommand (Disk, TRUE, 0, 0, Data, &Complete.Dma[End]);
    if (EFI_ERROR (Status)) {
      return Status;
    }
    Complete.Cpu[End] = (EFI_PHYSICAL_ADDRESS)(UINTN)Data;
    CopyMem (Complete.Capacity[End], Data, CAPACITY_BYTES);
    SetMem (Data, CAPACITY_BYTES, GUARD_BYTE);
    for (UINTN Byte = 0; Byte < GuardedBytes; ++Byte) {
      if (Guard[Byte] != GUARD_BYTE) {
        return EFI_COMPROMISED_DATA;
      }
    }
    Disk->LastBlock = SwapBytes32 (ReadUnaligned32 ((UINT32 *)Complete.Capacity[End]));
    Disk->BlockSize = SwapBytes32 (ReadUnaligned32 ((UINT32 *)(Complete.Capacity[End] + 4)));
    if (Disk->LastBlock != PACIFIC_LAST_LBA || Disk->BlockSize != PACIFIC_BLOCK_BYTES) {
      return EFI_VOLUME_CORRUPTED;
    }
  }
  DEBUG ((DEBUG_INFO, "Go UFS: LUN 4 capacity, CPU %Lx/%Lx DMA %Lx/%Lx, last LBA %x block %u\n",
          Complete.Cpu[0], Complete.Cpu[1], Complete.Dma[0], Complete.Dma[1],
          Disk->LastBlock, Disk->BlockSize));
  if (Sample != NULL) {
    CopyMem (Sample, &Complete, sizeof (Complete));
  }
  return EFI_SUCCESS;
}

// Some existing virtual disks put splash on another ordinary unit. Retain that
// discovery path when the controller does not enumerate Pacific's LUN 4.
STATIC BOOLEAN
FindOtherUnit (GO_UFS_LUN *Disk, GO_DECODE_SPLASH Decode, GO_OCULUS_LOGO *Logo)
{
  UINT8 TargetId[TARGET_MAX_BYTES];
  SetMem (TargetId, sizeof (TargetId), 0xff);
  UINT8 *Target = TargetId;
  for (UINTN Iter = 0; Iter < 32; ++Iter) {
    if (EFI_ERROR (Disk->Bus->GetNextTargetLun (Disk->Bus, &Target, &Disk->Lun))) {
      break;
    }
    if ((Disk->Lun & ~0x0700ULL) != 0 || Disk->Lun == PACIFIC_LUN4) {
      continue;
    }
    CopyMem (Disk->Target, Target, sizeof (Disk->Target));
    if (EFI_ERROR (ReadCommand (Disk, TRUE, 0, 0, Disk->Window, NULL))) {
      continue;
    }
    Disk->LastBlock = SwapBytes32 (ReadUnaligned32 ((UINT32 *)Disk->Window));
    Disk->BlockSize = SwapBytes32 (ReadUnaligned32 ((UINT32 *)(Disk->Window + 4)));
    if (Disk->LastBlock != MAX_UINT32 && Disk->BlockSize >= 512 && Disk->BlockSize <= 4096 &&
        (Disk->BlockSize & (Disk->BlockSize - 1)) == 0 &&
        FindSplash (Disk) && Decode (ReadSlice, Disk, Disk->Bytes, Logo)) {
      return TRUE;
    }
  }
  return FALSE;
}

STATIC EFI_STATUS
VisitController (EFI_HANDLE Controller, GO_DECODE_SPLASH Decode, GO_OCULUS_LOGO *Logo,
                 GO_UFS_CAPACITY_SAMPLE *Sample)
{
  GO_UFS_LUN Disk = { 0 };
  EFI_STATUS Status = gBS->HandleProtocol (Controller, &gEfiExtScsiPassThruProtocolGuid, (VOID **)&Disk.Bus);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = gBS->HandleProtocol (Controller, &gGoUfsCapacityProtocolGuid, (VOID **)&Disk.CapacityIo);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  UINTN Alignment = Disk.Bus->Mode->IoAlign;
  if (Alignment > CAPACITY_BYTES || (Alignment != 0 && (Alignment & (Alignment - 1)) != 0)) {
    return EFI_UNSUPPORTED;
  }

  // The first data page is used again for the first GPT block. The logo reader
  // batches later blocks in adjacent pages. Keep sense outside the guard area.
  UINTN Workspace = Decode == NULL ? EFI_PAGE_SIZE : WINDOW_BYTES;
  UINTN Pages = EFI_SIZE_TO_PAGES (Workspace) + 2;
  EFI_PHYSICAL_ADDRESS Base = 0;
  Status = gBS->AllocatePages (AllocateAnyPages, EfiBootServicesData, Pages, &Base);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Disk.Window = (UINT8 *)(UINTN)Base + EFI_PAGE_SIZE;
  Disk.Sense = (UINT8 *)(UINTN)Base + EFI_PAGES_TO_SIZE (Pages) - 32;
  UINT8 TargetId[TARGET_MAX_BYTES];
  SetMem (TargetId, sizeof (TargetId), 0xff);
  UINT8 *Target = TargetId;
  for (UINTN Iter = 0; Iter < 32; ++Iter) {
    Status = Disk.Bus->GetNextTargetLun (Disk.Bus, &Target, &Disk.Lun);
    if (EFI_ERROR (Status)) {
      if (Status == EFI_NOT_FOUND && Decode != NULL && FindOtherUnit (&Disk, Decode, Logo)) {
        Status = EFI_SUCCESS;
      }
      break;
    }
    if (Disk.Lun == PACIFIC_LUN4) {
      CopyMem (Disk.Target, Target, sizeof (Disk.Target));
      Status = MeasurePacificPage (&Disk, Sample);
      if (!EFI_ERROR (Status) && Decode != NULL &&
          !(FindSplash (&Disk) && Decode (ReadSlice, &Disk, Disk.Bytes, Logo))) {
        Status = EFI_NOT_FOUND;
      }
      break;
    }
    Status = EFI_NOT_FOUND;
  }
  EFI_STATUS Released = gBS->FreePages (Base, Pages);
  return EFI_ERROR (Released) ? Released : Status;
}

EFI_STATUS
GoUfsTestLun4Buffer (EFI_HANDLE Controller, GO_UFS_CAPACITY_SAMPLE *Result)
{
  if (Result == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  ZeroMem (Result, sizeof (*Result));
  if (Controller == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  EFI_STATUS Status = VisitController (Controller, NULL, NULL, Result);
  if (EFI_ERROR (Status)) {
    ZeroMem (Result, sizeof (*Result));
  }
  return Status;
}

BOOLEAN
GoReadUfsLogo (GO_DECODE_SPLASH Decode, GO_OCULUS_LOGO *Logo)
{
  EFI_HANDLE *Handles;
  UINTN Count;
  if (Decode == NULL || Logo == NULL ||
      EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEdkiiUfsHostControllerProtocolGuid, NULL, &Count, &Handles))) {
    return FALSE;
  }
  BOOLEAN Found = FALSE;
  for (UINTN Index = 0; Index < Count && !Found; ++Index) {
    VOID *CapacityIo;
    if (EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gGoUfsCapacityProtocolGuid, &CapacityIo))) {
      // Give the FV transport a chance to bind to this UFS controller only.
      gBS->ConnectController (Handles[Index], NULL, NULL, FALSE);
    }
    Found = !EFI_ERROR (VisitController (Handles[Index], Decode, Logo, NULL));
  }
  FreePool (Handles);
  return Found;
}
