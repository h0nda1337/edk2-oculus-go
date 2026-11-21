/** Runtime-sampled boot mark for the text console. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_CONSOLE_EMBLEM_H_
#define GO_CONSOLE_EMBLEM_H_
#include <Uefi.h>

#define GO_LOGO_WIDTH   68
#define GO_LOGO_HEIGHT  42
typedef struct {
  UINT8 Luma[GO_LOGO_HEIGHT][GO_LOGO_WIDTH];
} GO_OCULUS_LOGO;

typedef struct {
  // Copy the mark for presentation at the next clear of the wide text mode.
  VOID (EFIAPI *Set) (CONST GO_OCULUS_LOGO *Logo);
} GO_CONSOLE_EMBLEM_PROTOCOL;
extern EFI_GUID gOculusGoConsoleEmblemProtocolGuid;
#endif
