/** Pacific EVT UFS resource handed from SEC to DXE. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef PACIFIC_UFS_H_
#define PACIFIC_UFS_H_

#include <Uefi.h>

// Coordinates verified in the EVT and live device trees; see docs/UFS_SPLASH.md.
#define PACIFIC_UFS_BASE       0x00624000U
#define PACIFIC_UFS_LENGTH     0x2500U
#define PACIFIC_ENTRY_FDT      0x82000000U
#define PACIFIC_MAX_FDT_BYTES  SIZE_512KB

typedef struct {
  UINT64  Base;
  UINT32  Length;
  UINT32  DmaCoherent;
} GO_PACIFIC_UFS_RESOURCE;

extern EFI_GUID gOculusGoUfsResourceGuid;

BOOLEAN
GoPacificUfsFromFdt (
  CONST VOID *Fdt, UINTN Available, GO_PACIFIC_UFS_RESOURCE *Resource
  );

#endif
