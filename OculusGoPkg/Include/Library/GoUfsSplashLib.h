/** Read-only access to the Pacific splash. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_SPLASH_LIB_H_
#define GO_UFS_SPLASH_LIB_H_

#include <Uefi.h>
#include <Protocol/GoConsoleEmblem.h>

typedef EFI_STATUS (*GO_READ_SPLASH_BYTES)(VOID *Context, UINT64 Offset, UINTN Size, VOID *Buffer);
typedef BOOLEAN (*GO_DECODE_SPLASH)(GO_READ_SPLASH_BYTES Read, VOID *Context, UINT64 Bytes, GO_OCULUS_LOGO *Logo);

// Addresses describe completed transfers. Their mappings expire at Unmap.
typedef struct {
  EFI_PHYSICAL_ADDRESS Cpu[2];
  EFI_PHYSICAL_ADDRESS Dma[2];
  UINT8                Capacity[2][8];
} GO_UFS_CAPACITY_SAMPLE;

EFI_STATUS
GoUfsTestLun4Buffer (EFI_HANDLE Controller, GO_UFS_CAPACITY_SAMPLE *Result);

BOOLEAN
GoReadUfsLogo (GO_DECODE_SPLASH Decode, GO_OCULUS_LOGO *Logo);

#endif
