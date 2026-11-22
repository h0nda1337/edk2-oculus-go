/** Translate UFS requests through the DMA service attached to this controller.
    SPDX-License-Identifier: BSD-2-Clause-Patent **/
#include "GoUfsHc.h"

typedef struct {
  LIST_ENTRY Link;
  VOID       *Token;
  UINTN      Start;
  UINTN      Last;
  BOOLEAN    Granted;
  BOOLEAN    Busy;
  BOOLEAN    RetryCleanup;
} GO_MAP_RECORD;

typedef struct {
  LIST_ENTRY Link;
  UINTN      Start;
  UINTN      Last;
  BOOLEAN    Closing;
} GO_COMMON_BUFFER;

STATIC CONST struct {
  EDKII_IOMMU_OPERATION Operation;
  UINT64                Access;
} mOperation[] = {
  {EdkiiIoMmuOperationBusMasterRead,         EDKII_IOMMU_ACCESS_READ},
  {EdkiiIoMmuOperationBusMasterWrite,        EDKII_IOMMU_ACCESS_WRITE},
  {EdkiiIoMmuOperationBusMasterCommonBuffer, EDKII_IOMMU_ACCESS_READ | EDKII_IOMMU_ACCESS_WRITE}
};

// The provider commits a possible bounce buffer during Unmap. First revoke
// access for this exact device. A failed cleanup keeps the token for retry.
STATIC EFI_STATUS
ReleaseRecord (GO_UFS_HOST *Host, GO_MAP_RECORD *Map)
{
  EFI_STATUS Status = EFI_SUCCESS;
  if (Map->Granted) {
    Status = Host->Dma->SetAttribute (Host->Dma, Host->Controller, Map->Token, 0);
    if (!EFI_ERROR (Status)) {
      Map->Granted = FALSE;
    }
  }
  if (!EFI_ERROR (Status)) {
    Status = Host->Dma->Unmap (Host->Dma, Map->Token);
  }
  EFI_TPL Old = gBS->RaiseTPL (TPL_NOTIFY);
  if (EFI_ERROR (Status)) {
    Map->Busy = FALSE;
    Map->RetryCleanup = TRUE;
  } else {
    RemoveEntryList (&Map->Link);
  }
  gBS->RestoreTPL (Old);
  if (!EFI_ERROR (Status)) {
    FreePool (Map);
  }
  return Status;
}

EFI_STATUS EFIAPI
GoMap (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EDKII_UFS_HOST_CONTROLLER_OPERATION Op,
       VOID *Cpu, UINTN *Bytes, EFI_PHYSICAL_ADDRESS *Bus, VOID **Mapping)
{
  if (This == NULL || (UINTN)Op >= ARRAY_SIZE (mOperation) || Cpu == NULL || Bytes == NULL ||
      Bus == NULL || Mapping == NULL || *Bytes == 0 || *Bytes - 1 > MAX_UINTN - (UINTN)Cpu) {
    return EFI_INVALID_PARAMETER;
  }

  GO_UFS_HOST *Host = GO_HOST (This);
  UINTN Requested = *Bytes;
  *Bus = 0;
  *Mapping = NULL;
  *Bytes = 0;
  GO_MAP_RECORD *Record = AllocateZeroPool (sizeof (*Record));
  if (Record == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  Record->Start = (UINTN)Cpu;
  Record->Last = Record->Start + Requested - 1;
  Record->Busy = TRUE;
  EFI_TPL Old = gBS->RaiseTPL (TPL_NOTIFY);
  // Reserve this address range before invoking the provider. A callback
  // which attempts to free a common buffer cannot race the pending Map.
  BOOLEAN Common = FALSE;
  for (LIST_ENTRY *Link = Host->Allocations.ForwardLink; Link != &Host->Allocations; Link = Link->ForwardLink) {
    GO_COMMON_BUFFER *Buffer = BASE_CR (Link, GO_COMMON_BUFFER, Link);
    if (Buffer->Last < Record->Start || Record->Last < Buffer->Start) {
      continue;
    }
    if (Buffer->Closing || Record->Start < Buffer->Start || Record->Last > Buffer->Last) {
      gBS->RestoreTPL (Old);
      FreePool (Record);
      return EFI_ACCESS_DENIED;
    }
    Common = TRUE;
    break;
  }
  if (Op == EdkiiUfsHcOperationBusMasterCommonBuffer && !Common) {
    gBS->RestoreTPL (Old);
    FreePool (Record);
    return EFI_INVALID_PARAMETER;
  }
  InsertTailList (&Host->Mappings, &Record->Link);
  gBS->RestoreTPL (Old);

  EFI_PHYSICAL_ADDRESS Address;
  UINTN Length = Requested;
  EFI_STATUS Status = Host->Dma->Map (Host->Dma, mOperation[Op].Operation, Cpu, &Length, &Address, &Record->Token);
  if (EFI_ERROR (Status) || Record->Token == NULL) {
    Old = gBS->RaiseTPL (TPL_NOTIFY);
    RemoveEntryList (&Record->Link);
    gBS->RestoreTPL (Old);
    FreePool (Record);
    return EFI_ERROR (Status) ? Status : EFI_DEVICE_ERROR;
  }

  if (Length == 0 || Length > Requested || Address > MAX_UINT32 ||
      Length - 1 > MAX_UINT32 - Address) {
    Status = EFI_UNSUPPORTED;
  } else {
    // Ask for the portable 32-bit aperture. The provider may bounce or
    // translate requests from pages anywhere in CPU address space.
    Status = Host->Dma->SetAttribute (Host->Dma, Host->Controller, Record->Token, mOperation[Op].Access);
  }
  Record->Granted = !EFI_ERROR (Status);
  if (EFI_ERROR (Status)) {
    EFI_STATUS Cleanup = ReleaseRecord (Host, Record);
    return EFI_ERROR (Cleanup) ? Cleanup : Status;
  }

  Record->Busy = FALSE;
  *Bytes = Length;
  *Bus = Address;
  *Mapping = Record;
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
GoUnmap (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, VOID *Mapping)
{
  if (This == NULL || Mapping == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  GO_UFS_HOST *Host = GO_HOST (This);
  EFI_TPL Old = gBS->RaiseTPL (TPL_NOTIFY);
  for (LIST_ENTRY *Link = Host->Mappings.ForwardLink; Link != &Host->Mappings; Link = Link->ForwardLink) {
    GO_MAP_RECORD *Record = BASE_CR (Link, GO_MAP_RECORD, Link);
    if (Record == Mapping && !Record->Busy) {
      Record->Busy = TRUE;
      gBS->RestoreTPL (Old);
      return ReleaseRecord (Host, Record);
    }
  }
  gBS->RestoreTPL (Old);
  return EFI_INVALID_PARAMETER;
}

EFI_STATUS EFIAPI
GoAllocate (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EFI_ALLOCATE_TYPE Type, EFI_MEMORY_TYPE Memory,
            UINTN Pages, VOID **Cpu, UINT64 Attributes)
{
  if (This == NULL || Cpu == NULL || Pages == 0 || Pages > MAX_UINTN / EFI_PAGE_SIZE ||
      (Memory != EfiBootServicesData && Memory != EfiRuntimeServicesData)) {
    return EFI_INVALID_PARAMETER;
  }
  if ((Attributes & ~(EDKII_IOMMU_ATTRIBUTE_MEMORY_WRITE_COMBINE | EDKII_IOMMU_ATTRIBUTE_MEMORY_CACHED)) != 0) {
    return EFI_UNSUPPORTED;
  }
  GO_UFS_HOST *Host = GO_HOST (This);
  *Cpu = NULL;
  GO_COMMON_BUFFER *Buffer = AllocateZeroPool (sizeof (*Buffer));
  if (Buffer == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }
  VOID *Address = NULL;
  EFI_STATUS Status = Host->Dma->AllocateBuffer (Host->Dma, AllocateAnyPages, Memory, Pages, &Address, Attributes);
  if (EFI_ERROR (Status) || Address == NULL) {
    FreePool (Buffer);
    return EFI_ERROR (Status) ? Status : EFI_DEVICE_ERROR;
  }
  Buffer->Start = (UINTN)Address;
  // Page allocation by the provider guarantees an aligned, nonwrapping range.
  Buffer->Last = Buffer->Start + EFI_PAGES_TO_SIZE (Pages) - 1;
  EFI_TPL Old = gBS->RaiseTPL (TPL_NOTIFY);
  InsertTailList (&Host->Allocations, &Buffer->Link);
  gBS->RestoreTPL (Old);
  *Cpu = Address;
  return EFI_SUCCESS;
}

// Called by the buffer owner after its synchronous requests have returned.
// Retry only cleanup that previously failed. A live or busy grant pins RAM.
EFI_STATUS
GoCheckIdle (GO_UFS_HOST *Host, UINTN Start, UINTN Last)
{
  for (;;) {
    GO_MAP_RECORD *Pending = NULL;
    EFI_TPL Old = gBS->RaiseTPL (TPL_NOTIFY);
    for (LIST_ENTRY *Link = Host->Mappings.ForwardLink; Link != &Host->Mappings; Link = Link->ForwardLink) {
      GO_MAP_RECORD *Record = BASE_CR (Link, GO_MAP_RECORD, Link);
      if (Last < Record->Start || Record->Last < Start) {
        continue;
      }
      if (!Record->RetryCleanup || Record->Busy) {
        gBS->RestoreTPL (Old);
        return EFI_ACCESS_DENIED;
      }
      Record->Busy = TRUE;
      Pending = Record;
      break;
    }
    gBS->RestoreTPL (Old);
    if (Pending == NULL) {
      return EFI_SUCCESS;
    }
    EFI_STATUS Status = ReleaseRecord (Host, Pending);
    if (EFI_ERROR (Status)) {
      return Status;
    }
  }
}

EFI_STATUS EFIAPI
GoFree (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, UINTN Pages, VOID *Cpu)
{
  UINTN Start = (UINTN)Cpu;
  if (This == NULL || Cpu == NULL || Pages == 0 || Pages > MAX_UINTN / EFI_PAGE_SIZE ||
      EFI_PAGES_TO_SIZE (Pages) - 1 > MAX_UINTN - Start) {
    return EFI_INVALID_PARAMETER;
  }
  GO_UFS_HOST *Host = GO_HOST (This);
  UINTN Last = Start + EFI_PAGES_TO_SIZE (Pages) - 1;
  GO_COMMON_BUFFER *Buffer = NULL;
  EFI_TPL Old = gBS->RaiseTPL (TPL_NOTIFY);
  for (LIST_ENTRY *Link = Host->Allocations.ForwardLink; Link != &Host->Allocations; Link = Link->ForwardLink) {
    GO_COMMON_BUFFER *Entry = BASE_CR (Link, GO_COMMON_BUFFER, Link);
    if (Entry->Start == Start && Entry->Last == Last) {
      if (Entry->Closing) {
        gBS->RestoreTPL (Old);
        return EFI_ACCESS_DENIED;
      }
      Entry->Closing = TRUE;
      Buffer = Entry;
      break;
    }
  }
  gBS->RestoreTPL (Old);
  if (Buffer == NULL) {
    return EFI_INVALID_PARAMETER;
  }
  EFI_STATUS Status = GoCheckIdle (Host, Start, Last);
  if (!EFI_ERROR (Status)) {
    Status = Host->Dma->FreeBuffer (Host->Dma, Pages, Cpu);
  }
  Old = gBS->RaiseTPL (TPL_NOTIFY);
  if (EFI_ERROR (Status)) {
    Buffer->Closing = FALSE;
  } else {
    RemoveEntryList (&Buffer->Link);
  }
  gBS->RestoreTPL (Old);
  if (!EFI_ERROR (Status)) {
    FreePool (Buffer);
  }
  return Status;
}

EFI_STATUS
GoReleaseProbe (GO_UFS_HOST *Host)
{
  EFI_STATUS Status;
  if (Host->ProbeMap != NULL) {
    Status = GoUnmap (&Host->Hc, Host->ProbeMap);
    if (EFI_ERROR (Status)) {
      return Status;
    }
    Host->ProbeMap = NULL;
  }
  if (Host->ProbePage != NULL) {
    Status = GoFree (&Host->Hc, 1, Host->ProbePage);
    if (EFI_ERROR (Status)) {
      return Status;
    }
    Host->ProbePage = NULL;
  }
  return EFI_SUCCESS;
}

EFI_STATUS
GoProbeDma (GO_UFS_HOST *Host)
{
  EFI_STATUS Status = GoAllocate (&Host->Hc, AllocateAnyPages, EfiBootServicesData, 1, &Host->ProbePage, 0);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  UINTN Bytes = EFI_PAGE_SIZE;
  EFI_PHYSICAL_ADDRESS Bus;
  Status = GoMap (&Host->Hc, EdkiiUfsHcOperationBusMasterCommonBuffer, Host->ProbePage, &Bytes, &Bus, &Host->ProbeMap);
  if (!EFI_ERROR (Status) && (Bytes != EFI_PAGE_SIZE || (Bus & EFI_PAGE_MASK) != 0)) {
    Status = EFI_UNSUPPORTED;
  }
  EFI_STATUS Cleanup = GoReleaseProbe (Host);
  return EFI_ERROR (Cleanup) ? Cleanup : Status;
}
