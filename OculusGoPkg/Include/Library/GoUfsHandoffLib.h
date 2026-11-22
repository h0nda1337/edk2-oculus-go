/** Validate ownership and idle state before the DXE UFS transport initializes.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_HANDOFF_LIB_H_
#define GO_UFS_HANDOFF_LIB_H_

#include <Uefi.h>

// The caller has validated the mapped UFS register range for this device.
// ExpectedVersion is the exact VER for the board/model under test.
EFI_STATUS
GoUfsCheckHandoff (EFI_HANDLE Controller, UINTN MmioBase, UINT32 ExpectedVersion);

#endif
