/** QEMU platform bus for the non-discoverable UFS binding test.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#pragma once
#include <Uefi.h>
#include <Protocol/PciIo.h>

// QEMU 10.0 hw/ufs/ufs.c exposes UFS_SPEC_VER through VER.
#define GO_QEMU_UFS_VERSION 0x0400

typedef enum { Direct, Bounce, DenyTail, ShortTail, WrongHandle, MissingDma, BusyHandoff, RejectProbe, RetryRevoke, Allocation, MissingLun, Gpt, Takeover, NoRelease } PLATFORM_CASE;

EFI_STATUS
PublishFixture (PLATFORM_CASE Mode, EFI_HANDLE *Platform);

EFI_STATUS
PrepareInheritedQueues (PLATFORM_CASE Mode, EFI_HANDLE Controller, EFI_PCI_IO_PROTOCOL *Pci, UINTN Bar);

EFI_STATUS
CheckReplacementQueues (BOOLEAN AfterCapacity);

EFI_STATUS
FinishInheritedQueues (EFI_STATUS Result);

EFI_STATUS
UnpublishInheritedFixture (EFI_STATUS Result);

UINTN
LiveCommonGrant (EFI_PHYSICAL_ADDRESS Bus, UINTN Bytes);

VOID
PrintFixtureStats (VOID);
