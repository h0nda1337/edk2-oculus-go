/** Buffer lifetime of a device-scoped native UFS controller.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_DMA_GUARD_H_
#define GO_UFS_DMA_GUARD_H_

#include <Uefi.h>

typedef struct _GO_UFS_DMA_GUARD_PROTOCOL GO_UFS_DMA_GUARD_PROTOCOL;

// The owner has stopped submitting requests for this entire page range.
// EFI_SUCCESS permits it to release the pages. Any error requires preserving
// them. Cleanup of a previously failed Unmap may be retried. Live requests
// remain owned by their original submitters. Do not reuse retired tokens.
typedef EFI_STATUS (EFIAPI *GO_UFS_CHECK_IDLE) (
  GO_UFS_DMA_GUARD_PROTOCOL *This, EFI_PHYSICAL_ADDRESS Base, UINTN Pages
  );

struct _GO_UFS_DMA_GUARD_PROTOCOL {
  GO_UFS_CHECK_IDLE CheckIdle;
};

extern EFI_GUID gGoUfsDmaGuardProtocolGuid;
#endif
