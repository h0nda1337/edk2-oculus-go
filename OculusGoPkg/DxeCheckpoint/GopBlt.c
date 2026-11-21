/** Exercise the second dispatched image through the GOP it published.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#include <Protocol/GraphicsOutput.h>
#include <Protocol/DevicePath.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Display/Framebuffer.h>
#include <Trial/DxeLayout.h>

#ifdef OCULUS_GO_TEXT
VOID TrialTextOutput (UINTN Start, UINTN Limit, EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop);
#endif

STATIC CONST UINTN Rows[] = { 640, 1920 };
#define BAND_HEIGHT 32
#define BLOCK_WIDTH (GO_FB_WIDTH / 5)
STATIC_ASSERT (GO_FB_WIDTH % 5 == 0, "five equal blocks");

STATIC __attribute__((noinline,noreturn)) VOID
TrialGopRejected (VOID)
{
  // Replace any incomplete BLT pattern with a distinct raw diagnostic.
  TrialPaint (0x800080, 0);
  __asm__ volatile (".global TrialGopErrorVisible\nTrialGopErrorVisible: wfe\n b TrialGopErrorVisible");
  __builtin_unreachable ();
}

STATIC BOOLEAN
ReadColor (EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop, UINTN X, UINTN Y,
           CONST EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Expected)
{
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Actual = {0xa5, 0xa5, 0xa5, 0xa5};
  return Gop->Blt (Gop, &Actual, EfiBltVideoToBltBuffer, X, Y, 0, 0, 1, 1, 0) == EFI_SUCCESS &&
         CompareMem (&Actual, Expected, sizeof (Actual)) == 0;
}

VOID
TrialGopBlt (UINTN Start, UINTN Limit, CONST EFI_GUID *File)
{
  EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop;
  EFI_GRAPHICS_OUTPUT_MODE_INFORMATION *Info;
  UINTN Bytes;
  EFI_HANDLE *Handles;
  UINTN Count;
  VENDOR_DEVICE_PATH *Vendor;
  EFI_DEVICE_PATH_PROTOCOL *End;
  if (gBS->LocateHandleBuffer (ByProtocol, &gEfiGraphicsOutputProtocolGuid, NULL, &Count, &Handles) != EFI_SUCCESS ||
      Count != 1 || gBS->HandleProtocol (Handles[0], &gEfiDevicePathProtocolGuid, (VOID **)&Vendor) != EFI_SUCCESS ||
      gBS->HandleProtocol (Handles[0], &gEfiGraphicsOutputProtocolGuid, (VOID **)&Gop) != EFI_SUCCESS ||
      gBS->FreePool (Handles) != EFI_SUCCESS ||
      Vendor->Header.Type != HARDWARE_DEVICE_PATH || Vendor->Header.SubType != HW_VENDOR_DP ||
      Vendor->Header.Length[0] != sizeof (*Vendor) || Vendor->Header.Length[1] != 0 ||
      !CompareGuid (&Vendor->Guid, File)) {
    TrialGopRejected ();
  }
  End = (EFI_DEVICE_PATH_PROTOCOL *)(Vendor + 1);
  if (End->Type != END_DEVICE_PATH_TYPE || End->SubType != END_ENTIRE_DEVICE_PATH_SUBTYPE ||
      End->Length[0] != sizeof (*End) || End->Length[1] != 0 ||
      !TrialSpan ((UINTN)Gop->QueryMode, 4, Start, Limit) || !TrialSpan ((UINTN)Gop->Blt, 4, Start, Limit) ||
      Gop->Mode->MaxMode != 1 || Gop->Mode->Mode != 0 ||
      Gop->QueryMode (Gop, 0, &Bytes, &Info) != EFI_SUCCESS || Bytes != sizeof (*Info) ||
      Info->PixelFormat != PixelBltOnly || Info->HorizontalResolution != GO_FB_WIDTH ||
      Info->VerticalResolution != GO_FB_HEIGHT || Info->PixelsPerScanLine != GO_FB_WIDTH ||
      gBS->FreePool (Info) != EFI_SUCCESS) {
    TrialGopRejected ();
  }
  // UEFI BLT pixels are B,G,R,reserved. Scanout stores just the first three.
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Blue = {255,0,0,0}, Red = {0,0,255,0};
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL Black = {0,0,0,0}, Yellow = {0,255,255,0};
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL *Colors[] = { &Blue, &Red, &Black, &Red, &Blue };
  for (UINTN Band = 0; Band < ARRAY_SIZE (Rows); ++Band) {
    for (UINTN I = 0; I < ARRAY_SIZE (Colors); ++I) {
      if (Gop->Blt (Gop, Colors[I], EfiBltVideoFill, 0, 0, I * BLOCK_WIDTH, Rows[Band],
                    BLOCK_WIDTH, BAND_HEIGHT, 0) != EFI_SUCCESS ||
          !ReadColor (Gop, (I + 1) * BLOCK_WIDTH - 1, Rows[Band] + BAND_HEIGHT - 1, Colors[I])) {
        TrialGopRejected ();
      }
    }
  }
  for (UINTN Band = 0; Band < ARRAY_SIZE (Rows); ++Band) {
    if (Gop->Blt (Gop, &Yellow, EfiBltVideoFill, 0, 0, 2 * BLOCK_WIDTH, Rows[Band],
                  BLOCK_WIDTH, BAND_HEIGHT, 0) != EFI_SUCCESS ||
        !ReadColor (Gop, 2 * BLOCK_WIDTH, Rows[Band], &Yellow)) {
      TrialGopRejected ();
    }
  }
#ifdef OCULUS_GO_TEXT
  __asm__ volatile ("dsb sy\n.global TrialGopComplete\nTrialGopComplete:" ::: "memory");
  TrialTextOutput (Start, Limit, Gop);
#else
  __asm__ volatile ("dsb sy\n.global TrialGopComplete\nTrialGopComplete: b TrialGopComplete" ::: "memory");
#endif
  __builtin_unreachable ();
}
