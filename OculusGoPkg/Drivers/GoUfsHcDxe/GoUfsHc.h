/** On-board UFS host interface. SPDX-License-Identifier: BSD-2-Clause-Patent **/
#ifndef GO_UFS_HC_H_
#define GO_UFS_HC_H_

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/GoUfsPlatformDma.h>
#include <Protocol/GoUfsDmaGuard.h>
#include <Protocol/UfsHostController.h>

typedef struct {
  EDKII_UFS_HOST_CONTROLLER_PROTOCOL Hc;
  GO_UFS_DMA_GUARD_PROTOCOL          Guard;
  EFI_HANDLE                         Controller;
  EDKII_IOMMU_PROTOCOL               *Dma;
  UINTN                              Base;
  UINTN                              Size;
  LIST_ENTRY                         Mappings;
  LIST_ENTRY                         Allocations;
  // Retain the preflight page and both protocol opens if its release failed.
  VOID                               *ProbePage;
  VOID                               *ProbeMap;
  LIST_ENTRY                         PendingLink;
} GO_UFS_HOST;

#define GO_HOST(This) BASE_CR ((This), GO_UFS_HOST, Hc)

EFI_STATUS EFIAPI GoAllocate (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EFI_ALLOCATE_TYPE Type,
                              EFI_MEMORY_TYPE Memory, UINTN Pages, VOID **Cpu, UINT64 Attributes);
EFI_STATUS EFIAPI GoFree (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, UINTN Pages, VOID *Cpu);
EFI_STATUS EFIAPI GoMap (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, EDKII_UFS_HOST_CONTROLLER_OPERATION Op,
                         VOID *Cpu, UINTN *Bytes, EFI_PHYSICAL_ADDRESS *Bus, VOID **Mapping);
EFI_STATUS EFIAPI GoUnmap (EDKII_UFS_HOST_CONTROLLER_PROTOCOL *This, VOID *Mapping);

EFI_STATUS GoCheckIdle (GO_UFS_HOST *Host, UINTN Start, UINTN Last);
EFI_STATUS GoReleaseProbe (GO_UFS_HOST *Host);
EFI_STATUS GoProbeDma (GO_UFS_HOST *Host);

#endif
