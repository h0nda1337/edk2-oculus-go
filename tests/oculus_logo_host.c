/** Exercise the actual firmware reader with a read-only file as the GPT partition.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <zlib.h>
#undef NULL
#include <Uefi.h>
#include <Display/Framebuffer.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DiskIo.h>
#include <Protocol/PartitionInfo.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include "OculusLogo.h"

EFI_GUID gEfiBlockIoProtocolGuid, gEfiDiskIoProtocolGuid, gEfiPartitionInfoProtocolGuid;
STATIC EFI_PARTITION_INFO_PROTOCOL Part;
STATIC EFI_BLOCK_IO_MEDIA Media;
STATIC EFI_BLOCK_IO_PROTOCOL Block;
STATIC EFI_DISK_IO_PROTOCOL Disk;
STATIC EFI_BOOT_SERVICES Services;
EFI_BOOT_SERVICES *gBS = &Services;
STATIC FILE *Stock;
STATIC UINTN Reads, Pools;
STATIC BOOLEAN Available, BadHeader, Corrupt, ReadError;

VOID *EFIAPI AllocatePool (UINTN Size) { ++Pools; return malloc (Size); }
VOID EFIAPI FreePool (VOID *P) { assert (Pools && P); --Pools; free (P); }
INTN EFIAPI CompareMem (CONST VOID *A, CONST VOID *B, UINTN Size) { return memcmp (A, B, Size); }
STATIC EFI_STATUS EFIAPI Crc (VOID *Data, UINTN Size, UINT32 *Value) {
  *Value = crc32 (0, Data, Size); return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI List (EFI_LOCATE_SEARCH_TYPE Type, EFI_GUID *Id, VOID *Key, UINTN *Count, EFI_HANDLE **Handles) {
  assert (Type == ByProtocol && Id == &gEfiPartitionInfoProtocolGuid);
  if (!Available) {return EFI_NOT_FOUND;}
  *Count = 1; *Handles = AllocatePool (sizeof (EFI_HANDLE)); **Handles = (VOID *)&Part;
  return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Protocol (EFI_HANDLE Handle, EFI_GUID *Id, VOID **Out) {
  assert (Handle == (VOID *)&Part);
  if (Id == &gEfiPartitionInfoProtocolGuid) { *Out = &Part; }
  else if (Id == &gEfiBlockIoProtocolGuid) { *Out = &Block; }
  else if (Id == &gEfiDiskIoProtocolGuid) { *Out = &Disk; }
  else { return EFI_UNSUPPORTED; }
  return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Read (EFI_DISK_IO_PROTOCOL *This, UINT32 Id, UINT64 Offset, UINTN Len, VOID *Data) {
  assert (This == &Disk && Id == 7);
  assert ((Offset == 0 && Len == 24) || (Offset == 512 + (558*1440+657)*3 && Len == 203*4320+378));
  ++Reads;
  if (ReadError) {return EFI_MEDIA_CHANGED;}
  assert (fseek (Stock, Offset, SEEK_SET) == 0 && fread (Data, 1, Len, Stock) == Len);
  if (BadHeader && Offset == 0) {((UINT8 *)Data)[0] ^= 1;}
  if (Corrupt && Offset != 0) {memset (Data, 0, Len);}
  return EFI_SUCCESS;
}

int main (int Argc, char **Argv) {
  assert (Argc == 2);
  Stock = fopen (Argv[1], "rb"); assert (Stock);
  void *Frame = mmap ((void *)(UINTN)GO_FB_BASE, GO_FB_SIZE, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
  assert (Frame == (void *)(UINTN)GO_FB_BASE);
  Services.CalculateCrc32 = Crc; Services.LocateHandleBuffer = List; Services.HandleProtocol = Protocol;
  Disk.ReadDisk = Read; Block.Media = &Media;
  Media = (EFI_BLOCK_IO_MEDIA){ .MediaId = 7, .LogicalPartition = TRUE, .MediaPresent = TRUE,
                               .BlockSize = 4096, .LastBlock = 34226176/4096-1 };
  Part.Type = PARTITION_TYPE_GPT;
  memcpy (Part.Info.Gpt.PartitionName, L"splash", sizeof (L"splash"));
  GO_OCULUS_LOGO FromDisk, FromScreen;
  assert (!GoReadOculusLogo (&FromDisk) && Reads == 0);
  Available = TRUE;
  assert (GoReadOculusLogo (&FromDisk) == GoLogoPartition && Reads == 2 && crc32 (0, (void *)&FromDisk, sizeof FromDisk) == 0x93104dc6);
  BadHeader = TRUE; assert (!GoReadOculusLogo (&FromDisk) && Reads == 3); BadHeader = FALSE;
  Corrupt = TRUE; assert (!GoReadOculusLogo (&FromDisk) && Reads == 5); Corrupt = FALSE;
  ReadError = TRUE; assert (!GoReadOculusLogo (&FromDisk) && Reads == 6); ReadError = FALSE;
  Part.Info.Gpt.PartitionName[0] = 'x'; assert (!GoReadOculusLogo (&FromDisk) && Reads == 6);
  assert (fseek (Stock, 512, SEEK_SET) == 0 && fread (Frame, 1, GO_FB_SIZE, Stock) == GO_FB_SIZE);
  assert (GoReadOculusLogo (&FromScreen) == GoLogoFramebuffer && crc32 (0, (void *)&FromScreen, sizeof FromScreen) == 0x93104dc6);
  memset (Frame, 0, GO_FB_SIZE/2);
  assert (GoReadOculusLogo (&FromScreen) == GoLogoFramebuffer && crc32 (0, (void *)&FromScreen, sizeof FromScreen) == 0x05be5f49);
  Part.Info.Gpt.PartitionName[0] = 's';
  assert (GoReadOculusLogo (&FromScreen) == GoLogoPartition && Reads == 8);
  assert (crc32 (0, (void *)&FromScreen, sizeof FromScreen) == 0x93104dc6 && Pools == 0);
  munmap (Frame, GO_FB_SIZE); fclose (Stock);
  puts ("PASS: both inherited eyes, stock partition reads, wrong label/header/pixels, media change and absent disk");
  return 0;
}
