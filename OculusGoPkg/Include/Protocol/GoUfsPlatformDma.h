/** DMA service for one prepared, non-discoverable UFS controller.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_PLATFORM_DMA_H_
#define GO_UFS_PLATFORM_DMA_H_

#include <Protocol/IoMmu.h>

// The interface has the EDKII_IOMMU_PROTOCOL ABI. This private protocol GUID
// confines publication to the client driver and the board UFS device handle.
// System PCI/IOMMU consumers must continue using the system protocol GUID.
// Grant/revoke identify that handle. An incomplete release retains a valid
// retryable mapping; the caller owns its pages until cleanup succeeds.
extern EFI_GUID gGoUfsPlatformDmaProtocolGuid;
#endif
