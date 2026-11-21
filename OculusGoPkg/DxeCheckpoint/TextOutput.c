/** Select the console on the verified GOP handle and exercise SystemTable->ConOut.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <PiDxe.h>
#ifdef OCULUS_GO_APP
#include "AppLaunch.h"
#endif
#include <Protocol/GraphicsOutput.h>
#include <Protocol/SimpleTextOut.h>
#include <Library/BaseLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Trial/DxeLayout.h>

STATIC __attribute__((noinline,noreturn)) VOID
TextRejected (VOID)
{
  TrialPaint (0x800080, 0xff0000);
  __asm__ volatile ("dsb sy\n.global TrialTextErrorVisible\nTrialTextErrorVisible: wfe\n b TrialTextErrorVisible");
  __builtin_unreachable ();
}

VOID
TrialTextOutput (UINTN Start, UINTN Limit, EFI_GRAPHICS_OUTPUT_PROTOCOL *Gop)
{
  EFI_HANDLE *Handles;
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *Text;
  EFI_GRAPHICS_OUTPUT_PROTOCOL *Display;
  UINTN Count, Columns, Rows;
  if (gST->ConOut != NULL || gST->ConsoleOutHandle != NULL ||
      gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleTextOutProtocolGuid, NULL, &Count, &Handles) != EFI_SUCCESS ||
      Count != 1 || gBS->HandleProtocol (Handles[0], &gEfiGraphicsOutputProtocolGuid, (VOID **)&Display) != EFI_SUCCESS ||
      Display != Gop || gBS->HandleProtocol (Handles[0], &gEfiSimpleTextOutProtocolGuid, (VOID **)&Text) != EFI_SUCCESS ||
      !TrialSpan ((UINTN)Text->OutputString, 4, Start, Limit) ||
      Text->QueryMode (Text, 0, &Columns, &Rows) != EFI_SUCCESS || Columns != 80 || Rows != 25 ||
      Text->TestString (Text, L"1 EDK2 GO 2\r\n3 UEFI 42 4") != EFI_SUCCESS ||
      Text->TestString (Text, L"\x2603") != EFI_UNSUPPORTED) {
    TextRejected ();
  }
  gST->ConsoleOutHandle = Handles[0];
  gST->ConOut = Text;
  gST->Hdr.CRC32 = 0;
  gST->Hdr.CRC32 = CalculateCrc32 (gST, gST->Hdr.HeaderSize);
  if (gBS->FreePool (Handles) != EFI_SUCCESS ||
      Text->SetCursorPosition (Text, 34, 11) != EFI_SUCCESS ||
      Text->SetAttribute (Text, EFI_WHITE) != EFI_SUCCESS ||
      gST->ConOut->OutputString (gST->ConOut, L"1 EDK2 GO 2\r\n") != EFI_SUCCESS ||
      Text->Mode->CursorRow != 12 || Text->Mode->CursorColumn != 0 ||
      Text->SetCursorPosition (Text, 34, 12) != EFI_SUCCESS ||
      Text->SetAttribute (Text, EFI_LIGHTCYAN) != EFI_SUCCESS ||
      gST->ConOut->OutputString (gST->ConOut, L"3 UEFI 42 4") != EFI_SUCCESS ||
      Text->Mode->CursorRow != 12 || Text->Mode->CursorColumn != 45) {
    TextRejected ();
  }
#ifdef OCULUS_GO_APP
  __asm__ volatile ("dsb sy\n.global TrialTextComplete\nTrialTextComplete:" ::: "memory");
  TrialLaunchApplication ();
#else
  __asm__ volatile ("dsb sy\n.global TrialTextComplete\nTrialTextComplete: wfe\n b TrialTextComplete" ::: "memory");
#endif
  __builtin_unreachable ();
}
