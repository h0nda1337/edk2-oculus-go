/** @file
  Single-mode GOP over packed BGR888 RAM for the inherited Pacific splash surface.
  SEC_C identified byte 0 as blue and byte 2 as red on the inherited surface.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiDxe.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Display/Framebuffer.h>
#include <Protocol/GraphicsOutput.h>
#ifdef OCULUS_GO_GOP_DEVICE_PATH
#include <Protocol/DevicePathUtilities.h>
#ifdef OCULUS_GO_TEXT
#include "TextConsole.h"
#endif
#endif

STATIC EFI_GRAPHICS_OUTPUT_MODE_INFORMATION mInfo = {
  0, GO_FB_WIDTH, GO_FB_HEIGHT, PixelBltOnly,
  { 0, 0, 0, 0 }, GO_FB_WIDTH
};
STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE mMode = {
  1, 0, &mInfo, sizeof (mInfo), 0, 0
};
STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL mGop;

STATIC EFI_STATUS EFIAPI
QueryMode (
  IN EFI_GRAPHICS_OUTPUT_PROTOCOL *This,
  IN UINT32 ModeNumber,
  OUT UINTN *SizeOfInfo,
  OUT EFI_GRAPHICS_OUTPUT_MODE_INFORMATION **Info
  )
{
  if ((This != &mGop) || (ModeNumber != 0) || (SizeOfInfo == NULL) || (Info == NULL)) {
    return EFI_INVALID_PARAMETER;
  }
  *Info = AllocateCopyPool (sizeof (mInfo), &mInfo);
  if (*Info == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  *SizeOfInfo = sizeof (mInfo);
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
SetMode (IN EFI_GRAPHICS_OUTPUT_PROTOCOL *This, IN UINT32 ModeNumber)
{
  if (This != &mGop) {
    return EFI_INVALID_PARAMETER;
  }
  if (ModeNumber != 0) {
    return EFI_UNSUPPORTED;
  }
  ZeroMem ((VOID *)(UINTN)GO_FB_BASE, GO_FB_SIZE);
  return EFI_SUCCESS;
}

STATIC BOOLEAN
OnScreen (UINTN X, UINTN Y, UINTN Width, UINTN Height)
{
  return (X < GO_FB_WIDTH) && (Y < GO_FB_HEIGHT) &&
         (Width <= GO_FB_WIDTH - X) && (Height <= GO_FB_HEIGHT - Y);
}

STATIC UINT8 *
ScreenPixel (UINTN X, UINTN Y)
{
  return (UINT8 *)(UINTN)GO_FB_BASE + Y * GO_FB_STRIDE + X * GO_FB_BYTES_PER_PIXEL;
}

// Width and Height already fit the screen. The caller supplies the allocation,
// but even an invalid origin, pitch or pointer must never wrap our arithmetic.
STATIC BOOLEAN
BufferFits (
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Buffer, UINTN X, UINTN Y,
  UINTN Width, UINTN Height, UINTN *Delta
  )
{
  UINTN LastRow;
  UINTN LastByte;
  UINTN Available;

  if (Buffer == NULL) {
    return FALSE;
  }
  if (*Delta == 0) {
    if ((X != 0) || (Y != 0)) {
      return FALSE;
    }
    *Delta = Width * sizeof (*Buffer);
  }
  if ((Width > *Delta / sizeof (*Buffer)) ||
      (X > *Delta / sizeof (*Buffer) - Width) ||
      (Y > MAX_UINTN - (Height - 1))) {
    return FALSE;
  }
  LastRow = Y + (Height - 1);
  LastByte = (X + Width) * sizeof (*Buffer) - 1;
  Available = MAX_UINTN - (UINTN)Buffer;
  return (LastByte <= Available) && (LastRow <= (Available - LastByte) / *Delta);
}

STATIC VOID
WritePixel (UINT8 *Video, CONST EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Pixel)
{
  Video[0] = Pixel->Blue;
  Video[1] = Pixel->Green;
  Video[2] = Pixel->Red;
}

STATIC EFI_STATUS EFIAPI
Blt (
  IN EFI_GRAPHICS_OUTPUT_PROTOCOL *This,
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL *BltBuffer OPTIONAL,
  IN EFI_GRAPHICS_OUTPUT_BLT_OPERATION Operation,
  IN UINTN SourceX, IN UINTN SourceY, IN UINTN DestinationX, IN UINTN DestinationY,
  IN UINTN Width, IN UINTN Height, IN UINTN Delta OPTIONAL
  )
{
  UINTN Row;
  UINTN Col;
  UINTN Offset;
  UINT8 *Video;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL *BufferRow;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Color;

  if ((This != &mGop) || (Width == 0) || (Height == 0)) {
    return EFI_INVALID_PARAMETER;
  }
  switch (Operation) {
    case EfiBltVideoFill:
      if (!OnScreen (DestinationX, DestinationY, Width, Height) ||
          (BltBuffer == NULL) || ((UINTN)BltBuffer > MAX_UINTN - (sizeof (Color) - 1))) {
        return EFI_INVALID_PARAMETER;
      }
      Color = BltBuffer[0];
      for (Row = 0; Row < Height; Row++) {
        Video = ScreenPixel (DestinationX, DestinationY + Row);
        for (Col = 0; Col < Width; Col++) {
          WritePixel (Video + Col * GO_FB_BYTES_PER_PIXEL, &Color);
        }
      }
      break;
    case EfiBltVideoToBltBuffer:
      if (!OnScreen (SourceX, SourceY, Width, Height) ||
          !BufferFits (BltBuffer, DestinationX, DestinationY, Width, Height, &Delta)) {
        return EFI_INVALID_PARAMETER;
      }
      for (Row = 0; Row < Height; Row++) {
        Video = ScreenPixel (SourceX, SourceY + Row);
        BufferRow = (EFI_GRAPHICS_OUTPUT_BLT_PIXEL *)((UINT8 *)BltBuffer + (DestinationY + Row) * Delta) + DestinationX;
        for (Col = 0; Col < Width; Col++) {
          BufferRow[Col].Blue     = Video[Col * GO_FB_BYTES_PER_PIXEL];
          BufferRow[Col].Green    = Video[Col * GO_FB_BYTES_PER_PIXEL + 1];
          BufferRow[Col].Red      = Video[Col * GO_FB_BYTES_PER_PIXEL + 2];
          BufferRow[Col].Reserved = 0;
        }
      }
      break;
    case EfiBltBufferToVideo:
      if (!OnScreen (DestinationX, DestinationY, Width, Height) ||
          !BufferFits (BltBuffer, SourceX, SourceY, Width, Height, &Delta)) {
        return EFI_INVALID_PARAMETER;
      }
      for (Row = 0; Row < Height; Row++) {
        Video = ScreenPixel (DestinationX, DestinationY + Row);
        BufferRow = (EFI_GRAPHICS_OUTPUT_BLT_PIXEL *)((UINT8 *)BltBuffer + (SourceY + Row) * Delta) + SourceX;
        for (Col = 0; Col < Width; Col++) {
          WritePixel (Video + Col * GO_FB_BYTES_PER_PIXEL, &BufferRow[Col]);
        }
      }
      break;
    case EfiBltVideoToVideo:
      if (!OnScreen (SourceX, SourceY, Width, Height) ||
          !OnScreen (DestinationX, DestinationY, Width, Height)) {
        return EFI_INVALID_PARAMETER;
      }
      // CopyMem permits overlapping rows. Reverse row order for a downward move.
      for (Row = 0; Row < Height; Row++) {
        Offset = (DestinationY > SourceY) ? Height - 1 - Row : Row;
        CopyMem (ScreenPixel (DestinationX, DestinationY + Offset),
                 ScreenPixel (SourceX, SourceY + Offset), Width * GO_FB_BYTES_PER_PIXEL);
      }
      break;
    default:
      return EFI_INVALID_PARAMETER;
  }
  return EFI_SUCCESS;
}

STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL mGop = { QueryMode, SetMode, Blt, &mMode };

EFI_STATUS EFIAPI
InheritedGopDxeEntry (IN EFI_HANDLE ImageHandle, IN EFI_SYSTEM_TABLE *SystemTable)
{
  EFI_HANDLE Handle;

  Handle = NULL;
#ifdef OCULUS_GO_GOP_DEVICE_PATH
  EFI_DEVICE_PATH_UTILITIES_PROTOCOL *Utilities;
  EFI_DEVICE_PATH_PROTOCOL *Path;
  VENDOR_DEVICE_PATH Vendor = { { HARDWARE_DEVICE_PATH, HW_VENDOR_DP, { sizeof (Vendor), 0 } }, { 0 } };
  EFI_STATUS Status = gBS->LocateProtocol (&gEfiDevicePathUtilitiesProtocolGuid, NULL, (VOID **)&Utilities);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  CopyGuid (&Vendor.Guid, &gEfiCallerIdGuid);
  Path = Utilities->AppendDeviceNode (NULL, &Vendor.Header);
  if (Path == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
#ifdef OCULUS_GO_TEXT
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *Text = GoTextConsole (&mGop);
#endif
  Status = gBS->InstallMultipleProtocolInterfaces (&Handle, &gEfiGraphicsOutputProtocolGuid, &mGop,
                                                    &gEfiDevicePathProtocolGuid, Path,
#ifdef OCULUS_GO_TEXT
                                                    &gEfiSimpleTextOutProtocolGuid, Text,
                                                    &gOculusGoConsoleEmblemProtocolGuid, &gGoConsoleEmblem,
#endif
                                                    NULL);
  if (EFI_ERROR (Status)) {
    FreePool (Path);
  }
  return Status;
#else
  return gBS->InstallMultipleProtocolInterfaces (&Handle, &gEfiGraphicsOutputProtocolGuid, &mGop, NULL);
#endif
}
