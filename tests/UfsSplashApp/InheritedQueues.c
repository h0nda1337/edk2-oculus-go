/** Former-owner fixture for the emulated UFS BAR. No task or transfer is submitted
    from the old lists. Their backing mappings remain live throughout the handoff.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "PlatformFixture.h"
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/IoLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/PacificUfsHandoff.h>
#include <Protocol/PciIo.h>

enum {
  Version = 0x08, InterruptStatus = 0x20, Hcs = 0x30, Hce = 0x34,
  UtrBase = 0x50, UtrDoorbell = 0x58, UtrRun = 0x60,
  UtmBase = 0x70, UtmDoorbell = 0x78, UtmRun = 0x80, UicCommand = 0x90,
  LinkStartup = 0x16, ListOffset = 1024, ListGuard = 0xa5
};

typedef struct {
  UINT8                *Host;
  VOID                 *Token;
  EFI_PHYSICAL_ADDRESS Bus;
  UINTN                Bytes;
} OLD_LIST;

STATIC OLD_LIST mOld[2];
STATIC EFI_PHYSICAL_ADDRESS mReplacement[2];
STATIC UINTN mReplacementGrant[2];
STATIC EFI_PCI_IO_PROTOCOL *mOwner;
STATIC EFI_HANDLE mHandle;
STATIC UINTN mBar;
STATIC BOOLEAN mArmed, mReleased, mAllow, mInstalled, mAttributesChanged;
STATIC UINT64 mOldAttributes;

STATIC UINT64
ReadBase (UINTN Offset)
{
  UINT32 Low = MmioRead32 (mBar + Offset);
  UINT32 High = MmioRead32 (mBar + Offset + 4);
  return LShiftU64 (High, 32) | Low;
}

STATIC BOOLEAN
OldBytesUnchanged (VOID)
{
  for (UINTN I = 0; I < ARRAY_SIZE (mOld); ++I) {
    for (UINTN J = 0; J < EFI_PAGE_SIZE; ++J) {
      UINT8 Expected = (J >= ListOffset && J < ListOffset + mOld[I].Bytes) ? 0 : ListGuard;
      if (mOld[I].Host[J] != Expected) {
        return FALSE;
      }
    }
  }
  return TRUE;
}

STATIC EFI_STATUS EFIAPI
ConfirmRelease (GO_PACIFIC_UFS_HANDOFF_PROTOCOL *This, EFI_HANDLE Controller)
{
  if (Controller != mHandle || !mArmed || mReleased) {
    return EFI_NOT_READY;
  }
  Print (L"PLATFORM RELEASE %s\r\n", mAllow ? L"GRANTED" : L"DENIED");
  mReleased = mAllow;
  return mAllow ? EFI_SUCCESS : EFI_ACCESS_DENIED;
}

STATIC GO_PACIFIC_UFS_HANDOFF_PROTOCOL mHandoff = { ConfirmRelease };

STATIC EFI_STATUS
AllocateOldList (OLD_LIST *List)
{
  EFI_STATUS Status = mOwner->AllocateBuffer (mOwner, AllocateAnyPages, EfiBootServicesData, 1,
                                              (VOID **)&List->Host, 0);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  SetMem (List->Host, EFI_PAGE_SIZE, ListGuard);
  ZeroMem (List->Host + ListOffset, List->Bytes);
  UINTN Length = EFI_PAGE_SIZE;
  Status = mOwner->Map (mOwner, EfiPciIoOperationBusMasterCommonBuffer, List->Host, &Length,
                        &List->Bus, &List->Token);
  if (!EFI_ERROR (Status) && (Length != EFI_PAGE_SIZE || (List->Bus & EFI_PAGE_MASK) != 0 ||
      List->Bus > MAX_UINT64 - EFI_PAGE_SIZE)) {
    return EFI_NO_MAPPING;
  }
  return Status;
}

STATIC BOOLEAN
RunningIdle (BOOLEAN Log)
{
  UINT32 Enabled = MmioRead32 (mBar + Hce);
  UINT32 Transfers = MmioRead32 (mBar + UtrRun);
  UINT32 Tasks = MmioRead32 (mBar + UtmRun);
  UINT32 TransferDb = MmioRead32 (mBar + UtrDoorbell);
  UINT32 TaskDb = MmioRead32 (mBar + UtmDoorbell);
  if (Log) {
    Print (L"PLATFORM INITIAL HCE %x TRR %x TMR %x TRD %x TMD %x\r\n",
           Enabled, Transfers, Tasks, TransferDb, TaskDb);
  }
  return Enabled == 1 && Transfers == 1 && Tasks == 1 && TransferDb == 0 && TaskDb == 0;
}

EFI_STATUS
PrepareInheritedQueues (PLATFORM_CASE Mode, EFI_HANDLE Controller, EFI_PCI_IO_PROTOCOL *Pci, UINTN Bar)
{
  mOwner = Pci;
  mHandle = Controller;
  mAllow = Mode == Takeover;
  mBar = Bar;
  EFI_STATUS Status = Pci->Attributes (Pci, EfiPciIoAttributeOperationGet, 0, &mOldAttributes);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = Pci->Attributes (Pci, EfiPciIoAttributeOperationEnable,
                                       EFI_PCI_IO_ATTRIBUTE_MEMORY | EFI_PCI_IO_ATTRIBUTE_BUS_MASTER, NULL);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  mAttributesChanged = TRUE;
  if (MmioRead32 (Bar + Version) != GO_QEMU_UFS_VERSION || MmioRead32 (Bar + Hce) != 0 ||
      MmioRead32 (Bar + UtrRun) != 0 || MmioRead32 (Bar + UtmRun) != 0 ||
      MmioRead32 (Bar + UtrDoorbell) != 0 || MmioRead32 (Bar + UtmDoorbell) != 0) {
    return EFI_UNSUPPORTED;
  }
  UINT32 Cap = MmioRead32 (Bar);
  mOld[0].Bytes = 32 * ((Cap & 31) + 1);
  mOld[1].Bytes = 80 * (((Cap >> 16) & 7) + 1);
  for (UINTN I = 0; I < ARRAY_SIZE (mOld); ++I) {
    Status = AllocateOldList (&mOld[I]);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  if (mOld[0].Bus == mOld[1].Bus) {
    return EFI_PROTOCOL_ERROR;
  }
  mArmed = TRUE;
  MmioWrite32 (Bar + Hce, 1);
  MmioWrite32 (Bar + UicCommand, LinkStartup);
  if ((MmioRead32 (Bar + Hcs) & 15) != 15) {
    return EFI_DEVICE_ERROR;
  }
  // Acknowledge the fixture owner's completed link-startup UIC command.
  MmioWrite32 (Bar + InterruptStatus, BIT10);
  for (UINTN I = 0; I < ARRAY_SIZE (mOld); ++I) {
    UINTN Offset = I == 0 ? UtrBase : UtmBase;
    EFI_PHYSICAL_ADDRESS Bus = mOld[I].Bus + ListOffset;
    MmioWrite32 (Bar + Offset, (UINT32)Bus);
    MmioWrite32 (Bar + Offset + 4, (UINT32)RShiftU64 (Bus, 32));
  }
  MmioWrite32 (Bar + UtrRun, 1);
  MmioWrite32 (Bar + UtmRun, 1);
  UINT64 Transfer = ReadBase (UtrBase);
  UINT64 Task = ReadBase (UtmBase);
  Print (L"PLATFORM OLD UTR %lx UTM %lx\r\n", Transfer, Task);
  if (Transfer != mOld[0].Bus + ListOffset || Task != mOld[1].Bus + ListOffset) {
    return EFI_PROTOCOL_ERROR;
  }
  if (!RunningIdle (TRUE)) {
    // Stock QEMU 10.0 ignores UTMRLRSR. Never promote a partial fixture.
    return EFI_UNSUPPORTED;
  }
  Status = gBS->InstallProtocolInterface (&mHandle, &gGoPacificUfsHandoffProtocolGuid, EFI_NATIVE_INTERFACE,
                                          &mHandoff);
  mInstalled = !EFI_ERROR (Status);
  return Status;
}

EFI_STATUS
CheckReplacementQueues (BOOLEAN AfterCapacity)
{
  if (!mReleased || !RunningIdle (FALSE) || !OldBytesUnchanged ()) {
    return EFI_PROTOCOL_ERROR;
  }
  EFI_PHYSICAL_ADDRESS Bases[2] = { ReadBase (UtrBase), ReadBase (UtmBase) };
  if (Bases[0] == Bases[1]) {
    return EFI_PROTOCOL_ERROR;
  }
  UINTN Grants[2];
  for (UINTN I = 0; I < ARRAY_SIZE (Bases); ++I) {
    Grants[I] = LiveCommonGrant (Bases[I], mOld[I].Bytes);
    if (Grants[I] == 0 || (Bases[I] & 1023) != 0 ||
        (AfterCapacity && (Bases[I] != mReplacement[I] || Grants[I] != mReplacementGrant[I]))) {
      return EFI_NO_MAPPING;
    }
    for (UINTN J = 0; J < ARRAY_SIZE (mOld); ++J) {
      if (Bases[I] <= mOld[J].Bus + EFI_PAGE_SIZE - 1 &&
          mOld[J].Bus <= Bases[I] + mOld[I].Bytes - 1) {
        return EFI_PROTOCOL_ERROR;
      }
    }
    mReplacement[I] = Bases[I];
    mReplacementGrant[I] = Grants[I];
  }
  if (Grants[0] == Grants[1]) {
    return EFI_PROTOCOL_ERROR;
  }
  if (AfterCapacity) {
    Print (L"PLATFORM NEW MAPS STILL LIVE\r\n");
    Print (L"PLATFORM OLD PRESERVED\r\n");
  } else {
    Print (L"PLATFORM NEW UTR %lx UTM %lx\r\n", Bases[0], Bases[1]);
  }
  return EFI_SUCCESS;
}

EFI_STATUS
FinishInheritedQueues (EFI_STATUS Result)
{
  if (mOwner == NULL) {
    return Result;
  }
  if (mArmed) {
    if (!OldBytesUnchanged ()) {
      return EFI_COMPROMISED_DATA;
    }
    if (!mReleased) {
      if (!mAllow) {
        if (Result != EFI_ACCESS_DENIED || !RunningIdle (FALSE) ||
            ReadBase (UtrBase) != mOld[0].Bus + ListOffset || ReadBase (UtmBase) != mOld[1].Bus + ListOffset) {
          return EFI_PROTOCOL_ERROR;
        }
        Print (L"PLATFORM OLD PRESERVED\r\n");
      }
      Print (L"PLATFORM OWNER CLEANUP\r\n");
      MmioWrite32 (mBar + UtmRun, 0);
      MmioWrite32 (mBar + UtrRun, 0);
      MmioWrite32 (mBar + Hce, 0);
    }
    if (MmioRead32 (mBar + Hce) != 0 || MmioRead32 (mBar + UtmRun) != 0 ||
        MmioRead32 (mBar + UtrRun) != 0) {
      // No DMA page is freed while the hardware may still reference it.
      return EFI_NOT_READY;
    }
  }
  for (UINTN I = 0; I < ARRAY_SIZE (mOld); ++I) {
    EFI_STATUS Status;
    if (mOld[I].Token != NULL) {
      Status = mOwner->Unmap (mOwner, mOld[I].Token);
      if (EFI_ERROR (Status)) {
        return Status;
      }
    }
    if (mOld[I].Host != NULL) {
      Status = mOwner->FreeBuffer (mOwner, 1, mOld[I].Host);
      if (EFI_ERROR (Status)) {
        return Status;
      }
    }
  }
  if (mInstalled) {
    EFI_STATUS Status = gBS->UninstallProtocolInterface (mHandle, &gGoPacificUfsHandoffProtocolGuid, &mHandoff);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  if (mAttributesChanged) {
    EFI_STATUS Status = mOwner->Attributes (mOwner, EfiPciIoAttributeOperationSet, mOldAttributes, NULL);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
  Print (L"PLATFORM OLD BUFFERS FREED\r\n");
  return UnpublishInheritedFixture (Result);
}
