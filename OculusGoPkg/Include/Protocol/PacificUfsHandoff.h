/** Pacific board handoff for the integrated UFS controller. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef PACIFIC_UFS_HANDOFF_H_
#define PACIFIC_UFS_HANDOFF_H_

#include <Uefi.h>

typedef struct _GO_PACIFIC_UFS_HANDOFF_PROTOCOL GO_PACIFIC_UFS_HANDOFF_PROTOCOL;

// EFI_SUCCESS confirms exclusive DXE ownership of this registered controller,
// its clocks/PHY and accessible registers for the rest of boot services.
// The previous owner has ceased all submissions. It keeps the inherited
// lists, memory and DMA mappings reserved through HCI reset and installation
// of the replacement list bases.
// A provider must obtain the actual platform handoff before confirming it.
struct _GO_PACIFIC_UFS_HANDOFF_PROTOCOL {
  EFI_STATUS (EFIAPI *ConfirmReleased)(
    GO_PACIFIC_UFS_HANDOFF_PROTOCOL *This, EFI_HANDLE Controller
    );
};

extern EFI_GUID gGoPacificUfsHandoffProtocolGuid;

#endif
