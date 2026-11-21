/** Minimal UEFI application. Output uses the console supplied by its caller.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include <Uefi.h>

EFI_STATUS EFIAPI
ConsoleProbeMain (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
  if (ImageHandle == NULL || SystemTable == NULL || SystemTable->ConOut == NULL) {
    return EFI_UNSUPPORTED;
  }
  EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *Text = SystemTable->ConOut;
  EFI_STATUS Status = Text->SetCursorPosition (Text, 34, 12);
  if (Status == EFI_SUCCESS) {
    Status = Text->SetAttribute (Text, EFI_LIGHTGREEN);
  }
  if (Status == EFI_SUCCESS) {
    Status = Text->OutputString (Text, L"5 APP EFI 6");
  }
  if (Status == EFI_SUCCESS && (Text->Mode->CursorRow != 12 || Text->Mode->CursorColumn != 45)) {
    return EFI_DEVICE_ERROR;
  }
  return Status;
}
