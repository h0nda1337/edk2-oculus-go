/** QEMU platform bus for the non-discoverable UFS binding test.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#pragma once
#include <Uefi.h>

typedef enum { Direct, Bounce, DenyTail, ShortTail, WrongHandle, MissingDma, BusyHandoff, RejectProbe, RetryRevoke, Allocation, MissingLun, Gpt } PLATFORM_CASE;

EFI_STATUS
PublishFixture (PLATFORM_CASE Mode, EFI_HANDLE *Platform);

VOID
PrintFixtureStats (VOID);
