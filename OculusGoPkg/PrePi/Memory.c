/** @file
  Original Go memory handoff. Address provenance: docs/MEMORY_MAP.md.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiPei.h>
#include <Library/ArmMmuLib.h>
#include <Library/HobLib.h>
#include <Library/PcdLib.h>
#if defined (OCULUS_GO_GOP_MODEL) || defined (OCULUS_GO_BOOT_CONSOLE)
#include <Display/Framebuffer.h>
#define GO_DISPLAY_REGIONS  1
STATIC_ASSERT ((GO_FB_BASE & EFI_PAGE_MASK) == 0, "Unaligned model surface base");
STATIC_ASSERT ((GO_FB_SIZE & EFI_PAGE_MASK) == 0, "Unaligned model surface size");
#else
#define GO_DISPLAY_REGIONS  0
#endif

#define RAM_ATTRIBUTES (EFI_RESOURCE_ATTRIBUTE_PRESENT | \
  EFI_RESOURCE_ATTRIBUTE_INITIALIZED | EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE | \
  EFI_RESOURCE_ATTRIBUTE_WRITE_COMBINEABLE | EFI_RESOURCE_ATTRIBUTE_WRITE_THROUGH_CACHEABLE | \
  EFI_RESOURCE_ATTRIBUTE_WRITE_BACK_CACHEABLE | EFI_RESOURCE_ATTRIBUTE_TESTED)

EFI_STATUS
OculusGoInitializeMemory (VOID)
{
  ARM_MEMORY_REGION_DESCRIPTOR  Map[6 + GO_DISPLAY_REGIONS];
  VOID                         *Tables;
  UINTN                         TableSize;
  RETURN_STATUS                 Result;

  UINT64 FirmwareBytes = FixedPcdGet32 (PcdFdSize);
#if defined (OCULUS_GO_BOOT_CONSOLE)
  // The remainder of the loader-owned image is the only allocator resource.
  FirmwareBytes = FixedPcdGet64 (PcdSystemMemoryBase) - FixedPcdGet64 (PcdFdBaseAddress);
#endif
  BuildResourceDescriptorHob (EFI_RESOURCE_SYSTEM_MEMORY, RAM_ATTRIBUTES,
    FixedPcdGet64 (PcdSystemMemoryBase), FixedPcdGet64 (PcdSystemMemorySize));
  BuildResourceDescriptorHob (EFI_RESOURCE_SYSTEM_MEMORY, RAM_ATTRIBUTES,
    FixedPcdGet64 (PcdFdBaseAddress), FirmwareBytes);
  BuildMemoryAllocationHob (FixedPcdGet64 (PcdFdBaseAddress),
    FirmwareBytes, EfiBootServicesCode);

  Map[0] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    FixedPcdGet64 (PcdFdBaseAddress), FixedPcdGet64 (PcdFdBaseAddress),
    FirmwareBytes, ARM_MEMORY_REGION_ATTRIBUTE_WRITE_BACK
  };
  Map[1] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    FixedPcdGet64 (PcdSystemMemoryBase), FixedPcdGet64 (PcdSystemMemoryBase),
    FixedPcdGet64 (PcdSystemMemorySize), ARM_MEMORY_REGION_ATTRIBUTE_WRITE_BACK
  };
  Map[2] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    FixedPcdGet64 (PcdGicDistributorBase), FixedPcdGet64 (PcdGicDistributorBase), 0x10000, ARM_MEMORY_REGION_ATTRIBUTE_DEVICE
  };
  Map[3] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    FixedPcdGet64 (PcdGicRedistributorsBase), FixedPcdGet64 (PcdGicRedistributorsBase), 0x100000, ARM_MEMORY_REGION_ATTRIBUTE_DEVICE
  };
#if defined (OCULUS_GO_GOP_MODEL) || defined (OCULUS_GO_BOOT_CONSOLE)
  // Keep the packed scanout outside the DXE page allocator.
  BuildResourceDescriptorHob (EFI_RESOURCE_MEMORY_RESERVED,
    EFI_RESOURCE_ATTRIBUTE_PRESENT | EFI_RESOURCE_ATTRIBUTE_INITIALIZED |
    EFI_RESOURCE_ATTRIBUTE_UNCACHEABLE, GO_FB_BASE, GO_FB_SIZE);
  Map[4] = (ARM_MEMORY_REGION_DESCRIPTOR) {
    GO_FB_BASE, GO_FB_BASE, GO_FB_SIZE,
    ARM_MEMORY_REGION_ATTRIBUTE_UNCACHED_UNBUFFERED
  };
#endif
  UINTN Next = 4 + GO_DISPLAY_REGIONS;
#if defined (OCULUS_GO_BOOT_CONSOLE)
  UINT64 Serial = FixedPcdGet64 (PcdSerialRegisterBase);
  if (Serial != 0) {
    Map[Next++] = (ARM_MEMORY_REGION_DESCRIPTOR) { Serial, Serial, SIZE_4KB, ARM_MEMORY_REGION_ATTRIBUTE_DEVICE };
  }
#endif
  Map[Next] = (ARM_MEMORY_REGION_DESCRIPTOR) { 0, 0, 0, 0 };
  Result = ArmConfigureMmu (Map, &Tables, &TableSize);
  return RETURN_ERROR (Result) ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}
