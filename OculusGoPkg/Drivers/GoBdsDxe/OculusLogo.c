/** Read the stock Pacific emblem before BDS clears the inherited scanout.
    Pixel geometry and fingerprints: docs/OCULUS_LOGO.md.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>
#include <Display/Framebuffer.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DiskIo.h>
#include <Protocol/PartitionInfo.h>
#include "OculusLogo.h"

#define SPLASH_PARTITION_BYTES  34226176U
#define SPLASH_HEADER_BYTES     512U
#define SOURCE_X                657U
#define SCALE                   3U
#define SOURCE_WIDTH            (GO_LOGO_HEIGHT * SCALE)
#define SOURCE_ROWS             (GO_LOGO_WIDTH * SCALE)
#define CROP_BYTES              ((SOURCE_ROWS - 1) * GO_FB_STRIDE + SOURCE_WIDTH * GO_FB_BYTES_PER_PIXEL)

STATIC CONST UINTN  mFirstRow[] = { 558, 1799 };
STATIC CONST UINT32 mLogoCrc[]  = { 0x93104dc6, 0x05be5f49 };

STATIC UINTN
CropOffset (UINTN Eye)
{
  return mFirstRow[Eye] * GO_FB_STRIDE + SOURCE_X * GO_FB_BYTES_PER_PIXEL;
}

// Rotate the native scanout into the worn orientation and box-filter 3x3 pixels.
// Each fingerprint identifies the reduced mark from one eye of the stock splash.
STATIC BOOLEAN
SampleCrop (CONST UINT8 *Crop, GO_OCULUS_LOGO *Logo, UINTN Eye)
{
  for (UINTN Y = 0; Y < GO_LOGO_HEIGHT; ++Y) {
    for (UINTN X = 0; X < GO_LOGO_WIDTH; ++X) {
      CONST UINT8 *Pixel = Crop + X * SCALE * GO_FB_STRIDE +
                           (GO_LOGO_HEIGHT - 1 - Y) * SCALE * GO_FB_BYTES_PER_PIXEL;
      UINTN Sum = 0;
      for (UINTN Row = 0; Row < SCALE; ++Row) {
        for (UINTN Byte = 0; Byte < SCALE * GO_FB_BYTES_PER_PIXEL; ++Byte) {
          Sum += Pixel[Row * GO_FB_STRIDE + Byte];
        }
      }
      UINT8 Gray = (UINT8)(Sum / (SCALE * SCALE * GO_FB_BYTES_PER_PIXEL));
      Logo->Luma[Y][X] = Gray > 8 ? Gray : 0;
    }
  }
  UINT32 Crc;
  return !EFI_ERROR (gBS->CalculateCrc32 (Logo, sizeof (*Logo), &Crc)) && Crc == mLogoCrc[Eye];
}

STATIC BOOLEAN
ReadPartition (EFI_HANDLE Handle, GO_OCULUS_LOGO *Logo)
{
  EFI_PARTITION_INFO_PROTOCOL *Part;
  EFI_BLOCK_IO_PROTOCOL *Block;
  EFI_DISK_IO_PROTOCOL *Disk;
  CONST CHAR16 Label[] = L"splash";
  if (EFI_ERROR (gBS->HandleProtocol (Handle, &gEfiPartitionInfoProtocolGuid, (VOID **)&Part)) ||
      Part->Type != PARTITION_TYPE_GPT ||
      CompareMem (Part->Info.Gpt.PartitionName, Label, sizeof (Label)) != 0 ||
      EFI_ERROR (gBS->HandleProtocol (Handle, &gEfiBlockIoProtocolGuid, (VOID **)&Block)) ||
      EFI_ERROR (gBS->HandleProtocol (Handle, &gEfiDiskIoProtocolGuid, (VOID **)&Disk))) {
    return FALSE;
  }
  EFI_BLOCK_IO_MEDIA *Media = Block->Media;
  if (Media == NULL || !Media->LogicalPartition || !Media->MediaPresent || Media->BlockSize == 0 ||
      SPLASH_PARTITION_BYTES % Media->BlockSize != 0 ||
      Media->LastBlock != SPLASH_PARTITION_BYTES / Media->BlockSize - 1) {
    return FALSE;
  }
  // Width, height, uncompressed type and block count in the verified stock header.
  struct { CHAR8 Magic[8]; UINT32 Width, Height, Type, Blocks; } Header;
  UINT32 MediaId = Media->MediaId;
  if (EFI_ERROR (Disk->ReadDisk (Disk, MediaId, 0, sizeof (Header), &Header)) ||
      CompareMem (Header.Magic, "SPLASH!!", 8) != 0 || Header.Width != GO_FB_WIDTH ||
      Header.Height != GO_FB_HEIGHT || Header.Type != 0 || Header.Blocks != 0) {
    return FALSE;
  }
  UINT8 *Crop = AllocatePool (CROP_BYTES);
  if (Crop == NULL) {
    return FALSE;
  }
  EFI_STATUS Status = Disk->ReadDisk (Disk, MediaId, SPLASH_HEADER_BYTES + CropOffset (0), CROP_BYTES, Crop);
  BOOLEAN Found = !EFI_ERROR (Status) && SampleCrop (Crop, Logo, 0);
  FreePool (Crop);
  return Found;
}

BOOLEAN
GoReadPartitionLogo (GO_OCULUS_LOGO *Logo)
{
  EFI_HANDLE *Handles;
  UINTN Count;
  if (EFI_ERROR (gBS->LocateHandleBuffer (ByProtocol, &gEfiPartitionInfoProtocolGuid, NULL, &Count, &Handles))) {
    return FALSE;
  }
  BOOLEAN Found = FALSE;
  for (UINTN Index = 0; Index < Count && !Found; ++Index) {
    Found = ReadPartition (Handles[Index], Logo);
  }
  FreePool (Handles);
  return Found;
}

GO_LOGO_SOURCE
GoReadOculusLogo (GO_OCULUS_LOGO *Logo)
{
  if (GoReadPartitionLogo (Logo)) {
    return GoLogoPartition;
  }
  CONST UINT8 *Frame = (CONST UINT8 *)(UINTN)GO_FB_BASE;
  for (UINTN Eye = 0; Eye < ARRAY_SIZE (mFirstRow); ++Eye) {
    if (SampleCrop (Frame + CropOffset (Eye), Logo, Eye)) {
      return GoLogoFramebuffer;
    }
  }
  return GoLogoAbsent;
}
