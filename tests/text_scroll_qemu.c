/** Exercise the Pacific text console and packed-BGR GOP in AArch64 user-mode QEMU.
    The host adapter supplies ordinary guest RAM, EDK2 memory calls and protocol installation.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#undef NULL  // EDK2 Base.h supplies its own definition.
#include <PiDxe.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Display/Framebuffer.h>
#include "TextConsole.h"
#include <third-party/edk2/ConsoleFont.h>

EFI_STATUS EFIAPI InheritedGopDxeEntry (EFI_HANDLE Image, EFI_SYSTEM_TABLE *St);
STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL *Display;
STATIC EFI_BOOT_SERVICES Services;
EFI_BOOT_SERVICES *gBS = &Services;
EFI_GUID gEfiGraphicsOutputProtocolGuid = EFI_GRAPHICS_OUTPUT_PROTOCOL_GUID;

VOID *EFIAPI CopyMem (VOID *Dst, CONST VOID *Src, UINTN N) { return memmove (Dst, Src, N); }
VOID *EFIAPI ZeroMem (VOID *Dst, UINTN N) { return memset (Dst, 0, N); }
VOID *EFIAPI AllocateCopyPool (UINTN N, CONST VOID *Src)
{
  VOID *Dst = malloc (N);
  return Dst == NULL ? NULL : memcpy (Dst, Src, N);
}

STATIC EFI_STATUS EFIAPI Capture (EFI_HANDLE *Handle, ...)
{
  va_list Args;
  va_start (Args, Handle);
  assert (va_arg (Args, EFI_GUID *) == &gEfiGraphicsOutputProtocolGuid);
  Display = va_arg (Args, EFI_GRAPHICS_OUTPUT_PROTOCOL *);
  assert (va_arg (Args, VOID *) == NULL);
  va_end (Args);
  return EFI_SUCCESS;
}

// Independent pixel oracle: take the old observed orientation and turn it
// 180 degrees within each eye, including the glyph and its grid position.
STATIC VOID ExpectGlyph (UINT8 *Surface, UINTN Col, UINTN Row, CHAR16 Ch)
{
  for (UINTN Eye = 0; Eye < 2; ++Eye) {
    for (UINTN V = 0; V < 38; ++V) {
      for (UINTN U = 0; U < 16; ++U) {
        UINTN OldX = 245 + 38 * Row + V;
        UINTN OldY = 1279 - (16 * Col + U);
        UINTN X = 1439 - OldX;
        UINTN Y = Eye * 1280 + 1279 - OldY;
        UINT8 *Px = Surface + Y * GO_FB_STRIDE + 3 * X;
        BOOLEAN Ink = (mAsciiFont[Ch - L' '][V / 2] & (0x80 >> (U / 2))) != 0;
        Px[0] = Ink ? 255 : 170;
        Px[1] = Px[2] = Ink ? 255 : 0;
      }
    }
  }
}

int main (void)
{
  UINT8 *Video = mmap ((void *)(UINTN)GO_FB_BASE, GO_FB_SIZE, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
  UINT8 *Expected = malloc (GO_FB_SIZE);
  UINT8 *BeforeScroll = malloc (GO_FB_SIZE);
  assert ((UINTN)Video == GO_FB_BASE && Expected != NULL && BeforeScroll != NULL);
  for (UINTN I = 0; I < GO_FB_SIZE; ++I) {
    Video[I] = (UINT8)((I * 31) ^ (I >> 9));
  }
  memcpy (Expected, Video, GO_FB_SIZE);
  Services.InstallMultipleProtocolInterfaces = Capture;
  assert (InheritedGopDxeEntry (NULL, NULL) == EFI_SUCCESS && Display != NULL);
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *Text = GoTextConsole (Display);
  assert (Text->SetAttribute (Text, EFI_TEXT_ATTR (EFI_WHITE, EFI_BLUE)) == EFI_SUCCESS);

  // Keep the last cell for the subsequent automatic wrap-and-scroll.
  CONST UINTN Corners[][2] = {{0,0}, {79,0}, {0,24}, {78,24}};
  for (UINTN I = 0; I < 4; ++I) {
    CHAR16 Glyph[2] = {(CHAR16)(L'1' + I), 0};
    UINTN Col = Corners[I][0], Row = Corners[I][1];
    assert (Text->SetCursorPosition (Text, Col, Row) == EFI_SUCCESS);
    assert (Text->OutputString (Text, Glyph) == EFI_SUCCESS);
    ExpectGlyph (Expected, Col, Row, Glyph[0]);
    assert (memcmp (Expected, Video, GO_FB_SIZE) == 0);
  }

  assert (Text->SetCursorPosition (Text, 79, 24) == EFI_SUCCESS);
  assert (Text->OutputString (Text, L"F") == EFI_SUCCESS);
  assert (Text->Mode->CursorRow == 24 && Text->Mode->CursorColumn == 0);
  ExpectGlyph (Expected, 79, 24, L'F');
  memcpy (BeforeScroll, Expected, GO_FB_SIZE);
  for (UINTN Y = 0; Y < GO_FB_HEIGHT; ++Y) {
    UINT8 *Dest = Expected + Y * GO_FB_STRIDE;
    CONST UINT8 *Src = BeforeScroll + Y * GO_FB_STRIDE;
    for (UINTN X = 245; X < 283; ++X) {
      Dest[3 * X] = 170;
      Dest[3 * X + 1] = Dest[3 * X + 2] = 0;
    }
    memcpy (Dest + 283 * 3, Src + 245 * 3, 912 * 3);
  }
  assert (memcmp (Expected, Video, GO_FB_SIZE) == 0);
  free (BeforeScroll);
  free (Expected);
  assert (munmap (Video, GO_FB_SIZE) == 0);
  puts ("PASS: paired glyph pixels, asymmetric corners, bottom-right wrap, scroll, margins and background");
  return 0;
}
