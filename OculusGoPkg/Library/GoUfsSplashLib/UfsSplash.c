/** Read a named GPT slice over a UFS transport. No public raw-disk interface.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <IndustryStandard/Scsi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/GoUfsSplashLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/ScsiPassThruExt.h>
#include <Protocol/UfsHostController.h>
#include <Uefi/UefiGpt.h>

#define WINDOW_BYTES SIZE_64KB

typedef struct {
  EFI_EXT_SCSI_PASS_THRU_PROTOCOL *Bus;
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
ReadCommand (GO_UFS_LUN *Disk, BOOLEAN Capacity, UINT32 Lba, UINT16 Blocks)
{
  UINT8 Cdb[10] = { 0 };
  UINT32 Bytes = Capacity ? 8 : Blocks * Disk->BlockSize;
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
  Packet.InDataBuffer = Disk->Window;
  Packet.SenseData = Disk->Sense;
  // A device may report a power-on unit attention on its first command.
  // Retry that one read once with a fresh transfer length and sense buffer.
  for (UINTN Attempt = 0; Attempt < 2; ++Attempt) {
    ZeroMem (Disk->Sense, 18);
    Packet.SenseDataLength = 18;
    Packet.InTransferLength = Bytes;
    Packet.HostAdapterStatus = 0;
    Packet.TargetStatus = 0;
    EFI_STATUS Status = Disk->Bus->PassThru (Disk->Bus, Disk->Target, Disk->Lun, &Packet, NULL);
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
    EFI_STATUS Status = ReadCommand (Disk, FALSE, (UINT32)(Disk->First + Offset / Disk->BlockSize), Blocks);
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
  if (EFI_ERROR (ReadCommand (Disk, TRUE, 0, 0))) {
    return FALSE;
  }
  Disk->LastBlock = SwapBytes32 (ReadUnaligned32 ((UINT32 *)Disk->Window));
  Disk->BlockSize = SwapBytes32 (ReadUnaligned32 ((UINT32 *)(Disk->Window + 4)));
  if (Disk->LastBlock == MAX_UINT32 || Disk->BlockSize < 512 || Disk->BlockSize > 4096 ||
      (Disk->BlockSize & (Disk->BlockSize - 1)) != 0 ||
      EFI_ERROR (ReadCommand (Disk, FALSE, PRIMARY_PART_HEADER_LBA, 1))) {
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
      EFI_ERROR (ReadCommand (Disk, FALSE, (UINT32)Header.PartitionEntryLBA, Blocks)) ||
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

STATIC BOOLEAN
VisitController (EFI_EXT_SCSI_PASS_THRU_PROTOCOL *Bus, GO_DECODE_SPLASH Decode, GO_OCULUS_LOGO *Logo)
{
  GO_UFS_LUN Disk = { 0 };
  Disk.Bus = Bus;
  UINTN Alignment = Bus->Mode->IoAlign;
  if (Alignment > WINDOW_BYTES || (Alignment != 0 && (Alignment & (Alignment - 1)) != 0)) {
    return FALSE;
  }
  UINTN Pages = EFI_SIZE_TO_PAGES (WINDOW_BYTES + 18);
  Disk.Window = AllocateAlignedPages (Pages, MAX (EFI_PAGE_SIZE, Alignment));
  if (Disk.Window == NULL) {
    return FALSE;
  }
  Disk.Sense = Disk.Window + WINDOW_BYTES;
  BOOLEAN Found = FALSE;
  UINT8 TargetId[TARGET_MAX_BYTES];
  SetMem (TargetId, sizeof (TargetId), 0xff);
  UINT8 *Target = TargetId;
  // The pinned UFS enumerator returns ordinary units and well-known units.
  // Never send a CDB to boot, device-management or RPMB LUNs.
  for (UINTN Iter = 0; Iter < 32; ++Iter) {
    if (EFI_ERROR (Bus->GetNextTargetLun (Bus, &Target, &Disk.Lun))) {
      break;
    }
    if ((Disk.Lun & ~0x0700ULL) != 0) {
      continue;
    }
    CopyMem (Disk.Target, Target, sizeof (Disk.Target));
    if (FindSplash (&Disk) && Decode (ReadSlice, &Disk, Disk.Bytes, Logo)) {
      Found = TRUE;
      break;
    }
  }
  FreeAlignedPages (Disk.Window, Pages);
  return Found;
}

BOOLEAN
GoReadUfsLogo (GO_DECODE_SPLASH Decode, GO_OCULUS_LOGO *Logo)
{
  EFI_HANDLE *Handles;
  UINTN Count;
  if (EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEdkiiUfsHostControllerProtocolGuid, NULL, &Count, &Handles))) {
    return FALSE;
  }
  BOOLEAN Found = FALSE;
  for (UINTN Index = 0; Index < Count && !Found; ++Index) {
    EFI_EXT_SCSI_PASS_THRU_PROTOCOL *Bus;
    if (!EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiExtScsiPassThruProtocolGuid, (VOID **)&Bus))) {
      Found = VisitController (Bus, Decode, Logo);
    }
  }
  FreePool (Handles);
  return Found;
}
